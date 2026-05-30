"""
SAP Flat File Parser (MM60 / ME2M style export)

Research basis:
SAP's most common export for procurement and fuel data in sustainability contexts
is the flat-file BAPI export from Materials Management (MM) and Plant Maintenance (PM)
modules — specifically:
  - ME2M/ME2L: Purchase orders by material/supplier → gives procurement spend + material
  - MB51: Material document list → gives goods receipts (fuel deliveries, quantities)
  - IW39: PM work orders → sometimes carries fuel consumption

We chose the flat-file (ALV grid export to spreadsheet) rather than IDoc or OData because:
1. Most SAP clients the facilities team is dealing with don't have an activated OData service
2. IDocs require a dedicated ALE/EDI landscape — too heavy for a sustainability team
3. ALV → Excel/CSV is what 90% of SAP users actually hand over

Format characteristics we handle:
- Tab-separated or semicolon-separated (configurable)
- Dates as DD.MM.YYYY (German locale default) or YYYYMMDD (SAP internal)
- Column headers may be German (Menge = quantity, Einheit = unit, Werk = plant)
- Plant code (Werk) is a 4-char code needing lookup
- Units in SAP notation: L (litres), KG (kilograms), M3 (cubic metres), KWH
- Document number (Belegnummer) is our source_row_id
- Cost center (Kostenstelle) maps to our organizational grouping

We handle Scope 1 (fuel combustion from MB51-style goods receipts) and
Scope 3 Cat 1 (procurement spend from ME2M-style PO data).
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

# Maps German SAP column headers to our internal field names
SAP_COLUMN_MAP = {
    # German → internal
    'Belegnummer': 'document_number',
    'Belegdatum': 'document_date',
    'Buchungsdatum': 'posting_date',
    'Werk': 'plant_code',
    'Kostenstelle': 'cost_center',
    'Material': 'material_number',
    'Materialbeschreibung': 'material_description',
    'Warengruppe': 'material_group',
    'Menge': 'quantity',
    'Einheit': 'unit',
    'Nettowert': 'net_value',
    'Währung': 'currency',
    'Lieferant': 'vendor',
    # English fallbacks (some SAP configs export in English)
    'Document Number': 'document_number',
    'Document Date': 'document_date',
    'Posting Date': 'posting_date',
    'Plant': 'plant_code',
    'Cost Center': 'cost_center',
    'Material': 'material_number',
    'Material Description': 'material_description',
    'Material Group': 'material_group',
    'Quantity': 'quantity',
    'Unit': 'unit',
    'Net Value': 'net_value',
    'Currency': 'currency',
    'Vendor': 'vendor',
    # Abbreviated (common in exports)
    'Belegn.': 'document_number',
    'Belegdat.': 'document_date',
}

# SAP unit → canonical unit mapping
SAP_UNIT_MAP = {
    'L': ('litres', 'litres', Decimal('1')),
    'LTR': ('litres', 'litres', Decimal('1')),
    'KG': ('kg', 'kg', Decimal('1')),
    'G': ('g', 'kg', Decimal('0.001')),
    'T': ('tonnes', 'kg', Decimal('1000')),
    'M3': ('m3', 'litres', Decimal('1000')),   # 1 m3 = 1000 L
    'KWH': ('kWh', 'kWh', Decimal('1')),
    'MWH': ('MWh', 'kWh', Decimal('1000')),
    'GJ': ('GJ', 'kWh', Decimal('277.778')),   # 1 GJ = 277.778 kWh
    'EUR': ('EUR', 'USD', Decimal('1.09')),     # approximate, prod would use live FX
    'USD': ('USD', 'USD', Decimal('1')),
    'GBP': ('GBP', 'USD', Decimal('1.27')),
    'INR': ('INR', 'USD', Decimal('0.012')),
}

# Material group → activity type + scope mapping
# SAP material groups (Warengruppe) are client-defined but common patterns exist
MATERIAL_GROUP_MAP = {
    # Fuel material groups
    'FUEL': ('diesel_combustion', '1'),
    'DIESEL': ('diesel_combustion', '1'),
    'PETROL': ('petrol_combustion', '1'),
    'BENZIN': ('petrol_combustion', '1'),   # German
    'GAS': ('natural_gas_combustion', '1'),
    'ERDGAS': ('natural_gas_combustion', '1'),  # German: natural gas
    'HEL': ('diesel_combustion', '1'),      # Heizöl EL = heating oil
    # Procurement / Scope 3
    'ENERGY': ('procurement_spend', '3'),
    'SERVICES': ('procurement_spend', '3'),
    'RAWMAT': ('procurement_spend', '3'),
    'CHEMICALS': ('procurement_spend', '3'),
}

# Keywords in material description → activity type
DESCRIPTION_KEYWORDS = [
    ('diesel', 'diesel_combustion', '1'),
    ('petrol', 'petrol_combustion', '1'),
    ('gasoline', 'petrol_combustion', '1'),
    ('benzin', 'petrol_combustion', '1'),
    ('natural gas', 'natural_gas_combustion', '1'),
    ('erdgas', 'natural_gas_combustion', '1'),
    ('heizöl', 'diesel_combustion', '1'),
    ('heating oil', 'diesel_combustion', '1'),
    ('lpg', 'natural_gas_combustion', '1'),
    ('electricity', 'grid_electricity', '2_location'),
    ('strom', 'grid_electricity', '2_location'),
]


def _parse_sap_date(raw: str) -> Optional[date]:
    """
    SAP exports dates in multiple formats depending on locale and config:
    - DD.MM.YYYY (German default)
    - MM/DD/YYYY (US locale)
    - YYYYMMDD (SAP internal / IDoc)
    - DD-MM-YYYY
    """
    raw = raw.strip()
    if not raw or raw in ('00.00.0000', '0000-00-00', '00000000'):
        return None
    for fmt in ('%d.%m.%Y', '%m/%d/%Y', '%Y%m%d', '%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_sap_decimal(raw: str) -> Optional[Decimal]:
    """
    SAP numbers use European formatting in German locale:
    1.234,56 → 1234.56
    US locale: 1,234.56 → 1234.56
    Also handles negative in parentheses: (123,45)
    """
    raw = raw.strip()
    if not raw or raw == '-':
        return None
    # Negative in parentheses
    negative = raw.startswith('(') and raw.endswith(')')
    if negative:
        raw = raw[1:-1]
    # Determine if European format: last separator is comma with digit groups using dot
    # Heuristic: if there's a comma and the last comma comes after the last dot → European
    if ',' in raw and '.' in raw:
        last_dot = raw.rfind('.')
        last_comma = raw.rfind(',')
        if last_comma > last_dot:
            # European: dots are thousands, comma is decimal
            raw = raw.replace('.', '').replace(',', '.')
        else:
            # US: commas are thousands, dot is decimal
            raw = raw.replace(',', '')
    elif ',' in raw:
        # Assume European decimal comma (no thousands dot)
        raw = raw.replace(',', '.')
    try:
        val = Decimal(raw)
        return -val if negative else val
    except InvalidOperation:
        return None


def _infer_activity(material_group: str, description: str):
    """Infer activity_type and scope from material group and description."""
    mg_upper = material_group.upper().strip()
    if mg_upper in MATERIAL_GROUP_MAP:
        return MATERIAL_GROUP_MAP[mg_upper]
    desc_lower = description.lower()
    for keyword, activity, scope in DESCRIPTION_KEYWORDS:
        if keyword in desc_lower:
            return (activity, scope)
    # Default: treat as procurement spend, Scope 3
    return ('procurement_spend', '3')


def _normalize_unit(sap_unit: str, quantity: Decimal):
    """
    Returns (raw_unit, canonical_unit, canonical_value).
    Converts SAP unit codes to canonical units.
    """
    entry = SAP_UNIT_MAP.get(sap_unit.upper().strip())
    if entry:
        raw_unit, canonical_unit, factor = entry
        return raw_unit, canonical_unit, quantity * factor
    # Unknown unit: pass through unchanged
    return sap_unit, sap_unit, quantity


def parse_sap_file(file_content: bytes, filename: str) -> dict:
    """
    Main entry point. Parses a SAP flat file export (CSV/TSV).
    Returns:
      {
        'records': [list of parsed record dicts],
        'errors': [list of {row, message} dicts],
        'detected_separator': str,
        'detected_encoding': str,
        'column_map_used': dict
      }
    """
    # Detect encoding: SAP commonly exports in Windows-1252 (CP1252) or UTF-8
    encodings_to_try = ['utf-8-sig', 'cp1252', 'latin-1', 'utf-8']
    text = None
    used_encoding = 'utf-8'
    for enc in encodings_to_try:
        try:
            text = file_content.decode(enc)
            used_encoding = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return {'records': [], 'errors': [{'row': 0, 'message': 'Could not decode file'}],
                'detected_separator': '?', 'detected_encoding': 'unknown', 'column_map_used': {}}

    # Detect separator: SAP ALV exports use tab, semicolon, or comma
    first_line = text.split('\n')[0]
    sep = '\t'
    if ';' in first_line and first_line.count(';') > first_line.count('\t'):
        sep = ';'
    elif ',' in first_line and first_line.count(',') > first_line.count('\t'):
        sep = ','

    reader = csv.DictReader(io.StringIO(text), delimiter=sep)
    raw_headers = reader.fieldnames or []

    # Build column map for this specific file
    column_map = {}
    for header in raw_headers:
        if header in SAP_COLUMN_MAP:
            column_map[SAP_COLUMN_MAP[header]] = header

    records = []
    errors = []

    for row_num, row in enumerate(reader, start=2):  # 1-indexed, header is row 1
        try:
            # Extract fields using column map
            def get(internal_name, default=''):
                raw_col = column_map.get(internal_name)
                if raw_col:
                    return str(row.get(raw_col, '')).strip()
                # Try direct match
                return str(row.get(internal_name, default)).strip()

            doc_number = get('document_number')
            doc_date_raw = get('document_date') or get('posting_date')
            plant = get('plant_code')
            cost_center = get('cost_center')
            material_group = get('material_group')
            description = get('material_description')
            quantity_raw = get('quantity')
            unit_raw = get('unit')
            net_value_raw = get('net_value')
            currency = get('currency', 'EUR')

            # Validate required fields
            if not quantity_raw:
                errors.append({'row': row_num, 'message': 'Missing quantity'})
                continue

            quantity = _parse_sap_decimal(quantity_raw)
            if quantity is None:
                errors.append({'row': row_num, 'message': f'Cannot parse quantity: {quantity_raw!r}'})
                continue
            if quantity <= 0:
                errors.append({'row': row_num, 'message': f'Non-positive quantity: {quantity}'})
                continue

            activity_date = _parse_sap_date(doc_date_raw)
            if activity_date is None:
                errors.append({'row': row_num, 'message': f'Cannot parse date: {doc_date_raw!r}'})
                continue

            # Infer activity
            activity_type, scope = _infer_activity(material_group, description)

            # Normalize unit
            if not unit_raw:
                errors.append({'row': row_num, 'message': 'Missing unit'})
                continue

            raw_unit, canonical_unit, canonical_value = _normalize_unit(unit_raw, quantity)

            # Net value (optional, for procurement records)
            net_value = None
            if net_value_raw:
                net_value = _parse_sap_decimal(net_value_raw)

            # Flag conditions
            flags = []
            if quantity > Decimal('100000'):
                flags.append('unusually_large_quantity')
            if not plant:
                flags.append('missing_plant_code')
            if not doc_number:
                flags.append('missing_document_number')

            records.append({
                'source_row_id': doc_number or f'row_{row_num}',
                'activity_date': activity_date,
                'reporting_year': activity_date.year,
                'activity_type': activity_type,
                'scope': scope,
                'raw_value': quantity,
                'raw_unit': raw_unit,
                'canonical_value': canonical_value,
                'canonical_unit': canonical_unit,
                'plant_code_raw': plant,
                'sap_cost_center': cost_center,
                'sap_material_group': material_group,
                'sap_document_number': doc_number,
                'location_name': plant,
                'flag_reasons': flags,
                'is_flagged': len(flags) > 0,
                'metadata': {
                    'description': description,
                    'net_value': str(net_value) if net_value else None,
                    'currency': currency,
                    'vendor': get('vendor'),
                },
            })

        except Exception as e:
            errors.append({'row': row_num, 'message': f'Unexpected error: {str(e)}'})

    return {
        'records': records,
        'errors': errors,
        'detected_separator': sep,
        'detected_encoding': used_encoding,
        'column_map_used': column_map,
    }
