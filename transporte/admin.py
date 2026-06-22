from django.contrib import admin

from core.access import can_delete_records, get_representative_scope_codes, has_global_access
from transporte.models import TransportIncident, TransportIncidentAttachment


class NoDeleteUnlessSuperuserMixin:
    def has_delete_permission(self, request, obj=None):
        return can_delete_records(request.user)


class TransportIncidentAttachmentInline(admin.TabularInline):
    model = TransportIncidentAttachment
    extra = 0

    def has_delete_permission(self, request, obj=None):
        return can_delete_records(request.user)


@admin.register(TransportIncident)
class TransportIncidentAdmin(NoDeleteUnlessSuperuserMixin, admin.ModelAdmin):
    list_display = (
        "incident_number",
        "carrier",
        "incident_type",
        "representative_code",
        "status",
        "has_delivery_note",
        "created_at",
    )
    list_filter = ("status", "carrier", "incident_type", "representative_code", "created_at")
    search_fields = (
        "incident_number",
        "delivery_note_number",
        "customer_name",
        "representative_code",
        "tracking_number",
        "internal_reference",
        "sender",
        "recipient",
        "resolution_notes",
    )
    readonly_fields = ("incident_number", "created_at", "created_by", "closed_at", "closed_by")
    inlines = [TransportIncidentAttachmentInline]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if has_global_access(request.user):
            return queryset
        return queryset.filter(representative_code__in=get_representative_scope_codes(request.user))

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(TransportIncidentAttachment)
class TransportIncidentAttachmentAdmin(NoDeleteUnlessSuperuserMixin, admin.ModelAdmin):
    list_display = ("incident", "file", "uploaded_at", "uploaded_by")
    search_fields = ("incident__incident_number", "file")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if has_global_access(request.user):
            return queryset
        return queryset.filter(incident__representative_code__in=get_representative_scope_codes(request.user))
