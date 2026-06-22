from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, FormView, ListView, View

from core.access import (
    ActiveRepresentativeRequiredMixin,
    can_access_representative_code,
    get_accessible_representative_code,
    get_representative_scope_codes,
    get_representative_scope_queryset,
    has_global_access,
)
from core.exporting import build_csv_response, build_xlsx_response
from core.printable import build_pdf_response, display_user
from devoluciones.forms import DeliveryNoteSearchForm
from devoluciones.models import Representative
from erp.exceptions import ERPIntegrationError
from erp.services import get_delivery_note_for_representative
from transporte.forms import TransportIncidentCreateForm, TransportIncidentStatusForm
from transporte.models import TransportIncident, TransportIncidentStatus
from transporte.services import create_transport_incident
from transporte.session import (
    clear_transport_delivery_note,
    get_transport_delivery_note_data,
    store_transport_delivery_note,
)


def _scoped_transport_queryset(user, queryset):
    if has_global_access(user):
        return queryset
    representative_codes = get_representative_scope_codes(user)
    return queryset.filter(representative_code__in=representative_codes)


class TransportIncidentCreateView(ActiveRepresentativeRequiredMixin, FormView):
    form_class = TransportIncidentCreateForm
    template_name = "transporte/create_incident.html"

    def can_choose_representative(self):
        return has_global_access(self.request.user) or get_representative_scope_queryset(self.request.user).count() != 1

    def get_representative_choices(self):
        return list(get_representative_scope_queryset(self.request.user).order_by("code").values_list("code", "name"))

    def get_create_form_kwargs(self):
        can_choose_representative = has_global_access(self.request.user) or bool(
            get_representative_scope_codes(self.request.user)
        )
        return {
            "can_choose_representative": can_choose_representative,
            "representative_choices": self.get_representative_choices() if can_choose_representative else [],
            "representative_required": not has_global_access(self.request.user),
        }

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(self.get_create_form_kwargs())
        return kwargs

    def get_search_form(self):
        kwargs = {
            "can_choose_representative": self.can_choose_representative(),
            "representative_required": not has_global_access(self.request.user),
        }
        if kwargs["can_choose_representative"]:
            kwargs["representative_choices"] = self.get_representative_choices()
        return DeliveryNoteSearchForm(prefix="search", **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_form"] = kwargs.get("search_form", self.get_search_form())
        context["delivery_note"] = get_transport_delivery_note_data(self.request)
        representative_code = get_accessible_representative_code(self.request.user)
        context["representative"] = (
            Representative.objects.filter(code=representative_code).first() if representative_code else None
        )
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "search_delivery_note":
            return self.search_delivery_note(request)
        if request.POST.get("action") == "clear_delivery_note":
            clear_transport_delivery_note(request)
            messages.info(request, "Albarán desvinculado de la incidencia.")
            return redirect("transport-incident-create")
        return super().post(request, *args, **kwargs)

    def get_effective_representative_for_search(self, representative_code=None):
        if has_global_access(self.request.user) and not representative_code:
            return None
        if self.can_choose_representative():
            if not can_access_representative_code(self.request.user, representative_code):
                raise Representative.DoesNotExist
            return Representative.objects.get(code=representative_code)
        representative_code = get_accessible_representative_code(self.request.user)
        return Representative.objects.get(code=representative_code)

    def search_delivery_note(self, request):
        form = DeliveryNoteSearchForm(
            request.POST,
            prefix="search",
            can_choose_representative=self.can_choose_representative(),
            representative_choices=self.get_representative_choices() if self.can_choose_representative() else [],
            representative_required=not has_global_access(request.user),
        )
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(search_form=form))

        try:
            representative = self.get_effective_representative_for_search(form.cleaned_data.get("representative_code"))
            delivery_note = get_delivery_note_for_representative(
                representative.code if representative else None,
                form.cleaned_data["delivery_note_number"],
            )
        except Representative.DoesNotExist:
            form.add_error("representative_code", "Debes elegir un representante válido.")
            return self.render_to_response(self.get_context_data(search_form=form))
        except ERPIntegrationError as exc:
            form.add_error(None, str(exc))
            return self.render_to_response(self.get_context_data(search_form=form))

        if delivery_note is None:
            form.add_error("delivery_note_number", "No se ha encontrado el albarán para el representante indicado.")
            return self.render_to_response(self.get_context_data(search_form=form))

        if representative is None:
            representative = Representative.objects.filter(code=delivery_note.header.representative_code).first()
            if representative is None:
                form.add_error(None, "El albarán pertenece a un representante no configurado en la aplicación.")
                return self.render_to_response(self.get_context_data(search_form=form))

        store_transport_delivery_note(request, delivery_note, representative)
        messages.success(request, "Albarán asociado a la incidencia.")
        return redirect("transport-incident-create")

    def get_manual_representative(self, form):
        if form.cleaned_data["has_delivery_note"] == "yes":
            delivery_note = get_transport_delivery_note_data(self.request)
            if not delivery_note:
                raise ValidationError("Debes buscar un albarán antes de crear la incidencia.")
            representative_data = delivery_note["search_representative"]
            if not can_access_representative_code(self.request.user, representative_data["code"]):
                raise PermissionError
            return Representative.objects.get(code=representative_data["code"])

        representative_code = form.cleaned_data.get("representative_code")
        if not representative_code:
            return None
        if not can_access_representative_code(self.request.user, representative_code):
            raise PermissionError
        return Representative.objects.get(code=representative_code)

    def form_valid(self, form):
        try:
            representative = self.get_manual_representative(form)
            incident = create_transport_incident(
                user=self.request.user,
                representative=representative,
                delivery_note=get_transport_delivery_note_data(self.request) if form.cleaned_data["has_delivery_note"] == "yes" else None,
                form_data=form.cleaned_data,
                files=self.request.FILES.getlist("attachments"),
            )
        except PermissionError:
            messages.error(self.request, "No tienes acceso al representante indicado.")
            return redirect("access-denied")
        except (Representative.DoesNotExist, ValidationError) as exc:
            form.add_error(None, str(exc.message if hasattr(exc, "message") else exc))
            return self.form_invalid(form)

        clear_transport_delivery_note(self.request)
        messages.success(self.request, f"Incidencia {incident.incident_number} creada correctamente.")
        return redirect("transport-incident-detail", pk=incident.pk)


