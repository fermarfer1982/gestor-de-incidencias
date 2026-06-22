from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class Representative(models.Model):
    code = models.CharField("codigo", max_length=20, unique=True)
    name = models.CharField("nombre", max_length=255)

    class Meta:
        ordering = ["code"]
        verbose_name = "representante"
        verbose_name_plural = "representantes"

    def __str__(self):
        return f"{self.code} - {self.name}"


class UserRepresentative(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="representative_link",
        verbose_name="usuario",
    )
    representative = models.ForeignKey(
        Representative,
        on_delete=models.PROTECT,
        related_name="user_links",
        verbose_name="representante",
    )
    active = models.BooleanField("activo", default=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "usuario-representante"
        verbose_name_plural = "usuarios-representante"

    def __str__(self):
        state = "activo" if self.active else "inactivo"
        return f"{self.user} -> {self.representative.code} ({state})"


class ReturnIncidentStatus(models.TextChoices):
    PENDING = "pending", "Abierta"
    IN_PROGRESS = "in_progress", "En trámite"
    CLOSED = "closed", "Cerrada"


class ReturnIncident(models.Model):
    incident_number = models.CharField(
        "numero de incidencia",
        max_length=20,
        unique=True,
        editable=False,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="return_incidents_created",
        verbose_name="creado por",
    )
    created_at = models.DateTimeField("fecha de creacion", auto_now_add=True)
    delivery_note_number = models.CharField("numero de albaran", max_length=50)
    delivery_note_date = models.DateField("fecha de albaran", null=True, blank=True)
    customer_name = models.CharField("cliente", max_length=255)
    customer_fiscal_address = models.CharField("direccion fiscal", max_length=30, blank=True)
    representative_code = models.CharField("codigo de representante", max_length=20)
    representative_name = models.CharField("nombre de representante", max_length=255)
    observations = models.TextField("observaciones", blank=True)
    destination = models.CharField("destino", max_length=255)
    resolution_notes = models.TextField("como se ha solucionado", blank=True)
    status = models.CharField(
        "estado",
        max_length=20,
        choices=ReturnIncidentStatus.choices,
        default=ReturnIncidentStatus.PENDING,
    )
    total_selected_lines = models.PositiveIntegerField("total de lineas seleccionadas", default=0)
    closed_at = models.DateTimeField("fecha de cierre", null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="return_incidents_closed",
        verbose_name="cerrado por",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "incidencia de devolucion"
        verbose_name_plural = "incidencias de devolucion"

    def __str__(self):
        return f"{self.incident_number} - {self.customer_name}"

    def save(self, *args, **kwargs):
        if self.incident_number:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            self.incident_number = self.generate_incident_number()
            return super().save(*args, **kwargs)

    @classmethod
    def generate_incident_number(cls):
        year = timezone.now().year
        prefix = f"DEV-{year}-"
        last_incident = (
            cls.objects.select_for_update()
            .filter(incident_number__startswith=prefix)
            .order_by("-incident_number")
            .first()
        )

        if last_incident:
            last_sequence = int(last_incident.incident_number.rsplit("-", 1)[-1])
        else:
            last_sequence = 0

        return f"{prefix}{last_sequence + 1:06d}"


class ReturnIncidentLine(models.Model):
    incident = models.ForeignKey(
        ReturnIncident,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="incidencia",
    )
    delivery_note_number = models.CharField("numero de albaran", max_length=50)
    delivery_note_line = models.PositiveIntegerField("linea de albaran")
    article_code = models.CharField("codigo de articulo", max_length=50)
    article_description = models.CharField("descripcion de articulo", max_length=255)
    quantity_delivery_note = models.DecimalField(
        "cantidad albaran",
        max_digits=12,
        decimal_places=2,
    )
    quantity_incident = models.DecimalField(
        "cantidad incidencia",
        max_digits=12,
        decimal_places=2,
    )
    sale_lot = models.CharField("lote de venta", max_length=50, blank=True)

    class Meta:
        ordering = ["incident_id", "delivery_note_line", "id"]
        verbose_name = "linea de incidencia"
        verbose_name_plural = "lineas de incidencia"

    def __str__(self):
        return f"{self.incident.incident_number} - linea {self.delivery_note_line} - {self.article_code}"


def incident_attachment_upload_to(instance, filename):
    incident_number = instance.incident.incident_number or "sin-numero"
    return f"incidents/{incident_number}/{filename}"


class IncidentAttachment(models.Model):
    incident = models.ForeignKey(
        ReturnIncident,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="incidencia",
    )
    file = models.FileField("archivo", upload_to=incident_attachment_upload_to)
    uploaded_at = models.DateTimeField("subido el", auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="incident_attachments_uploaded",
        verbose_name="subido por",
    )

    class Meta:
        ordering = ["-uploaded_at", "-id"]
        verbose_name = "adjunto de incidencia"
        verbose_name_plural = "adjuntos de incidencia"

    def __str__(self):
        return f"{self.incident.incident_number} - {self.file.name}"
