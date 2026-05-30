"""
Ingestion service: ties parsers to models.
Creates IngestionBatch, EmissionRecord, FailedRow instances from parsed data.
Also handles emission factor lookup and CO2e calculation.
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from .models import (
    IngestionBatch, EmissionRecord, FailedRow, EmissionFactor,
    PlantCode, EmissionRecordAudit
)
from .parsers import parse_sap_file, parse_utility_file, parse_travel_file


# ---------------------------------------------------------------------------
# Emission factor table (DEFRA 2023 / EPA / IEA India 2022)
# ---------------------------------------------------------------------------

DEFAULT_EMISSION_FACTORS = [
    # Scope 1 – combustion
    {'activity_type': 'diesel_combustion',       'source': 'defra', 'year': 2023,
     'factor_kg_co2e_per_unit': '2.68650', 'unit': 'litres',
     'notes': 'DEFRA 2023 UK diesel, includes WTT'},
    {'activity_type': 'petrol_combustion',        'source': 'defra', 'year': 2023,
     'factor_kg_co2e_per_unit': '2.31410', 'unit': 'litres',
     'notes': 'DEFRA 2023 UK petrol, includes WTT'},
    {'activity_type': 'natural_gas_combustion',   'source': 'defra', 'year': 2023,
     'factor_kg_co2e_per_unit': '2.04220', 'unit': 'kWh',
     'notes': 'DEFRA 2023 natural gas kWh gross CV'},
    # Scope 2 – grid electricity (location-based, India 2022 IEA)
    {'activity_type': 'grid_electricity',         'source': 'iea',   'year': 2022,
     'factor_kg_co2e_per_unit': '0.71600', 'unit': 'kWh',
     'notes': 'IEA 2022 India average grid intensity (kgCO2/kWh), location-based'},
    # Scope 3 – travel (DEFRA 2023 including RF)
    {'activity_type': 'flight',                   'source': 'defra', 'year': 2023,
     'factor_kg_co2e_per_unit': '0.19085', 'unit': 'km',
     'notes': 'DEFRA 2023 long-haul economy incl. RF; used as fallback'},
    {'activity_type': 'hotel_stay',               'source': 'defra', 'year': 2023,
     'factor_kg_co2e_per_unit': '31.44000', 'unit': 'nights',
     'notes': 'DEFRA 2023 average hotel room night'},
    {'activity_type': 'car_rental',               'source': 'defra', 'year': 2023,
     'factor_kg_co2e_per_unit': '0.14549', 'unit': 'km',
     'notes': 'DEFRA 2023 average medium car (petrol)'},
    {'activity_type': 'rail_travel',              'source': 'defra', 'year': 2023,
     'factor_kg_co2e_per_unit': '0.03549', 'unit': 'km',
     'notes': 'DEFRA 2023 national rail average'},
    {'activity_type': 'procurement_spend',        'source': 'defra', 'year': 2023,
     'factor_kg_co2e_per_unit': '0.30000', 'unit': 'USD',
     'notes': 'Approximate EEIO spend-based factor; should be refined by category'},
]


def seed_emission_factors():
    """Create default emission factors if they don't exist."""
    for ef in DEFAULT_EMISSION_FACTORS:
        EmissionFactor.objects.get_or_create(
            activity_type=ef['activity_type'],
            source=ef['source'],
            year=ef['year'],
            defaults={
                'factor_kg_co2e_per_unit': Decimal(ef['factor_kg_co2e_per_unit']),
                'unit': ef['unit'],
                'notes': ef['notes'],
            }
        )


def _get_emission_factor(activity_type: str, year: int) -> 'EmissionFactor | None':
    """Get the best emission factor for an activity type and year."""
    # Try exact year match, then fall back to closest year
    try:
        return EmissionFactor.objects.filter(
            activity_type=activity_type, year=year
        ).order_by('-year').first() or EmissionFactor.objects.filter(
            activity_type=activity_type
        ).order_by('-year').first()
    except Exception:
        return None


def _calculate_co2e(record_data: dict, factor: 'EmissionFactor | None') -> 'Decimal | None':
    """Calculate CO2e in kg from canonical value and emission factor."""
    if factor is None:
        return None
    # Travel parser pre-calculates CO2e for flights (distance × class-specific factor)
    # For other types, use canonical_value × factor
    if record_data.get('co2e_kg') is not None:
        return record_data['co2e_kg']
    try:
        canonical = Decimal(str(record_data['canonical_value']))
        return (canonical * factor.factor_kg_co2e_per_unit).quantize(Decimal('0.0001'))
    except Exception:
        return None


