from django.urls import path

from transporte.views import (
    TransportIncidentCreateView,
    TransportIncidentDetailView,
    TransportIncidentExportView,
    TransportIncidentListView,
    TransportIncidentPDFView,
    TransportIncidentPrintableView,
)

urlpatterns = [
    path("", TransportIncidentListView.as_view(), name="transport-incidents"),
    path("export/<str:export_format>/", TransportIncidentExportView.as_view(), name="transport-incident-export"),
    path("nueva/", TransportIncidentCreateView.as_view(), name="transport-incident-create"),
    path("<int:pk>/imprimir/", TransportIncidentPrintableView.as_view(), name="transport-incident-print"),
    path("<int:pk>/pdf/", TransportIncidentPDFView.as_view(), name="transport-incident-pdf"),
    path("<int:pk>/", TransportIncidentDetailView.as_view(), name="transport-incident-detail"),
]
