"""
Corporate Travel Parser (Concur/Navan CSV export)

Research basis:
We looked at SAP Concur Expense and Travel export formats and Navan (formerly TripActions)
reporting exports. Both platforms let admins export trip reports as CSV/Excel.

Concur specifics:
- "Travel Itinerary Report" CSV: one row per segment (flight leg, hotel night, car day)
- Fields: Report Name, Employee, Departure Date, Departure Location (IATA code or city),
  Arrival Location, Class of Service, Distance (sometimes), Amount, Currency
- Navan "Travel Report" CSV: similar structure, slightly different column names

Key challenges:
1. Flights: distance is sometimes given (km/miles), sometimes only IATA codes provided.
   When only codes given, we estimate using great-circle distance via a simplified formula.
   (Production would use a proper IATA distance database.)
2. Hotel: nights × emission factor. Data gives check-in / check-out dates.
3. Car rental: days × car type × emission factor. Some platforms give distance.
4. Class of service (economy/business/first) multiplies the flight emission factor:
   - Economy: 1×
   - Premium Economy: 1.6×
   - Business: 2.9×
   - First: 4×
   (Source: DEFRA 2023 passenger transport factors)

Scope 3 Category 6 (Business travel) per GHG Protocol.

Emission factor approach for flights:
We use DEFRA 2023 factors for passenger km:
- Short-haul (<3700km) economy: 0.15544 kgCO2e/pkm
- Long-haul (≥3700km) economy: 0.19085 kgCO2e/pkm
- Include radiative forcing (RF) factor of 1.891 for flights (DEFRA methodology)
  RF accounts for non-CO2 warming effects at altitude.
"""

import csv
import io
import math
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

# Approximate lat/lon for major IATA codes (subset for demo; production uses a full DB)
AIRPORT_COORDS = {
    'LHR': (51.4775, -0.4614), 'LGW': (51.1537, -0.1821), 'MAN': (53.3537, -2.2750),
    'JFK': (40.6413, -73.7781), 'LAX': (33.9425, -118.4081), 'ORD': (41.9742, -87.9073),
    'SFO': (37.6213, -122.3790), 'BOS': (42.3656, -71.0096), 'MIA': (25.7959, -80.2870),
    'CDG': (49.0097, 2.5479), 'AMS': (52.3105, 4.7683), 'FRA': (50.0379, 8.5622),
    'MUC': (48.3537, 11.7750), 'MAD': (40.4719, -3.5626), 'BCN': (41.2974, 2.0833),
    'FCO': (41.7999, 12.2462), 'ZRH': (47.4647, 8.5492), 'BRU': (50.9010, 4.4844),
    'DXB': (25.2532, 55.3657), 'SIN': (1.3644, 103.9915), 'HKG': (22.3080, 113.9185),
    'NRT': (35.7720, 140.3929), 'ICN': (37.4602, 126.4407), 'PEK': (40.0801, 116.5846),
    'PVG': (31.1443, 121.8083), 'BOM': (19.0896, 72.8656), 'DEL': (28.5562, 77.1000),
    'BLR': (13.1986, 77.7066), 'MAA': (12.9941, 80.1709), 'HYD': (17.2403, 78.4294),
    'SYD': (-33.9399, 151.1753), 'MEL': (-37.6690, 144.8410), 'DFW': (32.8998, -97.0403),
    'ATL': (33.6367, -84.4281), 'SEA': (47.4502, -122.3088), 'YYZ': (43.6777, -79.6248),
    'GRU': (-23.4356, -46.4731), 'EZE': (-34.8222, -58.5358), 'MEX': (19.4363, -99.0721),
    'CPT': (-33.9715, 18.6021), 'JNB': (-26.1392, 28.2460), 'CAI': (30.1219, 31.4056),
    'IST': (40.9769, 28.8146), 'DOH': (25.2609, 51.6138), 'KUL': (2.7456, 101.7099),
    'BKK': (13.6811, 100.7470), 'CGK': (-6.1275, 106.6537),
}

