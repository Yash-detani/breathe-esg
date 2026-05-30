from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import (
    Client, ClientMembership, IngestionBatch, EmissionRecord,
    EmissionRecordAudit, FailedRow
)
from .serializers import (
    ClientSerializer, IngestionBatchSerializer, EmissionRecordSerializer,
    EmissionRecordListSerializer, FailedRowSerializer, ReviewActionSerializer,
    UploadSerializer, UserSerializer
)
from .services import process_upload


class MeView(views.APIView):
    """Current authenticated user info."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        memberships = ClientMembership.objects.filter(user=request.user).select_related('client')
        clients = [{'id': m.client.id, 'name': m.client.name, 'slug': m.client.slug,
                    'role': m.role} for m in memberships]
        return Response({
            'user': UserSerializer(request.user).data,
            'clients': clients,
        })


class ClientViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Users only see clients they're members of
        member_ids = ClientMembership.objects.filter(
            user=self.request.user
        ).values_list('client_id', flat=True)
        return Client.objects.filter(id__in=member_ids)


class IngestionBatchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IngestionBatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        client_id = self.request.query_params.get('client_id')
        qs = IngestionBatch.objects.all()
        if client_id:
            qs = qs.filter(client_id=client_id)
        else:
            member_ids = ClientMembership.objects.filter(
                user=self.request.user
            ).values_list('client_id', flat=True)
            qs = qs.filter(client_id__in=member_ids)
        return qs.select_related('uploaded_by')

    @action(detail=True, methods=['get'])
    def failed_rows(self, request, pk=None):
        batch = self.get_object()
        rows = FailedRow.objects.filter(batch=batch)
        serializer = FailedRowSerializer(rows, many=True)
        return Response(serializer.data)


class UploadView(views.APIView):
    """Handle file upload and trigger ingestion pipeline."""
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        source_type = serializer.validated_data['source_type']
        uploaded_file = serializer.validated_data['file']
        client_id = request.data.get('client_id')

        if not client_id:
            return Response({'error': 'client_id required'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify membership
        try:
            membership = ClientMembership.objects.get(
                user=request.user, client_id=client_id
            )
        except ClientMembership.DoesNotExist:
            return Response({'error': 'Not a member of this client'}, status=status.HTTP_403_FORBIDDEN)

        if membership.role == ClientMembership.ROLE_AUDITOR:
            return Response({'error': 'Auditors cannot upload data'}, status=status.HTTP_403_FORBIDDEN)

        client = membership.client
        file_content = uploaded_file.read()
        filename = uploaded_file.name

        batch = process_upload(client, source_type, file_content, filename, request.user)
        return Response(
            IngestionBatchSerializer(batch).data,
            status=status.HTTP_201_CREATED
        )


class EmissionRecordViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return EmissionRecordListSerializer
        return EmissionRecordSerializer

    def get_queryset(self):
        params = self.request.query_params
        client_id = params.get('client_id')

        # Validate membership
        member_ids = ClientMembership.objects.filter(
            user=self.request.user
        ).values_list('client_id', flat=True)

        qs = EmissionRecord.objects.filter(client_id__in=member_ids)

        if client_id:
            qs = qs.filter(client_id=client_id)

        # Filters
        if params.get('scope'):
            qs = qs.filter(scope=params['scope'])
        if params.get('source_type'):
            qs = qs.filter(source_type=params['source_type'])
        if params.get('review_status'):
            qs = qs.filter(review_status=params['review_status'])
        if params.get('is_flagged'):
            qs = qs.filter(is_flagged=params['is_flagged'].lower() == 'true')
        if params.get('batch_id'):
            qs = qs.filter(batch_id=params['batch_id'])
        if params.get('reporting_year'):
            qs = qs.filter(reporting_year=params['reporting_year'])
        if params.get('search'):
            q = params['search']
            qs = qs.filter(
                Q(location_name__icontains=q) |
                Q(traveler_name__icontains=q) |
                Q(source_row_id__icontains=q) |
                Q(sap_document_number__icontains=q) |
                Q(meter_id__icontains=q)
            )

        return qs.select_related(
            'batch', 'emission_factor', 'reviewed_by', 'plant_code'
        ).prefetch_related('audit_trail__actor')

    @action(detail=False, methods=['post'])
    def bulk_review(self, request):
        """Bulk approve / reject / flag records."""
        serializer = ReviewActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        record_ids = serializer.validated_data['record_ids']
        action_type = serializer.validated_data['action']
        note = serializer.validated_data.get('note', '')

        # Validate access
        member_ids = ClientMembership.objects.filter(
            user=request.user
        ).values_list('client_id', flat=True)

        records = EmissionRecord.objects.filter(
            id__in=record_ids,
            client_id__in=member_ids
        )

        status_map = {
            'approve': EmissionRecord.STATUS_APPROVED,
            'reject': EmissionRecord.STATUS_REJECTED,
            'flag': EmissionRecord.STATUS_FLAGGED,
        }
        audit_map = {
            'approve': EmissionRecordAudit.ACTION_APPROVED,
            'reject': EmissionRecordAudit.ACTION_REJECTED,
            'flag': EmissionRecordAudit.ACTION_FLAGGED,
        }

        now = timezone.now()
        new_status = status_map[action_type]
        audit_action = audit_map[action_type]

        updated = []
        for record in records:
            old_status = record.review_status
            record.review_status = new_status
            record.reviewed_by = request.user
            record.reviewed_at = now
            record.review_note = note
            if action_type == 'flag':
                record.is_flagged = True
            record.save()

            EmissionRecordAudit.objects.create(
                record=record,
                action=audit_action,
                actor=request.user,
                diff={'review_status': {'before': old_status, 'after': new_status}},
                note=note,
            )
            updated.append(str(record.id))

        return Response({'updated': len(updated), 'record_ids': updated})

    @action(detail=True, methods=['patch'])
    def review(self, request, pk=None):
        """Single record review action."""
        record = self.get_object()
        action_type = request.data.get('action')
        note = request.data.get('note', '')

        valid_actions = ['approve', 'reject', 'flag', 'pending']
        if action_type not in valid_actions:
            return Response({'error': f'action must be one of {valid_actions}'},
                          status=status.HTTP_400_BAD_REQUEST)

        status_map = {
            'approve': EmissionRecord.STATUS_APPROVED,
            'reject': EmissionRecord.STATUS_REJECTED,
            'flag': EmissionRecord.STATUS_FLAGGED,
            'pending': EmissionRecord.STATUS_PENDING,
        }
        audit_map = {
            'approve': EmissionRecordAudit.ACTION_APPROVED,
            'reject': EmissionRecordAudit.ACTION_REJECTED,
            'flag': EmissionRecordAudit.ACTION_FLAGGED,
            'pending': EmissionRecordAudit.ACTION_EDITED,
        }

        old_status = record.review_status
        record.review_status = status_map[action_type]
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.review_note = note
        if action_type == 'flag':
            record.is_flagged = True
        record.save()

        EmissionRecordAudit.objects.create(
            record=record,
            action=audit_map[action_type],
            actor=request.user,
            diff={'review_status': {'before': old_status, 'after': record.review_status}},
            note=note,
        )

        return Response(EmissionRecordSerializer(record).data)


class DashboardSummaryView(views.APIView):
    """Aggregated stats for the analyst dashboard."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        client_id = request.query_params.get('client_id')
        year = request.query_params.get('year', timezone.now().year)

        member_ids = ClientMembership.objects.filter(
            user=request.user
        ).values_list('client_id', flat=True)

        qs = EmissionRecord.objects.filter(
            client_id__in=member_ids,
            reporting_year=year,
        )
        if client_id:
            qs = qs.filter(client_id=client_id)

        # Total CO2e by scope
        scope_totals = qs.values('scope').annotate(
            total_co2e=Sum('co2e_kg'),
            count=Count('id'),
        )

        # Review status counts
        status_counts = qs.values('review_status').annotate(count=Count('id'))

        # Source type counts
        source_counts = qs.values('source_type').annotate(
            count=Count('id'),
            total_co2e=Sum('co2e_kg'),
        )

        # Flagged count
        flagged_count = qs.filter(is_flagged=True).count()
        pending_count = qs.filter(review_status=EmissionRecord.STATUS_PENDING).count()
        approved_count = qs.filter(review_status=EmissionRecord.STATUS_APPROVED).count()

        # Recent batches
        recent_batches = IngestionBatch.objects.filter(
            client_id__in=member_ids if not client_id else [client_id]
        ).order_by('-uploaded_at')[:5]

        total_co2e = qs.aggregate(total=Sum('co2e_kg'))['total'] or 0

        return Response({
            'reporting_year': year,
            'total_co2e_kg': float(total_co2e),
            'total_co2e_tonnes': float(total_co2e) / 1000,
            'scope_breakdown': list(scope_totals),
            'status_breakdown': list(status_counts),
            'source_breakdown': list(source_counts),
            'flagged_count': flagged_count,
            'pending_count': pending_count,
            'approved_count': approved_count,
            'total_records': qs.count(),
            'recent_batches': IngestionBatchSerializer(recent_batches, many=True).data,
        })
