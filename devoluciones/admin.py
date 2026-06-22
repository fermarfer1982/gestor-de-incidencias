from django.contrib import admin

from core.access import can_delete_records, get_representative_scope_codes, has_global_access
from devoluciones.models import (
    IncidentAttachment,
    Representative,
    ReturnIncident,
    ReturnIncidentLine,
    UserRepresentative,
)


class NoDeleteUnlessSuperuserMixin:
    def has_delete_permission(self, request, obj=None):
        return can_delete_records(request.user)


class ScopedIncidentAdminMixin(NoDeleteUnlessSuperuserMixin):
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if has_global_access(request.user):
            return queryset
        representative_codes = get_representative_scope_codes(request.user)
        return queryset.filter(incident__representative_code__in=representative_codes)


class ReturnIncidentLineInline(admin.TabularInline):
    model = ReturnIncidentLine
    extra = 0

    def has_delete_permission(self, request, obj=None):
        return can_delete_records(request.user)


class IncidentAttachmentInline(admin.TabularInline):
    model = IncidentAttachment
    extra = 0

    def has_delete_permission(self, request, obj=None):
        return can_delete_records(request.user)


@admin.register(Representative)
class RepresentativeAdmin(NoDeleteUnlessSuperuserMixin, admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(UserRepresentative)
class UserRepresentativeAdmin(NoDeleteUnlessSuperuserMixin, admin.ModelAdmin):
    list_display = ("user", "representative", "active")
    list_filter = ("active", "representative")
    search_fields = ("user__username", "user__email", "representative__code", "representative__name")


@admin.register(ReturnIncident)
class ReturnIncidentAdmin(NoDeleteUnlessSuperuserMixin, admin.ModelAdmin):
    list_display = (
        "incident_number",
        "delivery_note_number",
        "customer_name",
        "representative_code",
        "status",
        "total_selected_lines",
        "created_at",
    )
    list_filter = ("status", "representative_code", "created_at")
    search_fields = (
        "incident_number",
        "delivery_note_number",
        "customer_name",
        "representative_code",
        "representative_name",
        "resolution_notes",
    )
    readonly_fields = ("incident_number", "created_at", "created_by", "closed_at", "closed_by")
    fields = (
        "incident_number",
        "created_by",
        "created_at",
        "delivery_note_number",
        "delivery_note_date",
        "customer_name",
        "customer_fiscal_address",
        "representative_code",
        "representative_name",
        "observations",
        "destination",
        "status",
        "resolution_notes",
        "total_selected_lines",
        "closed_at",
        "closed_by",
    )
    inlines = [ReturnIncidentLineInline, IncidentAttachmentInline]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if has_global_access(request.user):
            return queryset
        representative_codes = get_representative_scope_codes(request.user)
        return queryset.filter(representative_code__in=representative_codes)

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ReturnIncidentLine)
class ReturnIncidentLineAdmin(ScopedIncidentAdminMixin, admin.ModelAdmin):
    list_display = (
        "incident",
        "delivery_note_number",
        "delivery_note_line",
        "article_code",
        "quantity_delivery_note",
        "quantity_incident",
        "sale_lot",
    )
    search_fields = ("incident__incident_number", "delivery_note_number", "article_code", "article_description")


@admin.register(IncidentAttachment)
class IncidentAttachmentAdmin(ScopedIncidentAdminMixin, admin.ModelAdmin):
    list_display = ("incident", "file", "uploaded_at", "uploaded_by")
    search_fields = ("incident__incident_number", "file")
