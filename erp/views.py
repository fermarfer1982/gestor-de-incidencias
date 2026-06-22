from django.views.generic import TemplateView

from core.access import ActiveRepresentativeRequiredMixin


class ErpIndexView(ActiveRepresentativeRequiredMixin, TemplateView):
    template_name = "erp/index.html"