@transaction.atomic
def process_upload(client, source_type: str, file_content: bytes, filename: str, user) -> IngestionBatch:
    """
    Main ingestion entry point.
    1. Creates IngestionBatch
    2. Calls appropriate parser
    3. Creates EmissionRecord for each parsed row
    4. Creates FailedRow for each parse error
    5. Updates batch counts and status
    """
    seed_emission_factors()

    batch = IngestionBatch.objects.create(
        client=client,
        source_type=source_type,
        uploaded_by=user,
        original_filename=filename,
        status=IngestionBatch.STATUS_PROCESSING,
    )

    # Parse
    if source_type == IngestionBatch.SOURCE_SAP:
        result = parse_sap_file(file_content, filename)
    elif source_type == IngestionBatch.SOURCE_UTILITY:
        result = parse_utility_file(file_content, filename)
    elif source_type == IngestionBatch.SOURCE_TRAVEL:
        result = parse_travel_file(file_content, filename)
    else:
        batch.status = IngestionBatch.STATUS_FAILED
        batch.error_log = [{'row': 0, 'message': f'Unknown source type: {source_type}'}]
        batch.save()
        return batch

    parsed_records = result.get('records', [])
    parse_errors = result.get('errors', [])

    # Store failed rows
    for err in parse_errors:
        FailedRow.objects.create(
            batch=batch,
            row_number=err.get('row', 0),
            raw_data=err,
            error_message=err.get('message', 'Unknown error'),
        )

    # Determine period bounds for overlap detection
    dates = [r['activity_date'] for r in parsed_records if r.get('activity_date')]
    if dates:
        batch.period_start = min(dates)
        batch.period_end = max(dates)

    # Create emission records
    success_count = 0
    flagged_count = 0

    for rec_data in parsed_records:
        activity_type = rec_data.get('activity_type', '')
        year = rec_data.get('reporting_year', timezone.now().year)
        factor = _get_emission_factor(activity_type, year)
        co2e = _calculate_co2e(rec_data, factor)

        # Resolve plant code
        plant_code_obj = None
        plant_code_raw = rec_data.get('plant_code_raw', '')
        if plant_code_raw:
            plant_code_obj = PlantCode.objects.filter(
                client=client, code=plant_code_raw
            ).first()
            if not plant_code_obj:
                rec_data.setdefault('flag_reasons', [])
                if 'unknown_plant_code' not in rec_data['flag_reasons']:
                    rec_data['flag_reasons'].append(f'unknown_plant_code_{plant_code_raw}')
                    rec_data['is_flagged'] = True

        # Additional anomaly checks
        flags = rec_data.get('flag_reasons', [])
        if co2e is None:
            flags.append('co2e_not_calculated_no_emission_factor')
            rec_data['is_flagged'] = True
        if co2e and co2e > Decimal('100000'):
            flags.append('unusually_high_co2e_kg')
            rec_data['is_flagged'] = True

        record = EmissionRecord.objects.create(
            client=client,
            batch=batch,
            source_row_id=rec_data.get('source_row_id', ''),
            source_type=source_type,
            scope=rec_data.get('scope', '3'),
            scope3_category=rec_data.get('scope3_category', ''),
            activity_type=activity_type,
            raw_value=Decimal(str(rec_data.get('raw_value', 0))),
            raw_unit=rec_data.get('raw_unit', ''),
            canonical_value=Decimal(str(rec_data.get('canonical_value', 0))),
            canonical_unit=rec_data.get('canonical_unit', ''),
            co2e_kg=co2e,
            emission_factor=factor,
            activity_date=rec_data['activity_date'],
            period_end=rec_data.get('period_end'),
            reporting_year=year,
            plant_code=plant_code_obj,
            location_name=rec_data.get('location_name', ''),
            country=rec_data.get('country', ''),
            travel_origin=rec_data.get('travel_origin', ''),
            travel_destination=rec_data.get('travel_destination', ''),
            travel_class=rec_data.get('travel_class', ''),
            traveler_name=rec_data.get('traveler_name', ''),
            distance_km=rec_data.get('distance_km'),
            meter_id=rec_data.get('meter_id', ''),
            tariff_code=rec_data.get('tariff_code', ''),
            sap_document_number=rec_data.get('sap_document_number', ''),
            sap_cost_center=rec_data.get('sap_cost_center', ''),
            sap_material_group=rec_data.get('sap_material_group', ''),
            review_status=EmissionRecord.STATUS_PENDING,
            is_flagged=rec_data.get('is_flagged', False),
            flag_reasons=flags,
        )

        # Create initial audit entry
        EmissionRecordAudit.objects.create(
            record=record,
            action=EmissionRecordAudit.ACTION_CREATED,
            actor=user,
            diff={},
            note=f'Ingested from {filename}',
        )

        success_count += 1
        if record.is_flagged:
            flagged_count += 1

    # Update batch stats
    batch.total_rows = len(parsed_records) + len(parse_errors)
    batch.success_rows = success_count
    batch.failed_rows = len(parse_errors)
    batch.flagged_rows = flagged_count
    batch.error_log = parse_errors
    batch.status = (
        IngestionBatch.STATUS_FAILED if success_count == 0 and parse_errors
        else IngestionBatch.STATUS_PARTIAL if parse_errors
        else IngestionBatch.STATUS_COMPLETE
    )
    batch.save()

    return batch
