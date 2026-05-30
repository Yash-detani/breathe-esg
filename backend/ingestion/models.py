"""
Data models for Breathe ESG ingestion platform.

Design principles:
- Multi-tenant from the ground up (every row scoped to a Client)
- Source-of-truth provenance on every emission record
- Immutable audit trail via EmissionRecordAudit
- Unit normalization to canonical units at ingestion time, raw value preserved
- Scope 1/2/3 classification per GHG Protocol
- Review workflow: PENDING → FLAGGED → APPROVED or REJECTED
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


# ---------------------------------------------------------------------------
# Tenant / Client
# ---------------------------------------------------------------------------

class Client(models.Model):
    """
    Top-level tenant. All data is scoped here.
    In a real deployment, users would be assigned to one or more clients
    via ClientMembership. For the prototype, we scope via FK.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    # Reporting year the client is currently working on
    active_reporting_year = models.IntegerField(default=2024)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ClientMembership(models.Model):
    """Links Django users to clients with a role."""
    ROLE_ANALYST = 'analyst'
    ROLE_ADMIN = 'admin'
    ROLE_AUDITOR = 'auditor'
    ROLE_CHOICES = [
        (ROLE_ANALYST, 'Analyst'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_AUDITOR, 'Auditor (read-only)'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ANALYST)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'client')

    def __str__(self):
        return f"{self.user.username} → {self.client.name} ({self.role})"


# ---------------------------------------------------------------------------
# Reference / Lookup tables
# ---------------------------------------------------------------------------

class PlantCode(models.Model):
    """
    SAP plant codes are opaque identifiers (e.g. "1000", "DE01").
    This table maps them to human-readable names and locations.
    Without this, a plant code on an emission record means nothing.
    """
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='plant_codes')
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    country = models.CharField(max_length=2, help_text='ISO 3166-1 alpha-2')
    region = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ('client', 'code')

    def __str__(self):
        return f"{self.code} – {self.name}"


class EmissionFactor(models.Model):
    """
    Emission factors used to convert activity data to CO2e.
    Factors change by year and source (IPCC, DEFRA, EPA, IEA grid factors).
    We store the factor used so records are reproducible even if factors update.
    """
    SOURCE_IPCC = 'ipcc'
    SOURCE_DEFRA = 'defra'
    SOURCE_EPA = 'epa'
    SOURCE_IEA = 'iea'
    SOURCE_CUSTOM = 'custom'
    SOURCE_CHOICES = [
        (SOURCE_IPCC, 'IPCC AR6'),
        (SOURCE_DEFRA, 'DEFRA UK'),
        (SOURCE_EPA, 'US EPA'),
        (SOURCE_IEA, 'IEA Grid'),
        (SOURCE_CUSTOM, 'Custom'),
    ]

    activity_type = models.CharField(max_length=100, help_text='e.g. diesel_combustion, grid_electricity_IN')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    year = models.IntegerField()
    # kg CO2e per unit of activity
    factor_kg_co2e_per_unit = models.DecimalField(max_digits=20, decimal_places=8)
    unit = models.CharField(max_length=50, help_text='Unit of activity (e.g. litre, kWh, km)')
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('activity_type', 'source', 'year')

    def __str__(self):
        return f"{self.activity_type} [{self.source} {self.year}] = {self.factor_kg_co2e_per_unit} kgCO2e/{self.unit}"


# ---------------------------------------------------------------------------
# Ingestion Batch (provenance / source-of-truth tracking)
# ---------------------------------------------------------------------------

class IngestionBatch(models.Model):
    """
    Every upload or pull is a batch. Emission records point back here.
    This answers: "Where did this row come from, when was it ingested,
    who uploaded it, and what was the raw file?"

    A record edited post-ingestion retains its original batch reference
    but gets an audit trail entry. The batch is never mutated.
    """
    SOURCE_SAP = 'sap'
    SOURCE_UTILITY = 'utility'
    SOURCE_TRAVEL = 'travel'
    SOURCE_CHOICES = [
        (SOURCE_SAP, 'SAP Export'),
        (SOURCE_UTILITY, 'Utility Portal'),
        (SOURCE_TRAVEL, 'Corporate Travel'),
    ]

    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETE = 'complete'
    STATUS_FAILED = 'failed'
    STATUS_PARTIAL = 'partial'
    STATUS_CHOICES = [
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETE, 'Complete'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_PARTIAL, 'Partial (some rows failed)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='batches')
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # Store original filename and raw file for full provenance
    original_filename = models.CharField(max_length=500, blank=True)
    raw_file = models.FileField(upload_to='raw_uploads/%Y/%m/', blank=True, null=True)
    # Counts populated after processing
    total_rows = models.IntegerField(default=0)
    success_rows = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    flagged_rows = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PROCESSING)
    error_log = models.JSONField(default=list, help_text='List of per-row parsing errors')
    # Reporting period this batch covers (used for dedup / overlap detection)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_source_type_display()} batch {self.id} for {self.client.name}"


