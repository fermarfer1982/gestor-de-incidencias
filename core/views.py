from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from core.access import ActiveRepresentativeRequiredMixin, get_representative_scope_codes, has_global_access
from devoluciones.models import ReturnIncident
from pedidos.models import OrderIncident
from transporte.models import TransportIncident


class HomeView(ActiveRepresentativeRequiredMixin, TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        representative_codes = get_representative_scope_codes(self.request.user)
        context["representative"] = None
        incidents = ReturnIncident.objects.all()
        order_incidents = OrderIncident.objects.all()
        transport_incidents = TransportIncident.objects.all()
        if not has_global_access(self.request.user):
            incidents = incidents.filter(representative_code__in=representative_codes)
            order_incidents = order_incidents.filter(representative_code__in=representative_codes)
            transport_incidents = transport_incidents.filter(representative_code__in=representative_codes)
        context["my_incidents_count"] = incidents.count()
        context["order_incidents_count"] = order_incidents.count()
        context["transport_incidents_count"] = transport_incidents.count()
        return context


class AccessDeniedView(LoginRequiredMixin, TemplateView):
    template_name = "core/access_denied.html"