TRAVEL_COLUMN_ALIASES = {
    'employee': ['Employee', 'Traveler', 'Employee Name', 'Name', 'Traveller', 'User'],
    'booking_ref': ['Report ID', 'Booking Ref', 'Trip ID', 'Reference', 'Booking ID',
                    'Itinerary ID', 'TransactionID'],
    'trip_type': ['Trip Type', 'Category', 'Type', 'Segment Type', 'Mode'],
    'departure_date': ['Departure Date', 'Travel Date', 'Check-in Date', 'Date',
                       'Start Date', 'Pickup Date'],
    'return_date': ['Return Date', 'Check-out Date', 'End Date', 'Drop-off Date'],
    'origin': ['From', 'Origin', 'Departure', 'Departure City', 'Departure Airport',
               'From City', 'Pickup Location'],
    'destination': ['To', 'Destination', 'Arrival', 'Arrival City', 'Arrival Airport',
                    'To City', 'Drop-off Location'],
    'class': ['Class', 'Class of Service', 'Cabin Class', 'Fare Class', 'Service Class'],
    'distance': ['Distance', 'Distance (km)', 'Distance (miles)', 'Miles', 'Km'],
    'distance_unit': ['Distance Unit', 'Unit'],
    'amount': ['Amount', 'Cost', 'Total', 'Fare', 'Price', 'Net Amount'],
    'currency': ['Currency', 'Curr'],
    'nights': ['Nights', 'Duration (nights)', 'Hotel Nights'],
    'hotel_name': ['Hotel', 'Hotel Name', 'Property'],
    'car_type': ['Car Type', 'Vehicle Type', 'Car Category'],
}

# DEFRA 2023 flight emission factors (kgCO2e per pkm, including radiative forcing)
FLIGHT_FACTORS = {
    'short_economy':    Decimal('0.15544'),  # <3700km economy
    'short_business':   Decimal('0.45089'),  # short-haul business (no premium cabin typically)
    'long_economy':     Decimal('0.19085'),  # ≥3700km economy
    'long_premium':     Decimal('0.30537'),  # premium economy long-haul
    'long_business':    Decimal('0.55387'),  # long-haul business
    'long_first':       Decimal('0.76338'),  # long-haul first
}

# Hotel stays: DEFRA 2023 average hotel night (kgCO2e per room night)
# Varies by region — we use global average and flag for region-specific refinement
HOTEL_FACTOR_KG_PER_NIGHT = Decimal('31.44')

# Car rental: DEFRA 2023 average rental car (kgCO2e per km, medium petrol car)
CAR_FACTOR_KG_PER_KM = Decimal('0.14549')

# Class multipliers for when we only have distance (not a specific factor per class)
CLASS_MULTIPLIERS = {
    'economy': Decimal('1.0'),
    'eco': Decimal('1.0'),
    'y': Decimal('1.0'),
    'premium economy': Decimal('1.6'),
    'premium': Decimal('1.6'),
    'w': Decimal('1.6'),
    'business': Decimal('2.9'),
    'biz': Decimal('2.9'),
    'c': Decimal('2.9'),
    'j': Decimal('2.9'),
    'first': Decimal('4.0'),
    'f': Decimal('4.0'),
}


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def _iata_distance_km(origin: str, dest: str) -> Optional[Decimal]:
    """Return great-circle distance between two IATA codes, or None if unknown."""
    o = AIRPORT_COORDS.get(origin.upper().strip())
    d = AIRPORT_COORDS.get(dest.upper().strip())
    if o and d:
        return Decimal(str(round(_haversine_km(o[0], o[1], d[0], d[1]), 1)))
    return None