# ---------------------------------------------------------------------------
# Emission Record (the normalized, canonical row)
# ---------------------------------------------------------------------------

class EmissionRecord(models.Model):
    """
    The central fact table. One row = one discrete emission-generating activity
    after normalization.

    Key design decisions:
    - raw_value / raw_unit preserved alongside canonical_value / canonical_unit
      so we can always re-derive or audit unit conversion
    - scope is mandatory and set at ingestion
    - co2e_kg is calculated using the emission_factor at ingestion time; the
      factor FK is stored so recalculation is possible if the factor is revised
    - review_status drives the analyst workflow
    - source_row_id is the identifier in the original source file (e.g. SAP
      document number, utility meter ID + billing period)
    """

    # Scope per GHG Protocol
    SCOPE_1 = '1'
    SCOPE_2_LOCATION = '2_location'
    SCOPE_2_MARKET = '2_market'
    SCOPE_3 = '3'
    SCOPE_CHOICES = [
        (SCOPE_1, 'Scope 1 – Direct'),
        (SCOPE_2_LOCATION, 'Scope 2 – Location-based'),
        (SCOPE_2_MARKET, 'Scope 2 – Market-based'),
        (SCOPE_3, 'Scope 3 – Value chain'),
    ]

    # Scope 3 categories (GHG Protocol)
    SCOPE3_CAT_1 = 'cat1_purchased_goods'
    SCOPE3_CAT_4 = 'cat4_upstream_transport'
    SCOPE3_CAT_6 = 'cat6_business_travel'
    SCOPE3_CAT_7 = 'cat7_employee_commuting'
    SCOPE3_NONE = ''
    SCOPE3_CHOICES = [
        (SCOPE3_NONE, 'N/A'),
        (SCOPE3_CAT_1, 'Cat 1: Purchased goods & services'),
        (SCOPE3_CAT_4, 'Cat 4: Upstream transport'),
        (SCOPE3_CAT_6, 'Cat 6: Business travel'),
        (SCOPE3_CAT_7, 'Cat 7: Employee commuting'),
    ]

    # Review workflow states
    STATUS_PENDING = 'pending'
    STATUS_FLAGGED = 'flagged'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_FLAGGED, 'Flagged – Needs Attention'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    # Activity categories (drives emission factor lookup)
    ACTIVITY_DIESEL = 'diesel_combustion'
    ACTIVITY_PETROL = 'petrol_combustion'
    ACTIVITY_NATURAL_GAS = 'natural_gas_combustion'
    ACTIVITY_GRID_ELECTRICITY = 'grid_electricity'
    ACTIVITY_FLIGHT = 'flight'
    ACTIVITY_HOTEL = 'hotel_stay'
    ACTIVITY_CAR_RENTAL = 'car_rental'
    ACTIVITY_RAIL = 'rail_travel'
    ACTIVITY_PROCUREMENT = 'procurement_spend'
    ACTIVITY_CHOICES = [
        (ACTIVITY_DIESEL, 'Diesel combustion'),
        (ACTIVITY_PETROL, 'Petrol combustion'),
        (ACTIVITY_NATURAL_GAS, 'Natural gas combustion'),
        (ACTIVITY_GRID_ELECTRICITY, 'Grid electricity consumption'),
        (ACTIVITY_FLIGHT, 'Flight'),
        (ACTIVITY_HOTEL, 'Hotel stay'),
        (ACTIVITY_CAR_RENTAL, 'Car rental'),
        (ACTIVITY_RAIL, 'Rail travel'),
        (ACTIVITY_PROCUREMENT, 'Procurement spend'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='emission_records')
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='records')

    # Provenance
    source_row_id = models.CharField(max_length=255, blank=True,
        help_text='Identifier in source system (SAP doc number, meter+period, booking ref)')
    source_type = models.CharField(max_length=20, choices=IngestionBatch.SOURCE_CHOICES)

    # Classification
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    scope3_category = models.CharField(max_length=50, choices=SCOPE3_CHOICES, blank=True, default='')
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_CHOICES)

    # Activity data – raw (as received from source)
    raw_value = models.DecimalField(max_digits=20, decimal_places=4)
    raw_unit = models.CharField(max_length=50)

    # Activity data – canonical (normalized)
    # Canonical units: energy → kWh, volume → litres, distance → km, mass → kg, money → USD
    canonical_value = models.DecimalField(max_digits=20, decimal_places=4)
    canonical_unit = models.CharField(max_length=50)

    # Emissions
    co2e_kg = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    emission_factor = models.ForeignKey(EmissionFactor, on_delete=models.SET_NULL,
        null=True, blank=True, help_text='Factor used to calculate co2e_kg')

    # Temporal
    activity_date = models.DateField(help_text='Date the activity occurred or billing period start')
    period_end = models.DateField(null=True, blank=True,
        help_text='End of billing period if activity spans a range')
    reporting_year = models.IntegerField()

    # Location / facility
    plant_code = models.ForeignKey(PlantCode, on_delete=models.SET_NULL, null=True, blank=True)
    location_name = models.CharField(max_length=255, blank=True,
        help_text='Human-readable location if no plant code')
    country = models.CharField(max_length=2, blank=True, help_text='ISO alpha-2')

    # Travel-specific metadata (null for non-travel)
    travel_origin = models.CharField(max_length=10, blank=True, help_text='IATA airport/city code')
    travel_destination = models.CharField(max_length=10, blank=True)
    travel_class = models.CharField(max_length=20, blank=True,
        help_text='economy / business / first (affects flight emission factor)')
    traveler_name = models.CharField(max_length=255, blank=True)
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Calculated or provided distance for travel records')

    # Utility-specific metadata
    meter_id = models.CharField(max_length=100, blank=True)
    tariff_code = models.CharField(max_length=100, blank=True)

    # SAP-specific metadata
    sap_document_number = models.CharField(max_length=50, blank=True)
    sap_cost_center = models.CharField(max_length=20, blank=True)
    sap_material_group = models.CharField(max_length=50, blank=True)

    # Review workflow
    review_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_records')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    # Anomaly / QA flags (populated by ingestion pipeline)
    is_flagged = models.BooleanField(default=False)
    flag_reasons = models.JSONField(default=list,
        help_text='List of strings describing why this record was auto-flagged')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-activity_date']
        indexes = [
            models.Index(fields=['client', 'reporting_year', 'scope']),
            models.Index(fields=['client', 'review_status']),
            models.Index(fields=['batch']),
        ]

    def __str__(self):
        return f"{self.get_activity_type_display()} | {self.activity_date} | {self.co2e_kg} kgCO2e"


