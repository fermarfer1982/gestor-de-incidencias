from django.urls import path

from devoluciones.views import (
    DeliveryNoteResultView,
    DeliveryNoteSearchView,
    MyReturnIncidentListView,
    ReturnIncidentExportView,
    ReturnIncidentCreateView,
    ReturnIncidentDetailView,
    ReturnIncidentPDFView,
    ReturnIncidentPrintableView,
)

urlpatterns = [
    path("", DeliveryNoteSearchView.as_view(), name="devoluciones-index"),
    path("albaran/", DeliveryNoteResultView.as_view(), name="delivery-note-result"),
    path("incidencias/nueva/", ReturnIncidentCreateView.as_view(), name="return-incident-create"),
    path("incidencias/mias/", MyReturnIncidentListView.as_view(), name="my-return-incidents"),
    path("incidencias/export/<str:export_format>/", ReturnIncidentExportView.as_view(), name="return-incident-export"),
    path("incidencias/<int:pk>/imprimir/", ReturnIncidentPrintableView.as_view(), name="return-incident-print"),
    path("incidencias/<int:pk>/pdf/", ReturnIncidentPDFView.as_view(), name="return-incident-pdf"),
    path("incidencias/<int:pk>/", ReturnIncidentDetailView.as_view(), name="return-incident-detail"),
]
