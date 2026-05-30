# SOURCES

For each of the three sources: what real-world format was researched, what was learned, what the sample data looks like and why, and what would break in a real deployment.

---

## 1. SAP — Fuel & Procurement Data

### What was researched

SAP Materials Management (MM) module exposes several transaction codes relevant to sustainability data:

- **MB51** (Material Document List): Shows all goods movements (goods receipts, goods issues). For fuel, this captures deliveries to a plant/cost centre — i.e. the moment diesel or gas was received into inventory, which is the best proxy for consumption in a manufacturing context.
- **ME2M / ME2L** (Purchase Orders by Material / Supplier): Purchase order line items with quantities, units, values. Better for procurement spend (Scope 3 Cat 1) than for direct fuel consumption.
- **IW39** (Plant Maintenance Work Orders): Can carry actual fuel quantities consumed during maintenance tasks. More granular than MB51 but requires PM module to be actively maintained.

The ALV (ABAP List Viewer) grid in each transaction has an "Export to Local File" button that produces CSV, TSV, or Excel. This is the mechanism almost all sustainability leads use — no technical integration required.

**Key things learned:**
- Column headers are controlled by the user's SAP language setting. German-language SAP systems output `Menge` (quantity), `Einheit` (unit), `Werk` (plant), `Belegdatum` (document date). English systems output `Quantity`, `Unit`, `Plant`, `Document Date`. Both forms exist in the same client organisation if they have offices in multiple countries.
- Number formatting follows locale: European (1.234,56 decimal comma) vs US (1,234.56 decimal point). SAP doesn't normalise this on export.
- SAP internal unit codes: `L` (litres), `KG`, `G`, `T` (metric ton), `M3` (cubic metres), `KWH`, `MWH`. These differ from standard SI abbreviations.
- Date formats: `DD.MM.YYYY` (German/European default), `YYYYMMDD` (internal SAP format, appears in some IDoc-derived exports), `MM/DD/YYYY` (US locale).
- Plant codes (Werk) are 4-character alphanumeric codes assigned during SAP implementation (e.g. `1000` for main plant, `DE01` for German office). They are completely opaque without a lookup table.
- Material groups (Warengruppe) are client-defined 9-character codes. Common patterns: `DIESEL`, `PETROL`, `ERDGAS`, `CHEMICALS`. German material group names are common even in multinational SAP systems.

### What the sample data looks like and why

`SAP_MB51_fuel_Q1_2024.csv` uses:
- **Semicolon separator**: Most common in European-locale SAP exports (comma would conflict with decimal comma in numbers).
- **German column headers**: `Belegnummer`, `Belegdatum`, `Werk`, `Menge`, `Einheit` — this is the default for SAP systems installed in Europe/India with German as the system language.
- **European number formatting**: `8.500,000` for 8500 litres, `685.250,00` for ₹685,250.
- **INR currency**: The demo client (Meridian Manufacturing) is India-based.
- **Plant codes 1000, 1010, 1020**: Canonical SAP numbering for a multi-plant Indian manufacturer.
- **Row 8 (N/A quantity)**: Realistic — SAP sometimes exports text values in quantity fields when a goods movement was reversed or partially recorded.
- **Row 7 (missing plant)**: Deliberate anomaly — happens when cost centre is used without a plant assignment, or when goods are issued from a central warehouse with no plant association.

### What would break in a real deployment

1. **Material group taxonomy is client-specific.** Our `MATERIAL_GROUP_MAP` covers common patterns but every SAP client has their own codes. A client using `FUEL-01` instead of `DIESEL` would silently fall through to `procurement_spend` scope 3 instead of scope 1. Production fix: a per-client material group → activity type mapping table, configurable in the UI.

2. **Units outside our map.** Clients in the US might have `GAL` (US gallons) or `MMBTU` (million BTU). Gas utilities often export in `MSCF` (thousand standard cubic feet) or `THERM`. Our parser returns these unrecognised with a flag, but the CO₂e calculation fails. Fix: extend `SAP_UNIT_MAP` and add a unit conversion service.

3. **FX rates are hardcoded.** We use `INR → USD = 0.012` as a fixed rate for procurement spend. On a date-stamped record from 18 months ago, this could be 8% off. Fix: integrate a historical FX rate API (ECB, Open Exchange Rates) and look up the rate at `activity_date`.

4. **Reversed goods movements have negative quantities.** SAP cancellation postings produce a goods movement with a negative `Menge`. Our parser rejects these (non-positive quantity check). In production, negative quantities should cancel a previous record — this requires matching on document reference, which we don't implement (see TRADEOFFS.md duplicate detection).

5. **Multi-currency PO lines.** A PO with line items in multiple currencies produces one export row per line. Our parser handles this correctly but the FX issue above means mixed-currency batches need extra care.

---

## 2. Utility Portal — Electricity

### What was researched

We looked at three utility contexts:

**India (MSEDCL, BESCOM, TPDDL, CESC):**
- All major Indian DISCOMs offer a customer portal where industrial HT (High Tension) and LT (Low Tension) customers can download consumption history as CSV.
- MSEDCL (Maharashtra) portal: "Billing History" download gives Account No, Meter No, From Date, To Date, Units Consumed, Amount. Period is 1–2 months, rarely aligned to calendar months.
- Tariff codes: `HT-I` (industrial HT), `LT-IV` (LT commercial/industrial), `AGR` (agriculture). The tariff code is on the bill but not always in the portal export.
- Units: "Units" in India = kWh. The term is used interchangeably.

**UK (smart meters, DNO half-hourly data):**
- Stark, Amber, and direct DNO portal exports: tab-separated CSV with MPAN (13-digit Meter Point Administration Number), Settlement Date, Period (1–48 for half-hourly), Consumption (kWh).
- We handle daily/monthly rolled-up exports, not half-hourly (which would require aggregation before emissions calc).
- Green tariff indicators: REGO (Renewable Energy Guarantees of Origin), REGo, "100% renewable" in tariff name.

**US (Green Button):**
- Green Button standard (ESPI XML or CSV) used by PG&E, ConEd, etc. CSV variant has columns: `Date`, `Start Time`, `Duration`, `Value`, `Unit`.
- Our parser handles the CSV variant.

**Key things learned:**
- Billing periods in India are explicitly non-calendar. MSEDCL bills one meter from the 3rd of one month to the 1st of the next. This is why `period_end` is a separate field — attributing all consumption to the month of `activity_date` is an approximation.
- kVAh (apparent energy) appears in some industrial tariff exports alongside kWh. It requires a power factor assumption to convert. We flag this.
- The "Total kWh" column is sometimes absent when peak and off-peak are reported separately. We sum them. If neither peak nor off-peak columns exist and total is absent, the row fails.
- Rooftop solar (net metering) can produce negative consumption rows (export to grid). Our parser rejects these with a non-positive consumption error. In production, net metering requires a separate handling path.

### What the sample data looks like and why

`MSEDCL_utility_Q1_2024.csv` uses:
- **Comma-separated**: Standard for Indian utility portal exports.
- **Date format MM/DD/YYYY**: Some portals use this even for Indian clients (portal software may be US-based).
- **Three meters**: MTR001 (Pune HT, large industrial), MTR002 (Chennai LT, medium industrial), MTR003 (Bengaluru, rooftop solar with green tariff).
- **Billing periods of 29–31 days**: Realistic — not aligned to calendar months.
- **MTR002 March spike (312,000 kWh vs ~95,000 kWh normally)**: Realistic anomaly — could be a production ramp-up, a meter error, or an unbundled bill covering two periods. This is exactly the kind of thing an analyst should flag.
- **GREEN-SOLAR-ROOFTOP tariff**: Triggers Scope 2 market-based classification with 0 kgCO₂e (rooftop solar with net metering).

### What would break in a real deployment

1. **Portal formats change without notice.** Utilities update their portal software and the CSV column order or names change. Our alias mapping handles many variants but a novel export would need a new alias added. Fix: a per-utility configuration file with column mappings.

2. **Half-hourly smart meter data.** A large facility with half-hourly data would produce 17,520 rows per meter per year. Our parser handles each row as an individual record, which is correct but creates very large batches. The dashboard aggregation queries would need optimisation (date_trunc grouping).

3. **Net metering / export rows.** A solar installation exporting to grid produces negative consumption. We reject these rows. In production, net metering records should be stored separately (or as negative records) and subtracted from location-based Scope 2 before reporting. This is a common source of double-counting errors.

4. **kVAh approximation.** We multiply kVAh × 0.9 (assumed power factor) to get kWh. Real power factors range 0.75–0.99 depending on equipment. For a large industrial site this could introduce a ±15% error. Fix: require the analyst to provide the site's actual power factor, or ask the utility for active energy (kWh) separately.

5. **Time zone handling.** Portal exports are in local time. When a billing period crosses a DST boundary (rare in India, common in UK/US), the period length appears wrong. Our flagging of periods <7 or >35 days catches egregious cases.

---

## 3. Corporate Travel — Flights, Hotels, Ground Transport

### What was researched

**SAP Concur:**
- Concur Expense report export: one row per expense line (flight, hotel, meal, car). Fields include Report ID, Employee Name, Expense Type, Transaction Date, Merchant Name, Amount, Currency, Business Purpose.
- Concur Travel itinerary export: more structured, one row per travel segment. Fields: Booking ID, Traveler Name, Departure Date/Time, Origin (airport code), Destination (airport code), Class of Service, Fare Basis Code, Ticket Number, Air Cost.
- Both exports are available from the Concur Analytics reporting module as CSV.