def _parse_date(raw: str) -> Optional[date]:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ('%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%d', '%d-%m-%Y',
                '%d %b %Y', '%b %d, %Y', '%d.%m.%Y', '%Y%m%d'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(raw: str) -> Optional[Decimal]:
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().replace(',', '').replace(' ', '')
    for sym in ['£', '$', '€', '₹', 'USD', 'GBP', 'EUR', 'INR']:
        cleaned = cleaned.replace(sym, '')
    try:
        return Decimal(cleaned.strip())
    except InvalidOperation:
        return None


def _find_column(headers, aliases):
    hl = {h.lower(): h for h in headers}
    for a in aliases:
        if a in headers:
            return a
        if a.lower() in hl:
            return hl[a.lower()]
    return None


def _infer_trip_type(raw: str) -> str:
    """Map free-text trip type to our activity categories."""
    r = raw.lower().strip()
    if any(k in r for k in ['flight', 'air', 'plane', 'fly']):
        return 'flight'
    if any(k in r for k in ['hotel', 'accommodation', 'lodging', 'stay']):
        return 'hotel_stay'
    if any(k in r for k in ['car', 'rental', 'hire', 'auto', 'taxi', 'uber', 'lyft', 'cab']):
        return 'car_rental'
    if any(k in r for k in ['rail', 'train', 'tram', 'metro', 'subway', 'bus', 'coach']):
        return 'rail_travel'
    return 'flight'  # default for ambiguous rows in travel reports


def _calc_flight_co2(distance_km: Decimal, travel_class: str) -> Decimal:
    cls = travel_class.lower().strip() if travel_class else 'economy'
    long_haul = distance_km >= Decimal('3700')
    if long_haul:
        if cls in ('first', 'f'):
            factor = FLIGHT_FACTORS['long_first']
        elif cls in ('business', 'biz', 'c', 'j'):
            factor = FLIGHT_FACTORS['long_business']
        elif cls in ('premium economy', 'premium', 'w'):
            factor = FLIGHT_FACTORS['long_premium']
        else:
            factor = FLIGHT_FACTORS['long_economy']
    else:
        if cls in ('business', 'biz', 'c', 'j', 'first', 'f'):
            factor = FLIGHT_FACTORS['short_business']
        else:
            factor = FLIGHT_FACTORS['short_economy']
    return (distance_km * factor).quantize(Decimal('0.0001'))


def parse_travel_file(file_content: bytes, filename: str) -> dict:
    """Parse Concur/Navan travel export CSV."""
    text = None
    for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
        try:
            text = file_content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return {'records': [], 'errors': [{'row': 0, 'message': 'Cannot decode file'}]}

    first = text.split('\n')[0]
    sep = ','
    if first.count('\t') > first.count(','):
        sep = '\t'
    elif first.count(';') > first.count(','):
        sep = ';'

    reader = csv.DictReader(io.StringIO(text), delimiter=sep)
    headers = reader.fieldnames or []
    col = {k: _find_column(headers, v) for k, v in TRAVEL_COLUMN_ALIASES.items()}

    records = []
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            def get(key, default=''):
                c = col.get(key)
                return str(row.get(c, default)).strip() if c else default

            employee = get('employee')
            booking_ref = get('booking_ref')
            trip_type_raw = get('trip_type', 'flight')
            dep_date_raw = get('departure_date')
            ret_date_raw = get('return_date')
            origin = get('origin')
            destination = get('destination')
            travel_class = get('class', 'economy')
            distance_raw = get('distance')
            distance_unit = get('distance_unit', 'km')
            nights_raw = get('nights')
            amount_raw = get('amount')
            currency = get('currency', 'USD')

            activity_type = _infer_trip_type(trip_type_raw)

            dep_date = _parse_date(dep_date_raw)
            ret_date = _parse_date(ret_date_raw)
            if dep_date is None:
                errors.append({'row': row_num, 'message': f'Cannot parse departure date: {dep_date_raw!r}'})
                continue

            flags = []
            co2e_kg = None
            distance_km = None

            if activity_type == 'flight':
                # Get or calculate distance
                if distance_raw:
                    dist_val = _parse_decimal(distance_raw)
                    if dist_val:
                        if distance_unit.lower() in ('miles', 'mi', 'mile'):
                            distance_km = dist_val * Decimal('1.60934')
                        else:
                            distance_km = dist_val
                if distance_km is None:
                    distance_km = _iata_distance_km(origin, destination)
                    if distance_km is None:
                        flags.append('distance_unknown_no_iata_coords')
                    else:
                        flags.append('distance_estimated_haversine')
                if distance_km:
                    co2e_kg = _calc_flight_co2(distance_km, travel_class)

                raw_value = distance_km or Decimal('0')
                raw_unit = 'km'
                canonical_value = raw_value
                canonical_unit = 'km'

            elif activity_type == 'hotel_stay':
                nights = None
                if nights_raw:
                    nights = _parse_decimal(nights_raw)
                if nights is None and dep_date and ret_date:
                    nights = Decimal(str((ret_date - dep_date).days))
                if nights is None:
                    nights = Decimal('1')
                    flags.append('hotel_nights_assumed_1')
                co2e_kg = (nights * HOTEL_FACTOR_KG_PER_NIGHT).quantize(Decimal('0.0001'))
                raw_value = nights
                raw_unit = 'nights'
                canonical_value = nights
                canonical_unit = 'nights'

            elif activity_type in ('car_rental', 'rail_travel'):
                if distance_raw:
                    dist_val = _parse_decimal(distance_raw)
                    if dist_val:
                        if distance_unit.lower() in ('miles', 'mi', 'mile'):
                            distance_km = dist_val * Decimal('1.60934')
                        else:
                            distance_km = dist_val
                if distance_km is None:
                    if dep_date and ret_date:
                        days = (ret_date - dep_date).days or 1
                        distance_km = Decimal(str(days * 50))  # 50km/day assumption
                        flags.append('car_distance_estimated_50km_per_day')
                    else:
                        distance_km = Decimal('50')
                        flags.append('car_distance_assumed_50km')
                if activity_type == 'car_rental':
                    co2e_kg = (distance_km * CAR_FACTOR_KG_PER_KM).quantize(Decimal('0.0001'))
                else:
                    # Rail: DEFRA 2023 national rail 0.03549 kgCO2e/pkm
                    co2e_kg = (distance_km * Decimal('0.03549')).quantize(Decimal('0.0001'))
                raw_value = distance_km
                raw_unit = 'km'
                canonical_value = distance_km
                canonical_unit = 'km'

            else:
                raw_value = Decimal('0')
                raw_unit = 'km'
                canonical_value = Decimal('0')
                canonical_unit = 'km'
                flags.append('unknown_trip_type')

            if not employee:
                flags.append('missing_employee_name')
            if not origin and not destination:
                flags.append('missing_location_data')

            cls_norm = travel_class.lower().strip() if travel_class else 'economy'
            if cls_norm not in CLASS_MULTIPLIERS and activity_type == 'flight':
                flags.append(f'unrecognised_class_{cls_norm}')

            records.append({
                'source_row_id': booking_ref or f'row_{row_num}',
                'activity_date': dep_date,
                'period_end': ret_date,
                'reporting_year': dep_date.year,
                'activity_type': activity_type,
                'scope': '3',
                'scope3_category': 'cat6_business_travel',
                'raw_value': raw_value,
                'raw_unit': raw_unit,
                'canonical_value': canonical_value,
                'canonical_unit': canonical_unit,
                'travel_origin': origin[:10] if origin else '',
                'travel_destination': destination[:10] if destination else '',
                'travel_class': cls_norm,
                'traveler_name': employee,
                'distance_km': distance_km,
                'co2e_kg': co2e_kg,
                'flag_reasons': flags,
                'is_flagged': len(flags) > 0,
                'metadata': {
                    'amount': amount_raw,
                    'currency': currency,
                    'trip_type_raw': trip_type_raw,
                    'nights': nights_raw,
                },
            })

        except Exception as e:
            errors.append({'row': row_num, 'message': f'Unexpected error: {str(e)}'})

    return {'records': records, 'errors': errors}