class TransportIncidentDetailView(ActiveRepresentativeRequiredMixin, DetailView):
    model = TransportIncident
    template_name = "transporte/incident_detail.html"
    context_object_name = "incident"

    def get_queryset(self):
        queryset = TransportIncident.objects.select_related("created_by", "closed_by").prefetch_related("attachments")
        return _scoped_transport_queryset(self.request.user, queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_form"] = kwargs.get(
            "status_form",
            TransportIncidentStatusForm(
                initial={
                    "status": self.object.status,
                    "resolution_notes": self.object.resolution_notes,
                }
            ),
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = TransportIncidentStatusForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(status_form=form))

        previous_status = self.object.status
        new_status = form.cleaned_data["status"]
        self.object.status = new_status
        self.object.resolution_notes = form.cleaned_data["resolution_notes"]
        update_fields = ["status", "resolution_notes"]
        if new_status == TransportIncidentStatus.CLOSED and previous_status != TransportIncidentStatus.CLOSED:
            self.object.closed_at = timezone.now()
            self.object.closed_by = request.user
            update_fields.extend(["closed_at", "closed_by"])
        self.object.save(update_fields=update_fields)
        messages.success(request, "Estado de la incidencia actualizado correctamente.")
        return redirect("transport-incident-detail", pk=self.object.pk)


