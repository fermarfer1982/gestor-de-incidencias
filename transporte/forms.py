from django import forms

from devoluciones.forms import DeliveryNoteSearchForm, MultipleFileField, MultipleFileInput
from transporte.models import (
    TransportCarrier,
    TransportIncidentStatus,
    TransportIncidentType,
    TransportShipmentDirection,
)


class TransportIncidentCreateForm(forms.Form):
    HAS_DELIVERY_NOTE_CHOICES = [
        ("yes", "Sí, asociar a albarán"),
        ("no", "No, crear sin albarán"),
    ]

    has_delivery_note = forms.ChoiceField(
        label="¿La incidencia lleva albarán?",
        choices=HAS_DELIVERY_NOTE_CHOICES,
        widget=forms.RadioSelect,
    )
    representative_code = forms.ChoiceField(
        label="Representante",
        required=False,
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    description = forms.CharField(
        label="Descripción",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )
    carrier = forms.ChoiceField(
        label="Transportista",
        choices=TransportCarrier.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    incident_type = forms.ChoiceField(
        label="Tipo de incidencia",
        choices=TransportIncidentType.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    shipment_direction = forms.ChoiceField(
        label="Envío / Recogida",
        choices=TransportShipmentDirection.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    tracking_number = forms.CharField(label="Número de seguimiento", widget=forms.TextInput(attrs={"class": "form-control"}))
    internal_reference = forms.CharField(label="Referencia interna", widget=forms.TextInput(attrs={"class": "form-control"}))
    country = forms.CharField(
        label="País",
        initial="España",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    province = forms.CharField(label="Provincia", widget=forms.TextInput(attrs={"class": "form-control"}))
    municipality = forms.CharField(label="Municipio", widget=forms.TextInput(attrs={"class": "form-control"}))
    sender = forms.CharField(label="Remitente", widget=forms.TextInput(attrs={"class": "form-control"}))
    recipient = forms.CharField(label="Destinatario", widget=forms.TextInput(attrs={"class": "form-control"}))
    shipping_date = forms.DateField(
        label="Fecha de envío",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    incident_date = forms.DateField(
        label="Fecha de incidencia",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    attachments = MultipleFileField(
        label="Adjuntos",
        required=False,
        widget=MultipleFileInput(attrs={"class": "form-control"}),
    )

    def __init__(
        self,
        *args,
        can_choose_representative=False,
        representative_choices=None,
        representative_required=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.can_choose_representative = can_choose_representative
        self.representative_required = representative_required
        if can_choose_representative:
            empty_label = "Selecciona un representante" if representative_required else "Sin representante"
            self.fields["representative_code"].choices = [("", empty_label)] + list(representative_choices or [])
        else:
            self.fields.pop("representative_code")

    def clean(self):
        cleaned_data = super().clean()
        has_delivery_note = cleaned_data.get("has_delivery_note") == "yes"
        representative_code = cleaned_data.get("representative_code")
        if not has_delivery_note and self.representative_required and not representative_code:
            self.add_error("representative_code", "Debes elegir un representante.")
        return cleaned_data


class TransportIncidentStatusForm(forms.Form):
    status = forms.ChoiceField(
        label="Estado",
        choices=TransportIncidentStatus.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    resolution_notes = forms.CharField(
        label="Cómo se ha solucionado",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("status") == TransportIncidentStatus.CLOSED and not cleaned_data.get("resolution_notes", "").strip():
            self.add_error("resolution_notes", "Debes indicar cómo se ha solucionado antes de cerrar la incidencia.")
        return cleaned_data
