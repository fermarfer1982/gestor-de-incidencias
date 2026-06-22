from django.conf import settings
from django.db import models


class AccessRole(models.TextChoices):
    COMERCIAL = "comercial", "Comercial"
    ADMINISTRACION = "administracion", "Administración"
    ALMACEN = "almacen", "Almacén"


class UserAccessProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_profile",
        verbose_name="usuario",
    )
    role = models.CharField("rol", max_length=30, choices=AccessRole.choices)
    all_representatives = models.BooleanField("todos los representantes", default=False)
    active = models.BooleanField("activo", default=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "perfil de acceso"
        verbose_name_plural = "perfiles de acceso"

    def __str__(self):
        state = "activo" if self.active else "inactivo"
        return f"{self.user} - {self.get_role_display()} ({state})"


class UserRepresentativeScope(models.Model):
    profile = models.ForeignKey(
        UserAccessProfile,
        on_delete=models.CASCADE,
        related_name="representative_scopes",
        verbose_name="perfil",
    )
    representative = models.ForeignKey(
        "devoluciones.Representative",
        on_delete=models.PROTECT,
        related_name="access_scopes",
        verbose_name="representante",
    )
    active = models.BooleanField("activo", default=True)

    class Meta:
        ordering = ["profile__user__username", "representative__code"]
        unique_together = [("profile", "representative")]
        verbose_name = "alcance de representante"
        verbose_name_plural = "alcances de representantes"

    def __str__(self):
        state = "activo" if self.active else "inactivo"
        return f"{self.profile.user} -> {self.representative.code} ({state})"