# ---------------------------------------------------------------------------
# Audit Trail
# ---------------------------------------------------------------------------

class EmissionRecordAudit(models.Model):
    """
    Append-only audit log for any change to an EmissionRecord.
    We never update audit rows; each change produces a new entry.

    Stores a snapshot of changed fields (before/after) and the actor.
    This satisfies auditors who need to know: who changed what and when.
    """
    ACTION_CREATED = 'created'
    ACTION_EDITED = 'edited'
    ACTION_APPROVED = 'approved'
    ACTION_REJECTED = 'rejected'
    ACTION_FLAGGED = 'flagged'
    ACTION_CHOICES = [
        (ACTION_CREATED, 'Created'),
        (ACTION_EDITED, 'Edited'),
        (ACTION_APPROVED, 'Approved'),
        (ACTION_REJECTED, 'Rejected'),
        (ACTION_FLAGGED, 'Flagged'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE, related_name='audit_trail')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    # JSON diff: {"field_name": {"before": ..., "after": ...}}
    diff = models.JSONField(default=dict)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.action} on {self.record_id} by {self.actor} at {self.timestamp}"


# ---------------------------------------------------------------------------
# Failed Row (parse failures land here, not silently discarded)
# ---------------------------------------------------------------------------

class FailedRow(models.Model):
    """
    When a row from an ingestion batch cannot be parsed or normalized,
    it lands here instead of being silently dropped.
    Analysts can inspect failures and decide whether to fix and re-ingest
    or mark as irrelevant.
    """
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='failed_row_items')
    row_number = models.IntegerField()
    raw_data = models.JSONField(help_text='The raw row as parsed from the source file')
    error_message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['row_number']

    def __str__(self):
        return f"Failed row {self.row_number} in batch {self.batch_id}"
