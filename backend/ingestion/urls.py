from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClientViewSet, IngestionBatchViewSet, EmissionRecordViewSet,
    UploadView, DashboardSummaryView, MeView
)

router = DefaultRouter()
router.register('clients', ClientViewSet, basename='client')
router.register('batches', IngestionBatchViewSet, basename='batch')
router.register('records', EmissionRecordViewSet, basename='record')

urlpatterns = [
    path('', include(router.urls)),
    path('upload/', UploadView.as_view(), name='upload'),
    path('dashboard/', DashboardSummaryView.as_view(), name='dashboard'),
    path('me/', MeView.as_view(), name='me'),
]