**Navan (formerly TripActions):**
- Navan "Travel Report" from the reporting dashboard: one row per trip segment. Fields: Trip ID, Traveler, Segment Type (Air/Hotel/Car/Rail), Travel Date, Origin, Destination, Class, Distance (km, sometimes), Nightly Rate, Total Cost.
- Navan includes distance for flights in some configurations (the airline provides it); Concur typically does not.

**Emission factor research:**
- DEFRA 2023 Greenhouse Gas Reporting: Conversion Factors. Section 6 (Business Travel — air) and Section 7 (Business Travel — hotels and land).
- Flight factors include Radiative Forcing (RF) multiplier of 1.891. DEFRA provides separate factors with and without RF; we use with-RF as DEFRA recommends for scope 3 reporting.
- Class multipliers are implicit in DEFRA's per-class factors (they publish separate economy, premium economy, business, first factors for both short- and long-haul).
- Hotel: DEFRA 2023 average hotel room night = 31.44 kgCO₂e (global average). Regional breakdown available (UK: 16.5, US: 53.7) but not used here as we default global.
- Car rental: DEFRA 2023 average medium petrol car = 0.14549 kgCO₂e/km.
- Rail: DEFRA 2023 UK national rail average = 0.03549 kgCO₂e/pkm. We use this globally which overstates for Indian rail (much lower grid intensity) and understates for diesel rail. Flagging this as an improvement area.

**IATA distance calculation:**
- When travel platforms don't provide distance, we calculate haversine (great-circle) distance between origin and destination IATA codes.
- We store approximate lat/lon for ~60 major airports covering most corporate travel routes.
- Haversine underestimates actual flight distance by 10–15% due to routing, holding patterns, and airways. DEFRA methodology acknowledges this and recommends a routing factor of 1.08 for short-haul and 1.09 for long-haul. We flag haversine-estimated distances so analysts can apply this correction manually.

### What the sample data looks like and why

`Navan_travel_Q1_2024.csv` uses:
- **Navan column names**: "Report ID", "Trip Type", "Class of Service" etc. matching Navan's export format.
- **IATA codes**: BOM (Mumbai), DEL (Delhi), BLR (Bengaluru), MAA (Chennai), FRA (Frankfurt), SYD (Sydney), SIN (Singapore) — realistic routes for a Pune-headquartered manufacturer with German parent company.
- **Mix of distance present and absent**: NVN-2024-00145 (BOM→FRA) provides distance (6285 km). NVN-2024-00201 (BOM→SYD) does not — triggers haversine estimation and flag.
- **Hotel rows linked to flight rows**: NVN-2024-00146 is the hotel stay associated with the Frankfurt trip — same traveler, same dates. One booking reference per segment.
- **Row 10 (TBC departure date)**: Realistic — a future booking where date is not confirmed. Parser fails with "Cannot parse departure date: TBC".
- **Row 14 (Ferry)**: Trip type not in our handled set. Parser fails with "Unknown trip type: Ferry". This is intentional — we document what we handle and what we don't.
- **Row 13 (missing employee name)**: Flagged. Happens when a booking is made centrally and not attributed to an individual.
- **Mixed currencies**: All INR in this sample (reimbursable costs), but IATA codes and distance drive the CO₂e calculation, not cost.

### What would break in a real deployment

1. **IATA code coverage.** Our airport coordinate table covers ~60 airports. A flight to a secondary airport (e.g. Ahmedabad AMD, Kochi COK, Coimbatore CJB) would return `distance_unknown_no_iata_coords`. Fix: use a full IATA database (OpenFlights.org publishes one free) or a flight distance API.

2. **Multi-leg trips.** A BOM→DXB→LHR itinerary might appear as one row (BOM→LHR) or two rows (BOM→DXB, DXB→LHR) depending on how the platform exports it. If stored as BOM→LHR, haversine gives 7,194 km — significantly less than the actual two-leg distance (~9,600 km). Fix: require segment-level data; reject or flag city-pair entries that span more than one timezone jump.

3. **Hotel regional factors.** We use a global average (31.44 kgCO₂e/night) for all hotels. A Frankfurt 5-star hotel has very different emissions from a Chennai business hotel. DEFRA and EPA publish regional factors; Scope 3 cat 6 guidance recommends hotel-specific data where available. Without this, hotel emissions are at best ±50% accurate.

4. **Radiative Forcing disagreement.** Some clients (and some audit frameworks) report flights without RF because IPCC GHG Protocol Scope 3 standard only requires CO₂. Others include RF. We include it (DEFRA recommendation). This is a ~2x difference on flight emissions and must be a client-level configuration, not a hardcoded choice.

5. **Rail factors are UK-specific.** We use DEFRA UK rail (0.035 kgCO₂e/pkm) for all rail travel. Indian Railways runs predominantly on electric traction at ~0.015 kgCO₂e/pkm (CEA 2022); European high-speed rail is ~0.006. Using UK national rail globally overestimates Indian rail emissions by ~2.3×. Fix: country-specific rail factors.
