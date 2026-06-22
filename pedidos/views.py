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
from devoluciones.models import Representative
from erp.exceptions import ERPIntegrationError
from erp.services import get_delivery_note_for_representative
from pedidos.forms import (
    DeliveryNoteSearchForm,
    OrderDeliveryNoteSelectionForm,
    OrderIncidentCreateForm,
    OrderIncidentStatusForm,
)
from pedidos.models import OrderIncident, OrderIncidentStatus
from pedidos.services import create_order_incident
from pedidos.session import (
    clear_order_incident_creation_session,
    get_order_delivery_note_data,
    get_order_selected_lines_data,
    store_order_delivery_note,
    store_order_selected_lines,
)


class OrderDeliveryNoteSearchView(ActiveRepresentativeRequiredMixin, FormView):
    form_class = DeliveryNoteSearchForm
    template_name = "pedidos/search.html"

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
            delivery_note = get_delivery_note_for_representative(
                representative.code if representative else None,
                delivery_note_number,
            )
        except Representative.DoesNotExist:
            form.add_error("representative_code", "Debes elegir un representante válido.")
            return self.form_invalid(form)
        except ERPIntegrationError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        if delivery_note is None:
            form.add_error("delivery_note_number", "No se ha encontrado el albarán para el representante indicado.")
            return self.form_invalid(form)

        if representative is None:
            representative = Representative.objects.filter(code=delivery_note.header.representative_code).first()
            if representative is None:
                form.add_error(None, "El albarán pertenece a un representante no configurado en la aplicación.")
                return self.form_invalid(form)

        store_order_delivery_note(self.request, delivery_note, representative)
        messages.success(self.request, "Albarán encontrado.")
        return redirect("order-delivery-note-result")


class OrderDeliveryNoteResultView(ActiveRepresentativeRequiredMixin, FormView):
    form_class = OrderDeliveryNoteSelectionForm
    template_name = "pedidos/result.html"

    def dispatch(self, request, *args, **kwargs):
        self.delivery_note = get_order_delivery_note_data(request)
        if not self.delivery_note:
            messages.error(request, "Primero debes buscar un albarán.")
            return redirect("pedidos-index")
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
                    "note_field": form[f"line_note_{index}"],
                }
            )
        context["line_rows"] = line_rows
        return context

    def form_valid(self, form):
        store_order_selected_lines(self.request, form.cleaned_data["selected_line_items"])
        return redirect("order-incident-create")


class OrderIncidentCreateView(ActiveRepresentativeRequiredMixin, FormView):
    form_class = OrderIncidentCreateForm
    template_name = "pedidos/create_incident.html"

    def dispatch(self, request, *args, **kwargs):
        self.delivery_note = get_order_delivery_note_data(request)
        self.selected_lines = get_order_selected_lines_data(request)
        if not self.delivery_note:
            messages.error(request, "Primero debes buscar un albarán.")
            return redirect("pedidos-index")
        if not self.selected_lines:
            messages.error(request, "Primero debes seleccionar líneas del albarán.")
            return redirect("order-delivery-note-result")
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
            incident = create_order_incident(
                user=self.request.user,
                representative=representative,
                delivery_note=self.delivery_note,
                selected_lines=self.selected_lines,
                general_observations=form.cleaned_data["general_observations"],
                files=files,
            )
        except ValidationError as exc:
            form.add_error(None, exc.message)
            return self.form_invalid(form)
        clear_order_incident_creation_session(self.request)
        messages.success(self.request, f"Incidencia {incident.incident_number} creada correctamente.")
        return redirect("order-incident-detail", pk=incident.pk)


class OrderIncidentDetailView(ActiveRepresentativeRequiredMixin, DetailView):
    model = OrderIncident
    template_name = "pedidos/incident_detail.html"
    context_object_name = "incident"

    def get_queryset(self):
        queryset = OrderIncident.objects.prefetch_related("lines", "attachments").select_related("created_by")
        if has_global_access(self.request.user):
            return queryset
        return queryset.filter(representative_code__in=get_representative_scope_codes(self.request.user))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_form"] = kwargs.get(
            "status_form",
            OrderIncidentStatusForm(
                initial={
                    "status": self.object.status,
                    "resolution_notes": self.object.resolution_notes,
                }
            ),
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = OrderIncidentStatusForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(status_form=form))

        previous_status = self.object.status
        new_status = form.cleaned_data["status"]
        self.object.status = new_status
        self.object.resolution_notes = form.cleaned_data["resolution_notes"]
        update_fields = ["status", "resolution_notes"]

        if new_status == OrderIncidentStatus.CLOSED and previous_status != OrderIncidentStatus.CLOSED:
            self.object.closed_at = timezone.now()
            self.object.closed_by = request.user
            update_fields.extend(["closed_at", "closed_by"])

        self.object.save(update_fields=update_fields)
        messages.success(request, "Estado de la incidencia actualizado correctamente.")
        return redirect("order-incident-detail", pk=self.object.pk)


def _order_incident_print_context(incident):
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
                ("Observaciones generales", incident.general_observations),
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
            "headers": ["Línea", "Artículo", "Descripción", "Cantidad", "Lote de venta", "Nota"],
            "rows": [
                [
                    line.delivery_note_line,
                    line.article_code,
                    line.article_description,
                    printable_value(line.quantity_delivery_note),
                    line.sale_lot,
                    line.line_note,
                ]
                for line in incident.lines.all()
            ],
        }
    ]
    return {
        "title": f"Incidencia de pedido {incident.incident_number}",
        "subtitle": "Vista imprimible",
        "sections": sections,
        "tables": tables,
        "attachments": [attachment.file.name for attachment in incident.attachments.all()],
    }


class OrderIncidentPrintableView(OrderIncidentDetailView):
    template_name = "incidents/printable_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_order_incident_print_context(self.object))
        context["detail_url"] = reverse("order-incident-detail", kwargs={"pk": self.object.pk})
        return context


class OrderIncidentPDFView(OrderIncidentDetailView):
    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = _order_incident_print_context(self.object)
        return build_pdf_response(
            filename=f"{self.object.incident_number}.pdf",
            title=context["title"],
            sections=context["sections"],
            tables=context["tables"],
            attachments=context["attachments"],
        )


class OrderIncidentListView(ActiveRepresentativeRequiredMixin, ListView):
    model = OrderIncident
    template_name = "pedidos/incident_list.html"
    context_object_name = "incidents"
    paginate_by = 20

    def get_queryset(self):
        queryset = OrderIncident.objects.select_related("created_by")
        if not has_global_access(self.request.user):
            queryset = queryset.filter(representative_code__in=get_representative_scope_codes(self.request.user))
        status = self.request.GET.get("status")
        if status in OrderIncidentStatus.values:
            queryset = queryset.filter(status=status)
        return queryset.order_by("-created_at", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_status"] = self.request.GET.get("status", "")
        return context


ORDER_EXPORT_HEADERS = [
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


class OrderIncidentExportView(ActiveRepresentativeRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        queryset = OrderIncidentListView()
        queryset.request = request
        incidents = queryset.get_queryset()
        rows = [
            [
                incident.incident_number,
                "pedidos",
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
            return build_xlsx_response(filename="incidencias_pedidos.xlsx", headers=ORDER_EXPORT_HEADERS, rows=rows)
        return build_csv_response(filename="incidencias_pedidos.csv", headers=ORDER_EXPORT_HEADERS, rows=rows)
