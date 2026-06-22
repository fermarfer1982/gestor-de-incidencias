from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date, parse_datetime
from django.db import transaction

from devoluciones.models import IncidentAttachment, ReturnIncident, ReturnIncidentLine, ReturnIncidentStatus


OPEN_INCIDENT_STATUSES = [
    ReturnIncidentStatus.PENDING,
    ReturnIncidentStatus.IN_PROGRESS,
]


def _get_selected_delivery_note_lines(selected_lines):
    return sorted(int(line["delivery_note_line"]) for line in selected_lines)


def _has_open_duplicate_incident(*, representative, delivery_note_number, selected_lines):
    selected_delivery_note_lines = _get_selected_delivery_note_lines(selected_lines)
    open_incidents = (
        ReturnIncident.objects.filter(
            delivery_note_number=delivery_note_number,
            representative_code=representative.code,
            status__in=OPEN_INCIDENT_STATUSES,
        )
        .prefetch_related("lines")
        .only("id", "delivery_note_number", "representative_code", "status")
    )

    for incident in open_incidents:
        incident_delivery_note_lines = sorted(incident.lines.values_list("delivery_note_line", flat=True))
        if incident_delivery_note_lines == selected_delivery_note_lines:
            return True
    return False


def _parse_delivery_note_date(value):
    if not value:
        return None
    parsed_date = parse_date(value)
    if parsed_date:
        return parsed_date
    parsed_datetime = parse_datetime(value)
    if parsed_datetime:
        return parsed_datetime.date()
    return None


def create_return_incident(*, user, representative, delivery_note, selected_lines, observations, destination, files):
    if not selected_lines:
        raise ValidationError("No se puede crear una incidencia sin líneas seleccionadas.")
    if _has_open_duplicate_incident(
        representative=representative,
        delivery_note_number=delivery_note["header"]["delivery_note_number"],
        selected_lines=selected_lines,
    ):
        raise ValidationError(
            "Ya existe una incidencia abierta para este albarán con las mismas líneas seleccionadas."
        )

    with transaction.atomic():
        incident = ReturnIncident.objects.create(
            created_by=user,
            delivery_note_number=delivery_note["header"]["delivery_note_number"],
            delivery_note_date=_parse_delivery_note_date(delivery_note["header"]["delivery_note_date"]),
            customer_name=delivery_note["header"]["customer_name"],
            customer_fiscal_address=delivery_note["header"].get("customer_fiscal_address", ""),
            representative_code=representative.code,
            representative_name=representative.name,
            observations=observations,
            destination=destination,
            total_selected_lines=len(selected_lines),
        )

        ReturnIncidentLine.objects.bulk_create(
            [
                ReturnIncidentLine(
                    incident=incident,
                    delivery_note_number=delivery_note["header"]["delivery_note_number"],
                    delivery_note_line=line["delivery_note_line"],
                    article_code=line["article_code"],
                    article_description=line["article_description"],
                    quantity_delivery_note=line["quantity"],
                    quantity_incident=line["quantity_incident"],
                    sale_lot=line["sale_lot"],
                )
                for line in selected_lines
            ]
        )

        for file_obj in files:
            IncidentAttachment.objects.create(
                incident=incident,
                file=file_obj,
                uploaded_by=user,
            )

    return incident
