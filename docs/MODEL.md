# DATA MODEL

## Overview

The schema is designed around one hard constraint: every emission record must be fully traceable — you have to be able to answer "where did this number come from, what calculation was applied, who reviewed it, and has it been touched since ingestion?" for every row an auditor looks at.

---

## Entity Relationship (conceptual)

```
Client ──< ClientMembership >── User
  │
  ├──< PlantCode
  ├──< IngestionBatch ──< EmissionRecord ──< EmissionRecordAudit
  │                    ──< FailedRow
  └──                        │
                          EmissionFactor (shared, not client-scoped)
```

---

## Tables

### `Client`
Top-level tenant. Every piece of data carries a `client_id` FK. There is no shared data between clients at the application layer. UUID primary key to avoid leaking record counts through sequential IDs.

Fields worth noting:
- `active_reporting_year`: the year analysts are currently working on. Drives default filters on the dashboard.

### `ClientMembership`
User ↔ Client M2M with a role. Three roles:
- `analyst` — can upload, review, flag, approve, reject
- `admin` — same as analyst plus can manage memberships (Django admin)
- `auditor` — read-only; cannot upload or change review status

### `PlantCode`
SAP plant codes (Werke) are 4-character opaque identifiers like "1000" or "DE01". Without a lookup table, an emission record labelled "1000" is meaningless to a reviewer or auditor. This table maps them to names and countries.

**Why not embed the name on the record?** Because plant names change (re-org, acquisition). The FK means we can update the PlantCode and all historical records reflect the new name. If a plant code appears in an upload that has no PlantCode entry, the record is flagged with `unknown_plant_code_XXXX` and the plant code is stored as `location_name` text as fallback.

### `EmissionFactor`
Emission factors versioned by `(activity_type, source, year)`. This is a shared table (not client-scoped) because factors are published data.

**Why store the FK on EmissionRecord?** If Breathe ESG updates a factor (e.g. IEA revises India grid intensity), old records must NOT silently change. The `emission_factor` FK freezes the calculation. Recalculation is an explicit bulk operation, not an automatic side effect.

Canonical unit for each factor is stored, enabling future consistency checks.

### `IngestionBatch`
Every upload = one batch. Immutable once created. Fields:
- `source_type`: sap | utility | travel
- `uploaded_by`, `uploaded_at`: who triggered this ingestion
- `original_filename`, `raw_file`: the exact file as uploaded, stored for reprocessing
- `period_start`, `period_end`: derived from the earliest and latest activity dates in the batch. Used to flag overlap with previous batches (future feature).
- `error_log`: JSON array of per-row parse failures stored on the batch for quick display without hitting FailedRow table
- `status`: processing → complete | partial | failed

### `EmissionRecord`
The central fact table. One row = one discrete emission-generating activity, post-normalization.

**Unit normalization design:**
- `raw_value` + `raw_unit` = exactly what came from the source file (e.g. 8500 L, 12.5 M3, 1234,56 EUR)
- `canonical_value` + `canonical_unit` = normalized form (litres, kWh, km, kg, USD)
- `co2e_kg` = `canonical_value × emission_factor.factor_kg_co2e_per_unit`

Both raw and canonical values are stored. This means: (1) we can audit conversions, (2) if a unit mapping is wrong we can recalculate without re-uploading, (3) the raw_unit appears in the detail view so analysts can cross-check against the source document.

**Scope classification:**
- `scope`: 1 | 2_location | 2_market | 3
- `scope3_category`: GHG Protocol Scope 3 categories (Cat 1, 4, 6, 7)

We deliberately split Scope 2 into location-based and market-based from the start. Many orgs report both; storing them as distinct values rather than a flag avoids messy filtering.

**Source-specific metadata columns:**
Rather than a JSONB blob, source-specific fields are separate nullable columns. Rationale: SQL filters work directly (e.g. `WHERE sap_document_number = '5000042301'`), type-safe, easier to index. The downside is a wider table with many NULLs, but for a ~10-column set this is acceptable. A JSONB `metadata` field would be preferable if sources were highly variable or user-defined.

**Review workflow:**
`review_status`: pending → flagged → approved | rejected

Approved records are "locked for audit" in the sense that the workflow is complete. In production we would add a `locked_at` timestamp and a permission check preventing any further edits once a reporting period is closed. That is noted in TRADEOFFS.md.

### `EmissionRecordAudit`
Append-only. Never updated. Each change to an EmissionRecord produces a new row with:
- `action`: created | edited | approved | rejected | flagged
- `actor`: the user who made the change
- `diff`: JSON `{field: {before, after}}` for field-level changes
- `note`: free text justification

This satisfies the audit requirement: for any record, you can replay its full history from creation to final approval, with actor and timestamp.

### `FailedRow`
When a row can't be parsed (bad date format, missing unit, non-numeric quantity), it lands here instead of being silently dropped. Fields:
- `raw_data`: the row as parsed (dict)
- `error_message`: why it failed

Analysts can inspect these in the Batches view and decide whether to fix the source file and re-upload.

---

## Multi-tenancy approach

Every query that touches `EmissionRecord`, `IngestionBatch`, or `PlantCode` starts with a filter on `client_id`. The views enforce this via `ClientMembership` lookups on `request.user`. 

In production, row-level security in PostgreSQL would be a secondary enforcement layer. That's not implemented here (noted in TRADEOFFS.md) but the model is designed for it — every relevant table has a `client` FK.

---

## Scope 1/2/3 classification

Classification happens at parse time in the ingestion service. The rules:

| Source | Activity | Default scope |
|--------|----------|---------------|
| SAP (fuel) | diesel_combustion, petrol_combustion, natural_gas_combustion | Scope 1 |
| SAP (procurement) | procurement_spend | Scope 3, Cat 1 |
| Utility | grid_electricity | Scope 2 location-based (market if green tariff detected) |
| Travel | flight, hotel_stay, car_rental, rail_travel | Scope 3, Cat 6 |

Analysts can override scope via the review UI (edit action creates an audit entry). A business case for override: a client who owns renewable energy certificates would reclassify grid electricity to Scope 2 market-based.

---

## Unit normalization

Canonical units by dimension:
- Volume (fuel): **litres** (L, LTR, M3 converted)
- Energy: **kWh** (MWh, GJ, kVAh converted; kVAh flagged)
- Mass: **kg** (g, T converted)
- Distance (travel): **km** (miles converted at 1.60934)
- Currency (procurement): **USD** (INR, EUR, GBP converted at approximate fixed rates; flagged for FX risk)
- Count: **nights** (hotel), no conversion

SAP date formats handled: DD.MM.YYYY (German), YYYYMMDD (internal), MM/DD/YYYY (US), DD-MM-YYYY.
SAP number formats handled: European 1.234,56, US 1,234.56, negatives in parentheses (1.234,56).

---

## Auto-flagging logic

Records are auto-flagged (is_flagged=True, flag_reasons populated) when:
- Quantity is unusually large (> 100,000 in raw unit)
- SAP plant code is missing or not in PlantCode lookup
- SAP document number is missing
- No emission factor found for the activity type
- CO₂e > 100,000 kg in a single record
- Utility billing period > 35 days or < 7 days
- kVAh unit used (approximate conversion)
- Unknown unit
- Travel distance estimated from IATA haversine (not provided by source)
- Car rental distance estimated (50 km/day default)
- Missing traveler name
- Hotel nights assumed (check-in/out not given)

Flagging is additive — multiple flags accumulate in the `flag_reasons` array.
