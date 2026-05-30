# DECISIONS

Every ambiguity I resolved, the choice made, the reasoning, and what I would have asked the PM.

---

## SAP: Which export mechanism?

**Options considered:**
- **IDoc (ANSI X12 / EDIFACT)**: SAP's native EDI format. Rigorous, complete. Requires ALE/EDI landscape active on the client's SAP system and a receiving middleware. Very few sustainability teams have this set up.
- **OData service (SAP Gateway)**: REST API, well-structured. Requires SAP Gateway component licensed and activated. Many on-premise SAP S/4HANA systems have it; older ECC systems often don't. Would also require an OAuth client registered in the client's system.
- **BAPI call**: SAP function module, callable from ABAP or via RFC connector. Requires network access to SAP RFC port (3300) and a technical user. Not realistic for a third-party SaaS ingesting from many clients.
- **ALV flat file / transaction export (chosen)**: The Analyze, List, View grid in SAP transactions MB51 (material documents) and ME2M (purchase orders) can be exported to spreadsheet/CSV via the "Local File" button. Every SAP user can do this. Zero infrastructure requirements. This is what 90% of sustainability leads are actually emailing over.

**Choice: ALV flat file CSV/TSV from MB51 and ME2M.**

**Tradeoffs:** The export is manual (someone runs the transaction and saves the file). It has no API, no scheduling. Headers vary by user's language setting and SAP version. We handle German and English headers via a column alias map.

**Subset handled:** Goods receipts (MB51) for fuel consumption (Scope 1: diesel, petrol, natural gas, LPG) and purchase orders (ME2M) for procurement spend (Scope 3 Cat 1). We do NOT handle: PM work orders (IW39) for maintenance fuel, CO-PA profitability analysis, or MM inventory movements for product transport.

**What I'd ask the PM:** Does the client's SAP system have Gateway active? If yes, we should build an OData connector in phase 2 — it eliminates the manual export step and reduces lag from days to real-time.

---

## Utility: Portal CSV vs PDF vs API

**Options considered:**
- **PDF bill**: Richest document (tariff structure, reactive power, penalties). Requires OCR + table extraction. Extremely fragile across utility formats — MSEDCL's PDF looks nothing like BESCOM's which looks nothing like a UK smart meter bill.
- **API (Green Button / ESPI)**: US standard. Works with PG&E, ConEd, etc. Not supported by Indian utilities (MSEDCL, BESCOM, CESC, etc.). Would cover only a subset of global clients.
- **Portal CSV export (chosen)**: All major Indian utilities (MSEDCL, BESCOM, CESC, TPDDL) and most UK/US utilities offer a "Download consumption data" CSV from their web portal. The facilities team already does this for their own reconciliation. Format is inconsistent but parseable.

**Choice: Portal CSV export.**

**Column mapping approach:** Rather than a rigid schema, we map a list of known aliases for each logical field (meter ID, period start, consumption, etc.) and pick the first match. This handles MSEDCL's "Consumption (kWh)" vs BESCOM's "Units Consumed" vs UK's "kWh" without requiring a per-utility configuration file.

**Billing period alignment:** Indian utility billing periods are 28–35 days and do NOT align with calendar months. We store `activity_date` (period start) and `period_end` on the record and detect/flag anomalous periods. For reporting, we attribute the entire consumption to the month the billing period starts. A more sophisticated approach (proportional allocation across months) is noted in TRADEOFFS.md.

**Scope 2 market-based detection:** If the tariff code contains renewable keywords (green, solar, wind, REC, REGO, GO100), we classify as Scope 2 market-based and set CO₂e to 0 (or a supplier-specific factor). The analyst is expected to verify this. In production, a proper REGo/REGO certificate registry check would be needed.

**What I'd ask the PM:** Does the client have AMI (smart meters) that report at half-hourly intervals? If so, the portal CSV has thousands of rows per meter and we'd need a different aggregation strategy before ingestion.

---

## Travel: Concur vs Navan vs others

