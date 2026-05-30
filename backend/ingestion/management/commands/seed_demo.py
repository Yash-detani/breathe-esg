"""
Seed the database with realistic demo data for Breathe ESG.

Creates:
- 1 demo client (Meridian Manufacturing Pvt Ltd)
- 2 users (analyst + admin)
- Plant codes for SAP
- Emission factors
- 3 ingestion batches (SAP, utility, travel) with realistic data
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
import datetime

from ingestion.models import (
    Client, ClientMembership, PlantCode, EmissionFactor,
    IngestionBatch, EmissionRecord, EmissionRecordAudit, FailedRow
)
from ingestion.services import seed_emission_factors


class Command(BaseCommand):
    help = 'Seed database with realistic demo data'

    def handle(self, *args, **options):
        self.stdout.write('Seeding demo data...')

        seed_emission_factors()

        # Client
        client, _ = Client.objects.get_or_create(
            slug='meridian-mfg',
            defaults={
                'name': 'Meridian Manufacturing Pvt Ltd',
                'active_reporting_year': 2024,
            }
        )

        # Users
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@meridian.example',
                'first_name': 'Admin',
                'last_name': 'User',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('demo1234')
            admin_user.save()

        analyst_user, created = User.objects.get_or_create(
            username='analyst',
            defaults={
                'email': 'priya@meridian.example',
                'first_name': 'Priya',
                'last_name': 'Sharma',
            }
        )
        if created:
            analyst_user.set_password('demo1234')
            analyst_user.save()

        ClientMembership.objects.get_or_create(
            user=admin_user, client=client,
            defaults={'role': ClientMembership.ROLE_ADMIN}
        )
        ClientMembership.objects.get_or_create(
            user=analyst_user, client=client,
            defaults={'role': ClientMembership.ROLE_ANALYST}
        )

        # Plant codes
        plant_data = [
            ('1000', 'Pune Plant', 'IN', 'Maharashtra'),
            ('1010', 'Chennai Facility', 'IN', 'Tamil Nadu'),
            ('1020', 'Bengaluru R&D', 'IN', 'Karnataka'),
            ('DE01', 'Frankfurt Office', 'DE', 'Hessen'),
        ]
        for code, name, country, region in plant_data:
            PlantCode.objects.get_or_create(
                client=client, code=code,
                defaults={'name': name, 'country': country, 'region': region}
            )

        ef_diesel = EmissionFactor.objects.filter(
            activity_type='diesel_combustion', source='defra', year=2023
        ).first()
        ef_petrol = EmissionFactor.objects.filter(
            activity_type='petrol_combustion', source='defra', year=2023
        ).first()
        ef_gas = EmissionFactor.objects.filter(
            activity_type='natural_gas_combustion', source='defra', year=2023
        ).first()
        ef_elec = EmissionFactor.objects.filter(
            activity_type='grid_electricity', source='iea', year=2022
        ).first()
        ef_flight = EmissionFactor.objects.filter(
            activity_type='flight', source='defra', year=2023
        ).first()
        ef_hotel = EmissionFactor.objects.filter(
            activity_type='hotel_stay', source='defra', year=2023
        ).first()
        ef_car = EmissionFactor.objects.filter(
            activity_type='car_rental', source='defra', year=2023
        ).first()

        plant_pune = PlantCode.objects.get(client=client, code='1000')
        plant_chennai = PlantCode.objects.get(client=client, code='1010')

        # ---------------------------------------------------------------
        # SAP Batch
        # ---------------------------------------------------------------
        if not IngestionBatch.objects.filter(client=client, source_type='sap').exists():
            sap_batch = IngestionBatch.objects.create(
                client=client,
                source_type='sap',
                uploaded_by=analyst_user,
                original_filename='MB51_fuel_goods_receipts_Q1_2024.csv',
                status='complete',
                total_rows=12,
                success_rows=10,
                failed_rows=2,
                flagged_rows=3,
                period_start=datetime.date(2024, 1, 1),
                period_end=datetime.date(2024, 3, 31),
                error_log=[
                    {'row': 7, 'message': 'Cannot parse quantity: "N/A"'},
                    {'row': 11, 'message': 'Missing unit'},
                ]
            )

            # Realistic SAP fuel records
            sap_records = [
                # Diesel deliveries to Pune plant
                {
                    'source_row_id': '5000042301', 'activity_date': datetime.date(2024, 1, 8),
                    'activity_type': 'diesel_combustion', 'scope': '1',
                    'raw_value': Decimal('8500'), 'raw_unit': 'litres',
                    'canonical_value': Decimal('8500'), 'canonical_unit': 'litres',
                    'co2e_kg': Decimal('8500') * Decimal('2.68650'),
                    'plant_code': plant_pune,
                    'sap_document_number': '5000042301', 'sap_cost_center': 'CC1001',
                    'sap_material_group': 'DIESEL', 'location_name': 'Pune Plant',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'approved',
                },
                {
                    'source_row_id': '5000043112', 'activity_date': datetime.date(2024, 2, 5),
                    'activity_type': 'diesel_combustion', 'scope': '1',
                    'raw_value': Decimal('9200'), 'raw_unit': 'litres',
                    'canonical_value': Decimal('9200'), 'canonical_unit': 'litres',
                    'co2e_kg': Decimal('9200') * Decimal('2.68650'),
                    'plant_code': plant_pune,
                    'sap_document_number': '5000043112', 'sap_cost_center': 'CC1001',
                    'sap_material_group': 'DIESEL', 'location_name': 'Pune Plant',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'pending',
                },
                {
                    'source_row_id': '5000044056', 'activity_date': datetime.date(2024, 3, 12),
                    'activity_type': 'diesel_combustion', 'scope': '1',
                    'raw_value': Decimal('41000'), 'raw_unit': 'litres',  # Unusually high
                    'canonical_value': Decimal('41000'), 'canonical_unit': 'litres',
                    'co2e_kg': Decimal('41000') * Decimal('2.68650'),
                    'plant_code': plant_pune,
                    'sap_document_number': '5000044056', 'sap_cost_center': 'CC1001',
                    'sap_material_group': 'DIESEL', 'location_name': 'Pune Plant',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': ['unusually_large_quantity'],
                    'is_flagged': True,
                    'review_status': 'flagged',
                },
                # Natural gas - Chennai
                {
                    'source_row_id': '5000042890', 'activity_date': datetime.date(2024, 1, 15),
                    'activity_type': 'natural_gas_combustion', 'scope': '1',
                    'raw_value': Decimal('12500'), 'raw_unit': 'kWh',
                    'canonical_value': Decimal('12500'), 'canonical_unit': 'kWh',
                    'co2e_kg': Decimal('12500') * Decimal('2.04220'),
                    'plant_code': plant_chennai,
                    'sap_document_number': '5000042890', 'sap_cost_center': 'CC2001',
                    'sap_material_group': 'GAS', 'location_name': 'Chennai Facility',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'pending',
                },
                {
                    'source_row_id': '5000043445', 'activity_date': datetime.date(2024, 2, 18),
                    'activity_type': 'natural_gas_combustion', 'scope': '1',
                    'raw_value': Decimal('11800'), 'raw_unit': 'kWh',
                    'canonical_value': Decimal('11800'), 'canonical_unit': 'kWh',
                    'co2e_kg': Decimal('11800') * Decimal('2.04220'),
                    'plant_code': plant_chennai,
                    'sap_document_number': '5000043445', 'sap_cost_center': 'CC2001',
                    'sap_material_group': 'ERDGAS', 'location_name': 'Chennai Facility',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'approved',
                },
                # Petrol - company vehicles
                {
                    'source_row_id': '5000043201', 'activity_date': datetime.date(2024, 1, 22),
                    'activity_type': 'petrol_combustion', 'scope': '1',
                    'raw_value': Decimal('1200'), 'raw_unit': 'litres',
                    'canonical_value': Decimal('1200'), 'canonical_unit': 'litres',
                    'co2e_kg': Decimal('1200') * Decimal('2.31410'),
                    'plant_code': plant_pune,
                    'sap_document_number': '5000043201', 'sap_cost_center': 'CC1005',
                    'sap_material_group': 'PETROL', 'location_name': 'Pune Plant',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'pending',
                },
                # Missing plant code - flagged
                {
                    'source_row_id': '5000045001', 'activity_date': datetime.date(2024, 3, 28),
                    'activity_type': 'diesel_combustion', 'scope': '1',
                    'raw_value': Decimal('3400'), 'raw_unit': 'litres',
                    'canonical_value': Decimal('3400'), 'canonical_unit': 'litres',
                    'co2e_kg': Decimal('3400') * Decimal('2.68650'),
                    'plant_code': None,
                    'sap_document_number': '5000045001', 'sap_cost_center': '',
                    'sap_material_group': 'DIESEL', 'location_name': '',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': ['missing_plant_code', 'missing_document_number'],
                    'is_flagged': True,
                    'review_status': 'flagged',
                },
                # Procurement (Scope 3)
                {
                    'source_row_id': '4500089012', 'activity_date': datetime.date(2024, 2, 14),
                    'activity_type': 'procurement_spend', 'scope': '3',
                    'scope3_category': 'cat1_purchased_goods',
                    'raw_value': Decimal('245000'), 'raw_unit': 'INR',
                    'canonical_value': Decimal('2940'), 'canonical_unit': 'USD',
                    'co2e_kg': Decimal('2940') * Decimal('0.30000'),
                    'plant_code': plant_pune,
                    'sap_document_number': '4500089012', 'sap_cost_center': 'CC1010',
                    'sap_material_group': 'CHEMICALS', 'location_name': 'Pune Plant',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': ['co2e_approximate_spend_based_factor'],
                    'is_flagged': True,
                    'review_status': 'pending',
                },
            ]

            for r in sap_records:
                scope3 = r.pop('scope3_category', '')
                rs = r.pop('review_status', 'pending')
                record = EmissionRecord.objects.create(
                    client=client, batch=sap_batch,
                    source_type='sap', scope3_category=scope3,
                    review_status=rs,
                    emission_factor=ef_diesel if 'diesel' in r.get('activity_type','') else
                                    ef_petrol if 'petrol' in r.get('activity_type','') else
                                    ef_gas if 'gas' in r.get('activity_type','') else None,
                    **r
                )
                EmissionRecordAudit.objects.create(
                    record=record, action='created', actor=analyst_user,
                    diff={}, note='Seeded from MB51 export demo data'
                )
                if rs == 'approved':
                    EmissionRecordAudit.objects.create(
                        record=record, action='approved', actor=admin_user,
                        diff={'review_status': {'before': 'pending', 'after': 'approved'}},
                        note='Verified against delivery note'
                    )

            # Failed rows for SAP batch
            FailedRow.objects.get_or_create(
                batch=sap_batch, row_number=7,
                defaults={
                    'raw_data': {'Belegnummer': '5000044999', 'Menge': 'N/A', 'Einheit': 'L',
                                 'Werk': '1000', 'Belegdatum': '14.03.2024'},
                    'error_message': 'Cannot parse quantity: "N/A"'
                }
            )
            FailedRow.objects.get_or_create(
                batch=sap_batch, row_number=11,
                defaults={
                    'raw_data': {'Belegnummer': '5000045100', 'Menge': '500', 'Einheit': '',
                                 'Werk': '1010', 'Belegdatum': '28.03.2024'},
                    'error_message': 'Missing unit'
                }
            )

        # ---------------------------------------------------------------
        # Utility Batch
        # ---------------------------------------------------------------
        if not IngestionBatch.objects.filter(client=client, source_type='utility').exists():
            util_batch = IngestionBatch.objects.create(
                client=client,
                source_type='utility',
                uploaded_by=analyst_user,
                original_filename='MSEDCL_meter_consumption_Q1_2024.csv',
                status='complete',
                total_rows=8,
                success_rows=8,
                failed_rows=0,
                flagged_rows=1,
                period_start=datetime.date(2024, 1, 3),
                period_end=datetime.date(2024, 3, 29),
                error_log=[],
            )

            # Billing periods in India don't align with calendar months
            utility_records = [
                {
                    'source_row_id': 'MTR001_2024-01-03',
                    'activity_date': datetime.date(2024, 1, 3),
                    'period_end': datetime.date(2024, 2, 1),  # 29 days
                    'activity_type': 'grid_electricity', 'scope': '2_location',
                    'raw_value': Decimal('184500'), 'raw_unit': 'kWh',
                    'canonical_value': Decimal('184500'), 'canonical_unit': 'kWh',
                    'co2e_kg': Decimal('184500') * Decimal('0.71600'),
                    'meter_id': 'MTR001', 'tariff_code': 'HT-I',
                    'location_name': 'Pune Plant - Main Supply',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'approved',
                },
                {
                    'source_row_id': 'MTR001_2024-02-02',
                    'activity_date': datetime.date(2024, 2, 2),
                    'period_end': datetime.date(2024, 3, 3),  # 30 days
                    'activity_type': 'grid_electricity', 'scope': '2_location',
                    'raw_value': Decimal('177200'), 'raw_unit': 'kWh',
                    'canonical_value': Decimal('177200'), 'canonical_unit': 'kWh',
                    'co2e_kg': Decimal('177200') * Decimal('0.71600'),
                    'meter_id': 'MTR001', 'tariff_code': 'HT-I',
                    'location_name': 'Pune Plant - Main Supply',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'pending',
                },
                {
                    'source_row_id': 'MTR001_2024-03-04',
                    'activity_date': datetime.date(2024, 3, 4),
                    'period_end': datetime.date(2024, 3, 29),
                    'activity_type': 'grid_electricity', 'scope': '2_location',
                    'raw_value': Decimal('163800'), 'raw_unit': 'kWh',
                    'canonical_value': Decimal('163800'), 'canonical_unit': 'kWh',
                    'co2e_kg': Decimal('163800') * Decimal('0.71600'),
                    'meter_id': 'MTR001', 'tariff_code': 'HT-I',
                    'location_name': 'Pune Plant - Main Supply',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'pending',
                },
                # Chennai - 3 billing periods
                {
                    'source_row_id': 'MTR002_2024-01-05',
                    'activity_date': datetime.date(2024, 1, 5),
                    'period_end': datetime.date(2024, 2, 5),
                    'activity_type': 'grid_electricity', 'scope': '2_location',
                    'raw_value': Decimal('98700'), 'raw_unit': 'kWh',
                    'canonical_value': Decimal('98700'), 'canonical_unit': 'kWh',
                    'co2e_kg': Decimal('98700') * Decimal('0.71600'),
                    'meter_id': 'MTR002', 'tariff_code': 'LT-IV',
                    'location_name': 'Chennai Facility',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'approved',
                },
                # Green tariff (market-based Scope 2)
                {
                    'source_row_id': 'MTR003_2024-01-08',
                    'activity_date': datetime.date(2024, 1, 8),
                    'period_end': datetime.date(2024, 2, 8),
                    'activity_type': 'grid_electricity', 'scope': '2_market',
                    'raw_value': Decimal('45200'), 'raw_unit': 'kWh',
                    'canonical_value': Decimal('45200'), 'canonical_unit': 'kWh',
                    'co2e_kg': Decimal('0'),  # Green tariff = 0 for market-based
                    'meter_id': 'MTR003', 'tariff_code': 'GREEN-SOLAR-ROOFTOP',
                    'location_name': 'Bengaluru R&D - Solar',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'approved',
                },
                # Unusually high spike
                {
                    'source_row_id': 'MTR002_2024-03-01',
                    'activity_date': datetime.date(2024, 3, 1),
                    'period_end': datetime.date(2024, 3, 29),
                    'activity_type': 'grid_electricity', 'scope': '2_location',
                    'raw_value': Decimal('312000'), 'raw_unit': 'kWh',  # spike
                    'canonical_value': Decimal('312000'), 'canonical_unit': 'kWh',
                    'co2e_kg': Decimal('312000') * Decimal('0.71600'),
                    'meter_id': 'MTR002', 'tariff_code': 'LT-IV',
                    'location_name': 'Chennai Facility',
                    'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': ['unusually_high_consumption_kwh'],
                    'is_flagged': True,
                    'review_status': 'flagged',
                },
            ]

            for r in utility_records:
                rs = r.pop('review_status', 'pending')
                EmissionRecord.objects.create(
                    client=client, batch=util_batch,
                    source_type='utility', emission_factor=ef_elec,
                    scope3_category='', review_status=rs,
                    **r
                )

        # ---------------------------------------------------------------
        # Travel Batch
        # ---------------------------------------------------------------
        if not IngestionBatch.objects.filter(client=client, source_type='travel').exists():
            travel_batch = IngestionBatch.objects.create(
                client=client,
                source_type='travel',
                uploaded_by=analyst_user,
                original_filename='Navan_travel_report_Q1_2024.csv',
                status='complete',
                total_rows=15,
                success_rows=13,
                failed_rows=2,
                flagged_rows=4,
                period_start=datetime.date(2024, 1, 10),
                period_end=datetime.date(2024, 3, 25),
                error_log=[
                    {'row': 9, 'message': 'Cannot parse departure date: "TBC"'},
                    {'row': 14, 'message': 'Unknown trip type: "Ferry"'},
                ]
            )

            travel_records = [
                # Long-haul business class BOM→FRA
                {
                    'source_row_id': 'NVN-2024-00145',
                    'activity_date': datetime.date(2024, 1, 15),
                    'period_end': datetime.date(2024, 1, 19),
                    'activity_type': 'flight', 'scope': '3',
                    'scope3_category': 'cat6_business_travel',
                    'raw_value': Decimal('6285'), 'raw_unit': 'km',
                    'canonical_value': Decimal('6285'), 'canonical_unit': 'km',
                    'co2e_kg': Decimal('6285') * Decimal('0.55387'),  # business class
                    'travel_origin': 'BOM', 'travel_destination': 'FRA',
                    'travel_class': 'business',
                    'traveler_name': 'Rajesh Kumar',
                    'distance_km': Decimal('6285'),
                    'location_name': '', 'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'approved',
                },
                # Short-haul economy BLR→DEL
                {
                    'source_row_id': 'NVN-2024-00148',
                    'activity_date': datetime.date(2024, 1, 22),
                    'period_end': datetime.date(2024, 1, 23),
                    'activity_type': 'flight', 'scope': '3',
                    'scope3_category': 'cat6_business_travel',
                    'raw_value': Decimal('1748'), 'raw_unit': 'km',
                    'canonical_value': Decimal('1748'), 'canonical_unit': 'km',
                    'co2e_kg': Decimal('1748') * Decimal('0.15544'),
                    'travel_origin': 'BLR', 'travel_destination': 'DEL',
                    'travel_class': 'economy',
                    'traveler_name': 'Priya Sharma',
                    'distance_km': Decimal('1748'),
                    'location_name': '', 'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'approved',
                },
                # Hotel Frankfurt - 4 nights
                {
                    'source_row_id': 'NVN-2024-00146',
                    'activity_date': datetime.date(2024, 1, 15),
                    'period_end': datetime.date(2024, 1, 19),
                    'activity_type': 'hotel_stay', 'scope': '3',
                    'scope3_category': 'cat6_business_travel',
                    'raw_value': Decimal('4'), 'raw_unit': 'nights',
                    'canonical_value': Decimal('4'), 'canonical_unit': 'nights',
                    'co2e_kg': Decimal('4') * Decimal('31.44'),
                    'travel_origin': '', 'travel_destination': 'FRA',
                    'travel_class': '',
                    'traveler_name': 'Rajesh Kumar',
                    'distance_km': None,
                    'location_name': 'Frankfurt', 'country': 'DE', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'approved',
                },
                # Long-haul BOM→SIN→SYD
                {
                    'source_row_id': 'NVN-2024-00201',
                    'activity_date': datetime.date(2024, 2, 8),
                    'period_end': datetime.date(2024, 2, 12),
                    'activity_type': 'flight', 'scope': '3',
                    'scope3_category': 'cat6_business_travel',
                    'raw_value': Decimal('9994'), 'raw_unit': 'km',
                    'canonical_value': Decimal('9994'), 'canonical_unit': 'km',
                    'co2e_kg': Decimal('9994') * Decimal('0.19085'),
                    'travel_origin': 'BOM', 'travel_destination': 'SYD',
                    'travel_class': 'economy',
                    'traveler_name': 'Anand Patel',
                    'distance_km': Decimal('9994'),
                    'location_name': '', 'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': ['distance_estimated_haversine'],
                    'is_flagged': True,
                    'review_status': 'flagged',
                },
                # Car rental - missing distance, estimated
                {
                    'source_row_id': 'NVN-2024-00210',
                    'activity_date': datetime.date(2024, 2, 8),
                    'period_end': datetime.date(2024, 2, 11),
                    'activity_type': 'car_rental', 'scope': '3',
                    'scope3_category': 'cat6_business_travel',
                    'raw_value': Decimal('150'), 'raw_unit': 'km',
                    'canonical_value': Decimal('150'), 'canonical_unit': 'km',
                    'co2e_kg': Decimal('150') * Decimal('0.14549'),
                    'travel_origin': '', 'travel_destination': 'SYD',
                    'travel_class': '',
                    'traveler_name': 'Anand Patel',
                    'distance_km': Decimal('150'),
                    'location_name': 'Sydney', 'country': 'AU', 'reporting_year': 2024,
                    'flag_reasons': ['car_distance_estimated_50km_per_day'],
                    'is_flagged': True,
                    'review_status': 'pending',
                },
                # Rail travel
                {
                    'source_row_id': 'NVN-2024-00312',
                    'activity_date': datetime.date(2024, 3, 5),
                    'period_end': datetime.date(2024, 3, 5),
                    'activity_type': 'rail_travel', 'scope': '3',
                    'scope3_category': 'cat6_business_travel',
                    'raw_value': Decimal('1400'), 'raw_unit': 'km',
                    'canonical_value': Decimal('1400'), 'canonical_unit': 'km',
                    'co2e_kg': Decimal('1400') * Decimal('0.03549'),
                    'travel_origin': 'DEL', 'travel_destination': 'BOM',
                    'travel_class': '',
                    'traveler_name': 'Meera Iyer',
                    'distance_km': Decimal('1400'),
                    'location_name': '', 'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': [], 'is_flagged': False,
                    'review_status': 'pending',
                },
                # Missing employee name
                {
                    'source_row_id': 'NVN-2024-00398',
                    'activity_date': datetime.date(2024, 3, 18),
                    'period_end': datetime.date(2024, 3, 20),
                    'activity_type': 'flight', 'scope': '3',
                    'scope3_category': 'cat6_business_travel',
                    'raw_value': Decimal('2200'), 'raw_unit': 'km',
                    'canonical_value': Decimal('2200'), 'canonical_unit': 'km',
                    'co2e_kg': Decimal('2200') * Decimal('0.15544'),
                    'travel_origin': 'MAA', 'travel_destination': 'BOM',
                    'travel_class': 'economy',
                    'traveler_name': '',
                    'distance_km': Decimal('2200'),
                    'location_name': '', 'country': 'IN', 'reporting_year': 2024,
                    'flag_reasons': ['missing_employee_name'],
                    'is_flagged': True,
                    'review_status': 'flagged',
                },
            ]

            for r in travel_records:
                rs = r.pop('review_status', 'pending')
                s3 = r.pop('scope3_category', 'cat6_business_travel')
                ef = ef_flight if r.get('activity_type') == 'flight' else \
                     ef_hotel if r.get('activity_type') == 'hotel_stay' else ef_car
                EmissionRecord.objects.create(
                    client=client, batch=travel_batch,
                    source_type='travel', scope3_category=s3,
                    review_status=rs, emission_factor=ef,
                    **r
                )

        self.stdout.write(self.style.SUCCESS(
            '\n✓ Demo data seeded successfully!\n'
            '  Client: Meridian Manufacturing Pvt Ltd\n'
            '  Admin login:    admin / demo1234\n'
            '  Analyst login:  analyst / demo1234\n'
        ))
