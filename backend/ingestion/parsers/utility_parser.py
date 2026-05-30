"""
Utility Portal CSV Parser (electricity)

Research basis:
Most electricity utilities in developed markets offer a portal where facilities
managers can download consumption data. Common formats:

1. UK: smart meter CSV from Stark/Amber, or manual half-hourly CSV from DNOs
2. US: Green Button (ESPI XML or CSV) from utilities like PG&E, ConEd
3. India: MSEDCL/BESCOM portal exports — custom CSV, usually PDF bills

We chose CSV portal export rather than PDF or API because:
- PDF requires OCR which is unreliable for table extraction across bill layouts
- API: Green Button Connect (ESPI OAuth) exists in the US but not globally;
  UK/India utilities largely don't offer developer APIs
- CSV download is the workflow 80% of facilities teams already use

Format characteristics we handle:
- Meter ID (may be MPAN/MPRN in UK, meter serial number in US/India)
- Account number
- Billing period: start date + end date (NOT calendar months — can span 28-35 days)
- Consumption: kWh (most common) or units that need conversion
- Peak / off-peak split (we sum them; could separate for market-based Scope 2)
- Tariff code (for market-based method documentation)
- Possible kVArh (reactive power) columns — we ignore those, they're not emissions-relevant
- Currency for cost column

We treat electricity as Scope 2 (location-based by default; market-based if tariff
suggests renewable certificate).

Units we handle:
- kWh (canonical)
- MWh → multiply by 1000
- Units (India: 1 unit = 1 kWh)
- kVAh (apparent energy, approximate: multiply by power factor ~0.9; we flag this)
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

# Column header aliases (different portals use different names)
UTILITY_COLUMN_ALIASES = {
    'meter_id': [
        'Meter ID', 'MeterID', 'Meter Serial', 'MPAN', 'MPRN', 'Meter Number',
        'meter_id', 'meter', 'Account Number', 'AccountNo'
    ],
    'period_start': [
        'From Date', 'Start Date', 'Period Start', 'Billing Start', 'FromDate',
        'Read Date From', 'Start', 'period_start', 'from'
    ],
    'period_end': [
        'To Date', 'End Date', 'Period End', 'Billing End', 'ToDate',
        'Read Date To', 'End', 'period_end', 'to'
    ],
    'consumption': [
        'Consumption (kWh)', 'kWh', 'Units Consumed', 'Total kWh', 'Consumption',
        'Energy (kWh)', 'Net Consumption', 'Usage (kWh)', 'consumption', 'usage'
    ],
    'consumption_unit': [
        'Unit', 'Units', 'Consumption Unit', 'Energy Unit', 'unit'
    ],
    'peak_consumption': [
        'Peak kWh', 'Day Units', 'On-Peak', 'Peak Consumption'
    ],
    'offpeak_consumption': [
        'Off-Peak kWh', 'Night Units', 'Off-Peak', 'OffPeak Consumption'
    ],
    'tariff_code': [
        'Tariff', 'Tariff Code', 'Rate Code', 'tariff', 'rate_code', 'Plan'
    ],
    'cost': [
        'Cost', 'Amount', 'Total Amount', 'Bill Amount', 'Charge', 'cost'
    ],
    'currency': [
        'Currency', 'currency', 'Curr.'
    ],
    'location': [
        'Site', 'Location', 'Site Name', 'Premises', 'Address', 'location'
    ],
}

# Renewable tariff indicators → market-based Scope 2
RENEWABLE_TARIFF_KEYWORDS = [
    'green', 'renewable', 'solar', 'wind', 'hydro', 'clean', 'zero', 'rego', 'rec',
    'go100', '100%', 'fit', 'roc'
]


def _find_column(headers: list, aliases: list) -> Optional[str]:
    """Find the first matching header from aliases list."""
    headers_lower = {h.lower().strip(): h for h in headers}
    for alias in aliases:
        if alias in headers:
            return alias
        if alias.lower() in headers_lower:
            return headers_lower[alias.lower()]
    return None


def _parse_date(raw: str) -> Optional[date]:
    """Parse various date formats found in utility exports."""
    raw = raw.strip()
    if not raw:
        return None
    fmts = [
        '%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d', '%d-%m-%Y',
        '%d %b %Y', '%d %B %Y', '%b %d, %Y', '%B %d, %Y',
        '%d.%m.%Y', '%Y%m%d', '%m-%d-%Y'
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(raw: str) -> Optional[Decimal]:
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().replace(',', '').replace(' ', '')
    # Remove currency symbols
    for sym in ['£', '$', '€', '₹', 'INR', 'USD', 'GBP', 'EUR']:
        cleaned = cleaned.replace(sym, '')
    cleaned = cleaned.strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _to_kwh(value: Decimal, unit: str) -> tuple:
    """Convert to kWh. Returns (canonical_value, canonical_unit, flags)."""
    unit_clean = unit.strip().upper() if unit else 'KWH'
    flags = []
    if unit_clean in ('KWH', 'KW.H', 'KILOWATT HOUR', 'UNITS', 'UNIT'):
        return value, 'kWh', flags
    elif unit_clean in ('MWH', 'MW.H', 'MEGAWATT HOUR'):
        return value * Decimal('1000'), 'kWh', flags
    elif unit_clean in ('GWH',):
        return value * Decimal('1000000'), 'kWh', flags
    elif unit_clean in ('GJ', 'GIGAJOULE'):
        return value * Decimal('277.778'), 'kWh', flags
    elif unit_clean in ('KVAH', 'KVA.H'):
        # Apparent energy — approximate with 0.9 power factor, flag it
        flags.append('kvah_approximated_with_power_factor_0.9')
        return value * Decimal('0.9'), 'kWh', flags
    else:
        flags.append(f'unrecognised_unit_{unit_clean}')
        return value, unit_clean, flags


def _infer_scope(tariff: str) -> str:
    """
    Location-based Scope 2 by default.
    If tariff looks like a green/renewable tariff, use market-based.
    """
    if tariff:
        tariff_lower = tariff.lower()
        for kw in RENEWABLE_TARIFF_KEYWORDS:
            if kw in tariff_lower:
                return '2_market'
    return '2_location'


def parse_utility_file(file_content: bytes, filename: str) -> dict:
    """
    Parse a utility portal CSV export.
    Returns same structure as sap_parser.
    """
    encodings_to_try = ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']
    text = None
    for enc in encodings_to_try:
        try:
            text = file_content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return {'records': [], 'errors': [{'row': 0, 'message': 'Cannot decode file'}]}

    # Some portals include header rows with account info before the data table
    # Find the actual header row by looking for date-like column name
    lines = text.split('\n')
    header_row_idx = 0
    for i, line in enumerate(lines[:10]):
        if any(alias.lower() in line.lower() for alias in
               UTILITY_COLUMN_ALIASES['period_start'] + UTILITY_COLUMN_ALIASES['consumption']):
            header_row_idx = i
            break

    data_text = '\n'.join(lines[header_row_idx:])

    # Detect separator
    first = data_text.split('\n')[0]
    sep = ','
    if first.count('\t') > first.count(','):
        sep = '\t'
    elif first.count(';') > first.count(','):
        sep = ';'

    reader = csv.DictReader(io.StringIO(data_text), delimiter=sep)
    headers = reader.fieldnames or []

    # Map columns
    col = {k: _find_column(headers, v) for k, v in UTILITY_COLUMN_ALIASES.items()}

    records = []
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            def get(key, default=''):
                c = col.get(key)
                return str(row.get(c, default)).strip() if c else default

            meter_id = get('meter_id')
            period_start_raw = get('period_start')
            period_end_raw = get('period_end')
            consumption_raw = get('consumption')
            consumption_unit = get('consumption_unit', 'kWh')
            tariff = get('tariff_code')
            location = get('location')

            # Try combining peak + off-peak if no total column
            if not consumption_raw:
                peak_raw = get('peak_consumption')
                offpeak_raw = get('offpeak_consumption')
                peak = _parse_decimal(peak_raw)
                offpeak = _parse_decimal(offpeak_raw)
                if peak is not None and offpeak is not None:
                    consumption_raw = str(peak + offpeak)
                elif peak is not None:
                    consumption_raw = str(peak)
                elif offpeak is not None:
                    consumption_raw = str(offpeak)

            if not consumption_raw:
                errors.append({'row': row_num, 'message': 'No consumption value found'})
                continue

            consumption = _parse_decimal(consumption_raw)
            if consumption is None:
                errors.append({'row': row_num, 'message': f'Cannot parse consumption: {consumption_raw!r}'})
                continue
            if consumption < 0:
                errors.append({'row': row_num, 'message': f'Negative consumption: {consumption}'})
                continue

            period_start = _parse_date(period_start_raw)
            period_end = _parse_date(period_end_raw)

            if period_start is None and period_end is None:
                errors.append({'row': row_num, 'message': 'No date found in row'})
                continue

            activity_date = period_start or period_end

            # Normalize to kWh
            canonical_value, canonical_unit, unit_flags = _to_kwh(consumption, consumption_unit)

            scope = _infer_scope(tariff)

            flags = list(unit_flags)
            if not meter_id:
                flags.append('missing_meter_id')
            if period_start and period_end:
                days = (period_end - period_start).days
                if days > 35:
                    flags.append(f'unusually_long_billing_period_{days}_days')
                if days < 7:
                    flags.append(f'unusually_short_billing_period_{days}_days')
            if consumption > Decimal('1000000'):
                flags.append('unusually_high_consumption_kwh')

            records.append({
                'source_row_id': f"{meter_id}_{period_start_raw}",
                'activity_date': activity_date,
                'period_end': period_end,
                'reporting_year': activity_date.year,
                'activity_type': 'grid_electricity',
                'scope': scope,
                'raw_value': consumption,
                'raw_unit': consumption_unit or 'kWh',
                'canonical_value': canonical_value,
                'canonical_unit': canonical_unit,
                'meter_id': meter_id,
                'tariff_code': tariff,
                'location_name': location,
                'flag_reasons': flags,
                'is_flagged': len(flags) > 0,
                'metadata': {
                    'cost': get('cost'),
                    'currency': get('currency'),
                    'period_start': str(period_start),
                    'period_end': str(period_end),
                },
            })

        except Exception as e:
            errors.append({'row': row_num, 'message': f'Unexpected error: {str(e)}'})

    return {'records': records, 'errors': errors}
