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
from core.printable import build_pdf_response, display_user, printable_value
from erp.exceptions import ERPIntegrationError
from erp.services import get_delivery_note_for_representative

from devoluciones.forms import (
    DeliveryNoteSearchForm,
    DeliveryNoteSelectionForm,
    ReturnIncidentCreateForm,
    ReturnIncidentStatusForm,
)
from devoluciones.models import Representative, ReturnIncident, ReturnIncidentStatus
from devoluciones.services import create_return_incident
from devoluciones.session import (
    clear_incident_creation_session,
    get_delivery_note_data,
    get_selected_lines_data,
    store_delivery_note,
    store_selected_lines,
)


class DeliveryNoteSearchView(ActiveRepresentativeRequiredMixin, FormView):
    form_class = DeliveryNoteSearchForm
    template_name = "devoluciones/search.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["can_choose_representative"] = self.can_choose_representative()
        kwargs["representative_required"] = not has_global_access(self.request.user)
        if kwargs["can_choose_representative"]:
            kwargs["representative_choices"] = list(
                get_representative_scope_queryset(self.request.user).order_by("code").values_list("code", "name")
            )
        return kwargs

    def can_choose_representative(self):
        return has_global_access(self.request.user) or get_representative_scope_queryset(self.request.user).count() != 1

    def get_effective_representative(self, representative_code=None):
        if has_global_access(self.request.user) and not representative_code:
            return None
        if self.can_choose_representative():
            if not can_access_representative_code(self.request.user, representative_code):
                raise Representative.DoesNotExist
            return Representative.objects.get(code=representative_code)
        representative_code = get_accessible_representative_code(self.request.user)
        return Representative.objects.get(code=representative_code)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        representative = None
        representative_code = get_accessible_representative_code(self.request.user)
        if representative_code:
            representative = Representative.objects.filter(code=representative_code).first()
        context["representative"] = representative
        context["can_choose_representative"] = self.can_choose_representative()
        return context

    def form_valid(self, form):
        delivery_note_number = form.cleaned_data["delivery_note_number"]
        try:
            representative = self.get_effective_representative(form.cleaned_data.get("representative_code"))
            self.delivery_note = get_delivery_note_for_representative(
                representative.code if representative else None,
                delivery_note_number,
            )
        except Representative.DoesNotExist:
            form.add_error("representative_code", "Debes elegir un representante válido.")
            return self.form_invalid(form)
        except ERPIntegrationError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        if self.delivery_note is None:
            form.add_error("delivery_note_number", "No se ha encontrado el albarán para el representante indicado.")
            return self.form_invalid(form)

        if representative is None:
            representative = Representative.objects.filter(code=self.delivery_note.header.representative_code).first()
            if representative is None:
                form.add_error(None, "El albarán pertenece a un representante no configurado en la aplicación.")
                return self.form_invalid(form)

        store_delivery_note(self.request, self.delivery_note, representative)
        messages.success(self.request, "Albarán encontrado.")
        return redirect("delivery-note-result")


class DeliveryNoteResultView(ActiveRepresentativeRequiredMixin, FormView):
    form_class = DeliveryNoteSelectionForm
    template_name = "devoluciones/result.html"

    def dispatch(self, request, *args, **kwargs):
        self.delivery_note = get_delivery_note_data(request)
        if not self.delivery_note:
            messages.error(request, "Primero debes buscar un albarán.")
            return redirect("devoluciones-index")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["delivery_note"] = self.delivery_note
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["delivery_note"] = self.delivery_note
        context["representative"] = self.delivery_note.get("search_representative")
        form = context["form"]
        checkbox_widgets = list(form["selected_lines"])
        line_rows = []
        for index, line in enumerate(self.delivery_note["lines"]):
            line_rows.append(
                {
                    "checkbox": checkbox_widgets[index],
                    "line": line,
                    "quantity_field": form[f"quantity_incident_{index}"],
                }
            )
        context["line_rows"] = line_rows
        return context

    def form_valid(self, form):
        store_selected_lines(self.request, form.cleaned_data["selected_line_items"])
        return redirect("return-incident-create")


class ReturnIncidentCreateView(ActiveRepresentativeRequiredMixin, FormView):
    form_class = ReturnIncidentCreateForm
    template_name = "devoluciones/create_incident.html"

    def dispatch(self, request, *args, **kwargs):
        self.delivery_note = get_delivery_note_data(request)
        self.selected_lines = get_selected_lines_data(request)
        if not self.delivery_note:
            messages.error(request, "Primero debes buscar un albarán.")
            return redirect("devoluciones-index")
        if not self.selected_lines:
            messages.error(request, "Primero debes seleccionar líneas del albarán.")
            return redirect("delivery-note-result")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["delivery_note"] = self.delivery_note
        context["selected_lines"] = self.selected_lines
        context["representative"] = self.delivery_note.get("search_representative")
        return context

    def form_valid(self, form):
        files = self.request.FILES.getlist("attachments")
        representative_data = self.delivery_note["search_representative"]
        if not can_access_representative_code(self.request.user, representative_data["code"]):
            messages.error(self.request, "No tienes acceso al representante de este albarán.")
            return redirect("access-denied")
        representative = Representative.objects.get(code=representative_data["code"])
        try:
            incident = create_return_incident(
                user=self.request.user,
                representative=representative,
                delivery_note=self.delivery_note,
                selected_lines=self.selected_lines,
                observations=form.cleaned_data["observations"],
                destination=form.cleaned_data["destination"],
                files=files,
            )
        except ValidationError as exc:
            form.add_error(None, exc.message)
            return self.form_invalid(form)
        clear_incident_creation_session(self.request)
        messages.success(self.request, f"Incidencia {incident.incident_number} creada correctamente.")
        return redirect("return-incident-detail", pk=incident.pk)


