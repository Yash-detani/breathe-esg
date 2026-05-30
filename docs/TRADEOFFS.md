# TRADEOFFS

Three things I deliberately did not build, and why.

---

## 1. Async ingestion pipeline (Celery + Redis)

**What it would look like:** File upload queues a Celery task. The API returns immediately with a batch ID. The frontend polls or uses WebSockets to show progress. Large files (50,000-row SAP exports) don't block the web worker.

**Why I didn't build it:** For a 4-day prototype evaluated on data model quality and decision reasoning, adding Celery + Redis + a task broker doubles the deployment surface area with no return in evaluation criteria. The current synchronous approach works correctly for files up to a few thousand rows (the realistic size for a quarterly SAP export). The Django request timeout (typically 30s on Render/Railway) is the practical limit.

**What breaks in production:** A 200,000-row SAP annual export would time out. A retry could create duplicate records (we don't have idempotency on re-ingestion yet). The fix is: (1) add Celery with Redis, (2) return `202 Accepted` with a task ID, (3) poll `GET /api/batches/{id}/` which reflects processing status. The model already has `status=processing` for this.

**Estimated effort to add:** 1 day.

---

## 2. Audit period lock / immutability enforcement

**What it would look like:** Once an analyst clicks "Lock period for audit" on a reporting year, all `EmissionRecord` rows for that `(client, reporting_year)` become immutable at the application layer. Any subsequent upload that falls into a locked period is rejected or quarantined for manual review. Auditors receive a signed manifest (hash of all approved records) that they can verify hasn't changed.

**Why I didn't build it:** The review workflow (pending → approved → [locked]) is complete without the lock step for a prototype. The lock is operationally critical — without it, data can change under an auditor after sign-off — but it adds three features at once: (1) a period-lock API endpoint, (2) permission checks on every EmissionRecord mutation, (3) a manifest generation step. The data model is designed for it: `review_status='approved'` and `reviewed_at` are already there; a `reporting_period_locked_at` field on `Client` or a new `ReportingPeriod` model would complete it.

**What breaks without it:** In production, an auditor could sign off on a set of records and a subsequent upload could add or change records in the same reporting year without the auditor being notified. This would be a compliance failure.

**Estimated effort to add:** Half a day for the model + endpoint; one day to add the permission checks everywhere + manifest generation.

---

## 3. Duplicate detection / re-ingestion deduplication

**What it would look like:** When a file is uploaded, the ingestion service checks `source_row_id` against existing records for the same `(client, source_type)`. If a matching `source_row_id` already exists in an approved record, the new row is flagged as a potential duplicate. If it exists in a pending record, the system offers to supersede it. The batch detail view shows which rows were new vs duplicates.

**Why I didn't build it:** This requires defining what "the same record" means across three different source types — which is non-trivial. For SAP, the document number (Belegnummer) is a reliable unique key. For utility, meter ID + billing period is unique. For travel, the booking reference is unique but only if the platform guarantees it (Concur report IDs are not globally unique across exports). Getting this wrong creates silent data quality problems (either missing records or double-counting emissions), which is worse than not having it. The correct approach requires a stakeholder conversation about source-system semantics before implementing.

**What breaks without it:** A user who uploads the same SAP file twice gets double the emissions for that period. The current system would create two sets of records with the same `source_row_id` and flag nothing. An analyst would need to notice the duplicate batch in the Batches view and reject one. This is a UX problem, not a data integrity problem (rejecting records exists), but it's invisible enough that it would catch someone out.

**Estimated effort to add:** 1–2 days, mostly in design decisions about supersede vs flag behaviour, not implementation.