def _transport_incident_print_context(incident):
    sections = [
        {
            "title": "Datos generales",
            "rows": [
                ("Número de incidencia", incident.incident_number),
                ("Estado", incident.get_status_display()),
                ("Fecha creación", incident.created_at),
                ("Creador", display_user(incident.created_by)),
                ("Representante", f"{incident.representative_code or '-'} {incident.representative_name or ''}"),
                ("Albarán", incident.delivery_note_number),
                ("Fecha de albarán", incident.delivery_note_date),
                ("Cliente", incident.customer_name),
                ("Descripción", incident.description),
            ],
        },
        {
            "title": "Transporte",
            "rows": [
                ("Transportista", incident.get_carrier_display()),
                ("Tipo de incidencia", incident.get_incident_type_display()),
                ("Envío/Recogida", incident.get_shipment_direction_display()),
                ("Número de seguimiento", incident.tracking_number),
                ("Referencia interna", incident.internal_reference),
                ("País", incident.country),
                ("Provincia", incident.province),
                ("Municipio", incident.municipality),
                ("Remitente", incident.sender),
                ("Destinatario", incident.recipient),
                ("Fecha de envío", incident.shipping_date),
                ("Fecha de incidencia", incident.incident_date),
            ],
        },
        {
            "title": "Resolución y cierre",
            "rows": [
                ("Cómo se ha solucionado", incident.resolution_notes),
                ("Cerrada el", incident.closed_at),
                ("Cerrada por", display_user(incident.closed_by)),
            ],
        },
    ]
    return {
        "title": f"Incidencia de transporte {incident.incident_number}",
        "subtitle": "Vista imprimible",
        "sections": sections,
        "tables": [],
        "attachments": [attachment.file.name for attachment in incident.attachments.all()],
    }


class TransportIncidentPrintableView(TransportIncidentDetailView):
    template_name = "incidents/printable_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_transport_incident_print_context(self.object))
        context["detail_url"] = reverse("transport-incident-detail", kwargs={"pk": self.object.pk})
        return context


class TransportIncidentPDFView(TransportIncidentDetailView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = _transport_incident_print_context(self.object)
        return build_pdf_response(
            filename=f"{self.object.incident_number}.pdf",
            title=context["title"],
            sections=context["sections"],
            tables=context["tables"],
            attachments=context["attachments"],
        )


class TransportIncidentListView(ActiveRepresentativeRequiredMixin, ListView):
    model = TransportIncident
    template_name = "transporte/incident_list.html"
    context_object_name = "incidents"
    paginate_by = 20

    def get_queryset(self):
        queryset = TransportIncident.objects.select_related("created_by")
        queryset = _scoped_transport_queryset(self.request.user, queryset)
        status = self.request.GET.get("status")
        if status in TransportIncidentStatus.values:
            queryset = queryset.filter(status=status)
        return queryset.order_by("-created_at", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_status"] = self.request.GET.get("status", "")
        return context


TRANSPORT_EXPORT_HEADERS = [
    "número de incidencia",
    "módulo",
    "estado",
    "fecha creación",
    "creador",
    "representative_code",
    "representative_name",
    "número de albarán",
    "cliente",
    "resolution_notes",
    "transportista",
    "tipo de incidencia",
    "número de seguimiento",
    "referencia interna",
]


class TransportIncidentExportView(ActiveRepresentativeRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        queryset = TransportIncidentListView()
        queryset.request = request
        incidents = queryset.get_queryset()
        rows = [
            [
                incident.incident_number,
                "transporte",
                incident.get_status_display(),
                incident.created_at,
                incident.created_by.email or incident.created_by.username,
                incident.representative_code,
                incident.representative_name,
                incident.delivery_note_number,
                incident.customer_name,
                incident.resolution_notes,
                incident.get_carrier_display(),
                incident.get_incident_type_display(),
                incident.tracking_number,
                incident.internal_reference,
            ]
            for incident in incidents
        ]
        export_format = kwargs["export_format"]
        if export_format == "xlsx":
            return build_xlsx_response(filename="incidencias_transporte.xlsx", headers=TRANSPORT_EXPORT_HEADERS, rows=rows)
        return build_csv_response(filename="incidencias_transporte.csv", headers=TRANSPORT_EXPORT_HEADERS, rows=rows)
