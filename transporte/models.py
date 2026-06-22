from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class TransportIncidentStatus(models.TextChoices):
    PENDING = "pending", "Abierta"
    IN_PROGRESS = "in_progress", "En trámite"
    CLOSED = "closed", "Cerrada"


class TransportCarrier(models.TextChoices):
    MRW = "MRW", "MRW"
    GLS = "GLS", "GLS"
    SEUR = "SEUR", "SEUR"
    DACHSER = "Dachser", "Dachser"
    INTEGRA2 = "Integra2", "Integra2"
    MBE = "MBE", "MBE"
    DHL = "DHL", "DHL"
    CORREOS = "Correos", "Correos"
    CTT = "CTT", "CTT"
    DSV = "DSV", "DSV"


class TransportIncidentType(models.TextChoices):
    LOST_PACKAGE = "lost_package", "Bulto perdido"
    DAMAGED_GOODS = "damaged_goods", "Daños en mercancía"
    DELAY = "delay", "Retraso"
    FAILED_DELIVERY = "failed_delivery", "Entrega fallida"
    OTHER = "other", "Otro"


class TransportShipmentDirection(models.TextChoices):
    SHIPMENT = "shipment", "Envío"
    PICKUP = "pickup", "Recogida"


class TransportIncident(models.Model):
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
        related_name="transport_incidents_created",
        verbose_name="creado por",
    )
    created_at = models.DateTimeField("fecha de creacion", auto_now_add=True)
    has_delivery_note = models.BooleanField("tiene albaran", default=False)
    delivery_note_number = models.CharField("numero de albaran", max_length=50, null=True, blank=True)
    delivery_note_date = models.DateField("fecha de albaran", null=True, blank=True)
    customer_name = models.CharField("cliente", max_length=255, null=True, blank=True)
    representative_code = models.CharField("codigo de representante", max_length=20, null=True, blank=True)
    representative_name = models.CharField("nombre de representante", max_length=255, null=True, blank=True)
    description = models.TextField("descripcion")
    carrier = models.CharField("transportista", max_length=30, choices=TransportCarrier.choices)
    incident_type = models.CharField("tipo de incidencia", max_length=30, choices=TransportIncidentType.choices)
    status = models.CharField(
        "estado",
        max_length=20,
        choices=TransportIncidentStatus.choices,
        default=TransportIncidentStatus.PENDING,
    )
    shipment_direction = models.CharField(
        "envio o recogida",
        max_length=20,
        choices=TransportShipmentDirection.choices,
    )
    tracking_number = models.CharField("numero de seguimiento", max_length=100)
    internal_reference = models.CharField("referencia interna", max_length=100)
    country = models.CharField("pais", max_length=100, default="España")
    province = models.CharField("provincia", max_length=100)
    municipality = models.CharField("municipio", max_length=100)
    sender = models.CharField("remitente", max_length=255)
    recipient = models.CharField("destinatario", max_length=255)
    shipping_date = models.DateField("fecha de envio")
    incident_date = models.DateField("fecha de incidencia")
    resolution_notes = models.TextField("como se ha solucionado", blank=True)
    closed_at = models.DateTimeField("fecha de cierre", null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transport_incidents_closed",
        verbose_name="cerrado por",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "incidencia de transporte"
        verbose_name_plural = "incidencias de transporte"

    def __str__(self):
        return f"{self.incident_number} - {self.get_carrier_display()}"

    def save(self, *args, **kwargs):
        if self.incident_number:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            self.incident_number = self.generate_incident_number()
            return super().save(*args, **kwargs)

    @classmethod
    def generate_incident_number(cls):
        year = timezone.now().year
        prefix = f"TRA-{year}-"
        last_incident = (
            cls.objects.select_for_update()
            .filter(incident_number__startswith=prefix)
            .order_by("-incident_number")
            .first()
        )
        last_sequence = int(last_incident.incident_number.rsplit("-", 1)[-1]) if last_incident else 0
        return f"{prefix}{last_sequence + 1:06d}"


def transport_incident_attachment_upload_to(instance, filename):
    incident_number = instance.incident.incident_number or "sin-numero"
    return f"transport-incidents/{incident_number}/{filename}"


class TransportIncidentAttachment(models.Model):
    incident = models.ForeignKey(
        TransportIncident,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="incidencia",
    )
    file = models.FileField("archivo", upload_to=transport_incident_attachment_upload_to)
    uploaded_at = models.DateTimeField("subido el", auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transport_incident_attachments_uploaded",
        verbose_name="subido por",
    )

    class Meta:
        ordering = ["-uploaded_at", "-id"]
        verbose_name = "adjunto de incidencia de transporte"
        verbose_name_plural = "adjuntos de incidencias de transporte"

    def __str__(self):
        return f"{self.incident.incident_number} - {self.file.name}"
