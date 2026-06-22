from django.contrib import admin

from core.models import UserAccessProfile, UserRepresentativeScope


class UserRepresentativeScopeInline(admin.TabularInline):
    model = UserRepresentativeScope
    extra = 0


@admin.register(UserAccessProfile)
class UserAccessProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "all_representatives", "active")
    list_filter = ("role", "all_representatives", "active")
    search_fields = ("user__username", "user__email")
    inlines = [UserRepresentativeScopeInline]

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(UserRepresentativeScope)
class UserRepresentativeScopeAdmin(admin.ModelAdmin):
    list_display = ("profile", "representative", "active")
    list_filter = ("active", "representative")
    search_fields = (
        "profile__user__username",
        "profile__user__email",
        "representative__code",
        "representative__name",
    )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
