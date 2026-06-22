from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect
from django.urls import reverse

from core.models import UserAccessProfile
from devoluciones.models import UserRepresentative

ROLE_COMERCIAL = "comercial"
ROLE_ADMINISTRACION = "administracion"
ROLE_ALMACEN = "almacen"

GLOBAL_ACCESS_ROLES = {ROLE_ALMACEN}
VALID_ACCESS_ROLES = {ROLE_COMERCIAL, ROLE_ADMINISTRACION, ROLE_ALMACEN}


def get_active_user_representative(user):
    if not user or not user.is_authenticated or not user.email:
        return None

    return (
        UserRepresentative.objects.select_related("representative", "user")
        .filter(user__email__iexact=user.email, active=True)
        .first()
    )


def get_active_representative_code(user):
    user_representative = get_active_user_representative(user)
    if not user_representative:
        return None
    return user_representative.representative.code


def get_active_access_profile(user):
    if not user or not user.is_authenticated:
        return None

    return (
        UserAccessProfile.objects.select_related("user")
        .prefetch_related("representative_scopes__representative")
        .filter(user=user, active=True)
        .first()
    )


def user_has_group(user, group_name):
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name=group_name).exists()


def get_user_role_names(user):
    if not user or not user.is_authenticated:
        return set()
    return set(user.groups.values_list("name", flat=True))


def get_user_access_role(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return "superuser"

    profile = get_active_access_profile(user)
    if not profile:
        return None

    user_roles = get_user_role_names(user)
    if profile.role in user_roles and profile.role in VALID_ACCESS_ROLES:
        return profile.role
    return None


def has_global_access(user):
    role = get_user_access_role(user)
    if role == "superuser" or role in GLOBAL_ACCESS_ROLES:
        return True

    profile = get_active_access_profile(user)
    return bool(
        profile
        and profile.active
        and profile.role == ROLE_ADMINISTRACION
        and profile.all_representatives
    )


def has_global_access_bypass(user):
    return has_global_access(user)


def has_valid_access_role(user):
    if not user or not user.is_authenticated:
        return False
    return get_user_access_role(user) is not None


def can_delete_records(user):
    return bool(user and user.is_authenticated and user.is_superuser)


def get_representative_scope_codes(user):
    if not user or not user.is_authenticated:
        return []
    if has_global_access(user):
        return None

    profile = get_active_access_profile(user)
    if not profile:
        return []

    return list(
        profile.representative_scopes.filter(active=True)
        .select_related("representative")
        .values_list("representative__code", flat=True)
    )


def get_representative_scope_queryset(user):
    from devoluciones.models import Representative

    if not user or not user.is_authenticated:
        return Representative.objects.none()
    if has_global_access(user):
        return Representative.objects.all()

    codes = get_representative_scope_codes(user)
    return Representative.objects.filter(code__in=codes)


def get_accessible_representative_code(user):
    if has_global_access(user):
        return None
    codes = get_representative_scope_codes(user)
    if len(codes) == 1:
        return codes[0]
    return None


def can_access_representative_code(user, representative_code):
    if has_global_access(user):
        return True
    codes = get_representative_scope_codes(user)
    return str(representative_code) in {str(code) for code in codes}


class ActiveRepresentativeRequiredMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        self.access_role = get_user_access_role(request.user)
        if not self.access_role:
            return redirect(reverse("access-denied"))

        self.access_profile = get_active_access_profile(request.user)

        if has_global_access(request.user):
            self.user_representative = None
            return super().dispatch(request, *args, **kwargs)

        representative_codes = get_representative_scope_codes(request.user)
        if not representative_codes:
            return redirect(reverse("access-denied"))

        self.user_representative = None
        return super().dispatch(request, *args, **kwargs)
