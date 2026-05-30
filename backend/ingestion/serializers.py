from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Client, ClientMembership, IngestionBatch, EmissionRecord,
    EmissionRecordAudit, FailedRow, PlantCode, EmissionFactor
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'name', 'slug', 'active_reporting_year', 'created_at']


class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = ['id', 'activity_type', 'source', 'year', 'factor_kg_co2e_per_unit', 'unit', 'notes']


class IngestionBatchSerializer(serializers.ModelSerializer):
    uploaded_by = UserSerializer(read_only=True)
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = IngestionBatch
        fields = [
            'id', 'client', 'source_type', 'source_type_display',
            'uploaded_by', 'uploaded_at', 'original_filename',
            'total_rows', 'success_rows', 'failed_rows', 'flagged_rows',
            'status', 'status_display', 'error_log',
            'period_start', 'period_end',
        ]


class EmissionRecordAuditSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = EmissionRecordAudit
        fields = ['id', 'action', 'action_display', 'actor', 'timestamp', 'diff', 'note']


class FailedRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = FailedRow
        fields = ['id', 'row_number', 'raw_data', 'error_message', 'created_at']


class EmissionRecordSerializer(serializers.ModelSerializer):
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    review_status_display = serializers.CharField(source='get_review_status_display', read_only=True)
    reviewed_by = UserSerializer(read_only=True)
    emission_factor = EmissionFactorSerializer(read_only=True)
    audit_trail = EmissionRecordAuditSerializer(many=True, read_only=True)
    batch_filename = serializers.CharField(source='batch.original_filename', read_only=True)

    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'client', 'batch', 'batch_filename',
            'source_row_id', 'source_type',
            'scope', 'scope_display', 'scope3_category',
            'activity_type', 'activity_type_display',
            'raw_value', 'raw_unit',
            'canonical_value', 'canonical_unit',
            'co2e_kg', 'emission_factor',
            'activity_date', 'period_end', 'reporting_year',
            'plant_code', 'location_name', 'country',
            'travel_origin', 'travel_destination', 'travel_class', 'traveler_name',
            'distance_km', 'meter_id', 'tariff_code',
            'sap_document_number', 'sap_cost_center', 'sap_material_group',
            'review_status', 'review_status_display',
            'reviewed_by', 'reviewed_at', 'review_note',
            'is_flagged', 'flag_reasons',
            'created_at', 'updated_at',
            'audit_trail',
        ]
        read_only_fields = [
            'id', 'client', 'batch', 'source_row_id', 'source_type',
            'raw_value', 'raw_unit', 'canonical_value', 'canonical_unit',
            'co2e_kg', 'emission_factor', 'reporting_year',
            'created_at', 'updated_at',
        ]


class EmissionRecordListSerializer(serializers.ModelSerializer):
    """Lighter serializer for list views (no audit trail)."""
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    review_status_display = serializers.CharField(source='get_review_status_display', read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()
    batch_filename = serializers.CharField(source='batch.original_filename', read_only=True)

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.get_full_name() or obj.reviewed_by.username
        return None

    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'source_type', 'batch_filename',
            'scope', 'scope_display', 'scope3_category',
            'activity_type', 'activity_type_display',
            'co2e_kg', 'canonical_value', 'canonical_unit',
            'activity_date', 'reporting_year',
            'location_name', 'country',
            'travel_origin', 'travel_destination', 'traveler_name',
            'meter_id',
            'review_status', 'review_status_display',
            'reviewed_by_name', 'reviewed_at',
            'is_flagged', 'flag_reasons',
            'created_at',
        ]


class ReviewActionSerializer(serializers.Serializer):
    """Input for bulk approve/reject/flag actions."""
    record_ids = serializers.ListField(child=serializers.UUIDField())
    action = serializers.ChoiceField(choices=['approve', 'reject', 'flag'])
    note = serializers.CharField(required=False, allow_blank=True, default='')


class UploadSerializer(serializers.Serializer):
    source_type = serializers.ChoiceField(choices=[
        ('sap', 'SAP Export'),
        ('utility', 'Utility Portal'),
        ('travel', 'Corporate Travel'),
    ])
    file = serializers.FileField()