**Research:** SAP Concur's "Travel Expense Report" export and Navan's "Travel Report" CSV have similar structures: one row per trip segment (each flight leg, each hotel stay, each car rental day is a separate row). Both platforms let admins pull the data as CSV from their reporting module.

**Column name differences handled:** We map a comprehensive alias list so "Class of Service" (Concur) and "Cabin Class" (Navan) both resolve to `travel_class`.

**Distance calculation:** Many travel platforms don't include distance. When origin and destination IATA codes are given but distance is absent, we calculate great-circle (haversine) distance. This underestimates actual flight path by ~10–15% due to routing, but it's the standard approach (DEFRA methodology notes this). Records with estimated distances are flagged.

**Radiative Forcing (RF):** We apply DEFRA 2023 factors that already include an RF multiplier of 1.891 for flights. Some clients will want factors without RF (for direct GHG Protocol Scope 3 reporting). This should be a per-client configuration — noted as a TODO.

**What I'd ask the PM:**
1. Is the client on Concur or Navan? (Affects expected column names — though our alias map handles both, confirming avoids surprises.)
2. Should we include RF in the flight factors? GHG Protocol Scope 3 standard says CO₂ only; many voluntary frameworks include RF. This is a material difference.
3. Does the client want hotel emissions allocated by region (DEFRA has UK-specific factors; US EPA has US factors) or use the global average?

---

## Emission Factors: Which source?

**Choice: DEFRA 2023 as primary, IEA 2022 for India grid, EPA as fallback.**

Rationale: DEFRA publishes the most comprehensive and regularly updated GHG conversion factors, covering fuel combustion, travel, and hotel stays in a single document. For India-specific grid electricity, IEA's country-level grid intensity (0.716 kgCO₂/kWh for India 2022) is more accurate than DEFRA's UK grid factor.

**Factors are versioned and stored in the DB.** When a client's reporting year is 2023, we use 2023 factors. If 2023 factors are unavailable for an activity, we fall back to the most recent year available. The FK on EmissionRecord freezes the factor used at ingestion time.

**What I'd ask the PM:** Do clients want GHG Protocol Scope 3 Cat 1 factors by ISIC/product category (spend-based EEIO) rather than the flat $0.30/USD we're using? The flat rate is a placeholder; a real deployment needs either USEEIO or Exiobase spend-based factors by material group.

---

## Review workflow: Which statuses?

**Choice: pending → flagged → approved | rejected, plus reset to pending.**

Deliberate decision NOT to have a "draft" or "needs info" status beyond flagged. The complexity of a multi-step workflow (e.g. send back to uploader for clarification) is out of scope for the prototype. Flagging + review note covers the "something's wrong, look at this" case.

**Bulk actions:** Analysts can select N records and approve/flag/reject in one action. This is critical for usability when a batch has 200 straightforward records and 3 flagged ones — the analyst shouldn't have to click through 200 detail pages.

---

## Multi-tenancy: Row-level vs application-level

**Choice: Application-level filtering in every queryset.**

Every ViewSet's `get_queryset()` starts with a `ClientMembership` check and filters `client_id__in=member_ids`. This is implemented consistently and tested. We do NOT use PostgreSQL row-level security (RLS) as a secondary enforcement layer — that's in TRADEOFFS.md.

---

## Deployment: SQLite for dev, PostgreSQL for production

`dj-database-url` reads `DATABASE_URL` from environment. If absent, SQLite is used. On Render, the PostgreSQL service sets this env var automatically. No code changes required between environments.

---

## What I would ask the PM before building phase 2

1. Do clients need a "lock reporting period" action that prevents any further edits once auditors have a copy? (Critical for audit integrity.)
2. Is there a requirement for PCAF, SBTi, or CDP export format, or is CSV sufficient for the auditors?
3. Should re-ingesting a file that overlaps a previously ingested period auto-detect and deduplicate (matching on `source_row_id`), or always create new records?
4. What's the expected volume? 10,000 records/batch changes nothing; 10M records requires async processing (Celery) and pagination strategy changes.
5. Does the client have renewable energy certificates (RECs/REGOs) that need to be matched against their Scope 2 consumption records?
