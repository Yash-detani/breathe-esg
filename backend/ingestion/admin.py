from django.contrib import admin
from .models import (
    Client, ClientMembership, PlantCode, EmissionFactor,
    IngestionBatch, EmissionRecord, EmissionRecordAudit, FailedRow
)

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'active_reporting_year', 'created_at']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(ClientMembership)
class ClientMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'client', 'role']

@admin.register(PlantCode)
class PlantCodeAdmin(admin.ModelAdmin):
    list_display = ['client', 'code', 'name', 'country']

@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ['activity_type', 'source', 'year', 'factor_kg_co2e_per_unit', 'unit']

@admin.register(IngestionBatch)
class IngestionBatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'source_type', 'status', 'uploaded_at',
                    'success_rows', 'failed_rows', 'flagged_rows']
    list_filter = ['status', 'source_type']

@admin.register(EmissionRecord)
class EmissionRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'activity_type', 'scope', 'co2e_kg',
                    'activity_date', 'review_status', 'is_flagged']
    list_filter = ['scope', 'activity_type', 'review_status', 'source_type', 'is_flagged']
    search_fields = ['source_row_id', 'location_name', 'traveler_name']

@admin.register(EmissionRecordAudit)
class EmissionRecordAuditAdmin(admin.ModelAdmin):
    list_display = ['record', 'action', 'actor', 'timestamp']
    list_filter = ['action']

@admin.register(FailedRow)
class FailedRowAdmin(admin.ModelAdmin):
    list_display = ['batch', 'row_number', 'error_message', 'created_at']
