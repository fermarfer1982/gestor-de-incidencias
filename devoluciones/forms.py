from django import forms
from django.core.exceptions import ValidationError
from decimal import Decimal

from devoluciones.models import ReturnIncidentStatus


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return [single_file_clean(data, initial)]


class DeliveryNoteSearchForm(forms.Form):
    delivery_note_number = forms.CharField(
        label="Número de albarán",
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Introduce el número de albarán",
            }
        ),
    )
    representative_code = forms.ChoiceField(
        label="Representante",
        required=False,
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(
        self,
        *args,
        can_choose_representative=False,
        representative_choices=None,
        representative_required=True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.can_choose_representative = can_choose_representative
        self.representative_required = representative_required
        if can_choose_representative:
            empty_label = "Selecciona un representante" if representative_required else "Todos los representantes"
            self.fields["representative_code"].choices = [("", empty_label)] + list(
                representative_choices or []
            )
        else:
            self.fields.pop("representative_code")

    def clean(self):
        cleaned_data = super().clean()
        if (
            self.can_choose_representative
            and self.representative_required
            and not cleaned_data.get("representative_code")
        ):
            self.add_error("representative_code", "Debes elegir un representante.")
        return cleaned_data


class DeliveryNoteSelectionForm(forms.Form):
    selected_lines = forms.MultipleChoiceField(
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label="Líneas seleccionadas",
    )

    def __init__(self, *args, delivery_note=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.delivery_note = delivery_note or {"lines": []}
        choices = []
        for index, line in enumerate(self.delivery_note["lines"]):
            label = f"Línea {line['delivery_note_line']} · {line['article_code']} · {line['article_description']}"
            choices.append((str(index), label))
            self.fields[f"quantity_incident_{index}"] = forms.DecimalField(
                required=False,
                min_value=0,
                max_digits=12,
                decimal_places=2,
                label=f"Cantidad incidencia línea {line['delivery_note_line']}",
                widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            )
        self.fields["selected_lines"].choices = choices

    def clean(self):
        cleaned_data = super().clean()
        selected_indices = cleaned_data.get("selected_lines", [])
        if not selected_indices:
            raise ValidationError("Debes seleccionar al menos una línea.")

        selected_lines = []
        for index_str in selected_indices:
            index = int(index_str)
            line = self.delivery_note["lines"][index]
            delivery_quantity = Decimal(str(line["quantity"]))
            quantity_incident = cleaned_data.get(f"quantity_incident_{index}")
            if quantity_incident is None:
                self.add_error(f"quantity_incident_{index}", "Indica la cantidad de incidencia.")
                continue
            if quantity_incident <= 0:
                self.add_error(f"quantity_incident_{index}", "La cantidad debe ser mayor que cero.")
                continue
            if quantity_incident > delivery_quantity:
                self.add_error(
                    f"quantity_incident_{index}",
                    "La cantidad de incidencia no puede superar la cantidad del albarán.",
                )
                continue

            selected_line = dict(line)
            selected_line["quantity_incident"] = quantity_incident
            selected_lines.append(selected_line)

        cleaned_data["selected_line_items"] = selected_lines
        return cleaned_data


class ReturnIncidentCreateForm(forms.Form):
    DESTINATION_CHOICES = [
        ("Delegación-Almería", "Delegación-Almería"),
        ("Delegación-Murcia", "Delegación-Murcia"),
        ("Delegación-Sevilla", "Delegación-Sevilla"),
        ("Calahorra-La Plana", "Calahorra-La Plana"),
    ]

    observations = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )
    destination = forms.ChoiceField(
        label="Destino de mercancía",
        choices=DESTINATION_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    attachments = MultipleFileField(
        label="Adjuntos",
        required=False,
        widget=MultipleFileInput(attrs={"class": "form-control"}),
    )


class ReturnIncidentStatusForm(forms.Form):
    status = forms.ChoiceField(
        label="Estado",
        choices=ReturnIncidentStatus.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    resolution_notes = forms.CharField(
        label="Cómo se ha solucionado",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("status") == ReturnIncidentStatus.CLOSED and not cleaned_data.get("resolution_notes", "").strip():
            self.add_error("resolution_notes", "Debes indicar cómo se ha solucionado antes de cerrar la incidencia.")
        return cleaned_data
