from django.urls import path

from pedidos.views import (
    OrderDeliveryNoteResultView,
    OrderDeliveryNoteSearchView,
    OrderIncidentCreateView,
    OrderIncidentDetailView,
    OrderIncidentExportView,
    OrderIncidentListView,
    OrderIncidentPDFView,
    OrderIncidentPrintableView,
)

urlpatterns = [
    path("", OrderDeliveryNoteSearchView.as_view(), name="pedidos-index"),
    path("albaran/", OrderDeliveryNoteResultView.as_view(), name="order-delivery-note-result"),
    path("incidencias/nueva/", OrderIncidentCreateView.as_view(), name="order-incident-create"),
    path("incidencias/", OrderIncidentListView.as_view(), name="order-incidents"),
    path("incidencias/export/<str:export_format>/", OrderIncidentExportView.as_view(), name="order-incident-export"),
    path("incidencias/<int:pk>/imprimir/", OrderIncidentPrintableView.as_view(), name="order-incident-print"),
    path("incidencias/<int:pk>/pdf/", OrderIncidentPDFView.as_view(), name="order-incident-pdf"),
    path("incidencias/<int:pk>/", OrderIncidentDetailView.as_view(), name="order-incident-detail"),
]