class ReturnIncidentDetailView(ActiveRepresentativeRequiredMixin, DetailView):
    model = ReturnIncident
    template_name = "devoluciones/incident_detail.html"
    context_object_name = "incident"

    def get_queryset(self):
        queryset = ReturnIncident.objects.prefetch_related("lines", "attachments").select_related("created_by")
        if has_global_access(self.request.user):
            return queryset
        return queryset.filter(representative_code__in=get_representative_scope_codes(self.request.user))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_form"] = kwargs.get(
            "status_form",
            ReturnIncidentStatusForm(
                initial={
                    "status": self.object.status,
                    "resolution_notes": self.object.resolution_notes,
                }
            ),
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = ReturnIncidentStatusForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(status_form=form))

        previous_status = self.object.status
        new_status = form.cleaned_data["status"]
        self.object.status = new_status
        self.object.resolution_notes = form.cleaned_data["resolution_notes"]
        update_fields = ["status", "resolution_notes"]

        if new_status == ReturnIncidentStatus.CLOSED and previous_status != ReturnIncidentStatus.CLOSED:
            self.object.closed_at = timezone.now()
            self.object.closed_by = request.user
            update_fields.extend(["closed_at", "closed_by"])

        self.object.save(update_fields=update_fields)
        messages.success(request, "Estado de la incidencia actualizado correctamente.")
        return redirect("return-incident-detail", pk=self.object.pk)


def _return_incident_print_context(incident):
    sections = [
        {
            "title": "Datos generales",
            "rows": [
                ("Número de incidencia", incident.incident_number),
                ("Estado", incident.get_status_display()),
                ("Fecha creación", incident.created_at),
                ("Creador", display_user(incident.created_by)),
                ("Representante", f"{incident.representative_code} - {incident.representative_name}"),
                ("Albarán", incident.delivery_note_number),
                ("Fecha de albarán", incident.delivery_note_date),
                ("Cliente", incident.customer_name),
                ("Enviado a", incident.customer_fiscal_address),
                ("Destino", incident.destination),
                ("Observaciones", incident.observations),
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
    tables = [
        {
            "title": "Líneas",
            "headers": ["Línea", "Artículo", "Descripción", "Cantidad", "Cantidad incidencia", "Lote de venta"],
            "rows": [
                [
                    line.delivery_note_line,
                    line.article_code,
                    line.article_description,
                    printable_value(line.quantity_delivery_note),
                    printable_value(line.quantity_incident),
                    line.sale_lot,
                ]
                for line in incident.lines.all()
            ],
        }
    ]
    return {
        "title": f"Incidencia de devolución {incident.incident_number}",
        "subtitle": "Vista imprimible",
        "sections": sections,
        "tables": tables,
        "attachments": [attachment.file.name for attachment in incident.attachments.all()],
    }


class ReturnIncidentPrintableView(ReturnIncidentDetailView):
    template_name = "incidents/printable_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_return_incident_print_context(self.object))
        context["detail_url"] = reverse("return-incident-detail", kwargs={"pk": self.object.pk})
        return context


class ReturnIncidentPDFView(ReturnIncidentDetailView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = _return_incident_print_context(self.object)
        return build_pdf_response(
            filename=f"{self.object.incident_number}.pdf",
            title=context["title"],
            sections=context["sections"],
            tables=context["tables"],
            attachments=context["attachments"],
        )


class MyReturnIncidentListView(ActiveRepresentativeRequiredMixin, ListView):
    model = ReturnIncident
    template_name = "devoluciones/incident_list.html"
    context_object_name = "incidents"
    paginate_by = 20

    def get_queryset(self):
        queryset = ReturnIncident.objects.select_related("created_by")
        if not has_global_access(self.request.user):
            queryset = queryset.filter(representative_code__in=get_representative_scope_codes(self.request.user))
        status = self.request.GET.get("status")
        if status in ReturnIncidentStatus.values:
            queryset = queryset.filter(status=status)
        return queryset.order_by("-created_at", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_status"] = self.request.GET.get("status", "")
        return context


RETURN_EXPORT_HEADERS = [
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
]


class ReturnIncidentExportView(ActiveRepresentativeRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        queryset = MyReturnIncidentListView()
        queryset.request = request
        incidents = queryset.get_queryset()
        rows = [
            [
                incident.incident_number,
                "devoluciones",
                incident.get_status_display(),
                incident.created_at,
                incident.created_by.email or incident.created_by.username,
                incident.representative_code,
                incident.representative_name,
                incident.delivery_note_number,
                incident.customer_name,
                incident.resolution_notes,
            ]
            for incident in incidents
        ]
        export_format = kwargs["export_format"]
        if export_format == "xlsx":
            return build_xlsx_response(filename="incidencias_devoluciones.xlsx", headers=RETURN_EXPORT_HEADERS, rows=rows)
        return build_csv_response(filename="incidencias_devoluciones.csv", headers=RETURN_EXPORT_HEADERS, rows=rows)
