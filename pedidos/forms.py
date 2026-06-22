from django import forms
from django.core.exceptions import ValidationError

from devoluciones.forms import DeliveryNoteSearchForm, MultipleFileField, MultipleFileInput
from pedidos.models import OrderIncidentStatus


class OrderDeliveryNoteSelectionForm(forms.Form):
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
            self.fields[f"line_note_{index}"] = forms.CharField(
                required=False,
                label=f"Nota línea {line['delivery_note_line']}",
                widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Nota específica"}),
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

            selected_line = dict(line)
            selected_line["line_note"] = cleaned_data.get(f"line_note_{index}", "")
            selected_lines.append(selected_line)

        cleaned_data["selected_line_items"] = selected_lines
        return cleaned_data


class OrderIncidentCreateForm(forms.Form):
    general_observations = forms.CharField(
        label="Observaciones generales",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )
    attachments = MultipleFileField(
        label="Adjuntos",
        required=False,
        widget=MultipleFileInput(attrs={"class": "form-control"}),
    )


class OrderIncidentStatusForm(forms.Form):
    status = forms.ChoiceField(
        label="Estado",
        choices=OrderIncidentStatus.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    resolution_notes = forms.CharField(
        label="Cómo se ha solucionado",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("status") == OrderIncidentStatus.CLOSED and not cleaned_data.get("resolution_notes", "").strip():
            self.add_error("resolution_notes", "Debes indicar cómo se ha solucionado antes de cerrar la incidencia.")
        return cleaned_data
