from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime

from pedidos.models import OrderIncident, OrderIncidentAttachment, OrderIncidentLine


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


def create_order_incident(*, user, representative, delivery_note, selected_lines, general_observations, files):
    if not selected_lines:
        raise ValidationError("No se puede crear una incidencia sin líneas seleccionadas.")

    with transaction.atomic():
        incident = OrderIncident.objects.create(
            created_by=user,
            delivery_note_number=delivery_note["header"]["delivery_note_number"],
            delivery_note_date=_parse_delivery_note_date(delivery_note["header"]["delivery_note_date"]),
            customer_name=delivery_note["header"]["customer_name"],
            customer_fiscal_address=delivery_note["header"].get("customer_fiscal_address", ""),
            representative_code=representative.code,
            representative_name=representative.name,
            general_observations=general_observations,
            total_selected_lines=len(selected_lines),
        )

        OrderIncidentLine.objects.bulk_create(
            [
                OrderIncidentLine(
                    incident=incident,
                    delivery_note_number=delivery_note["header"]["delivery_note_number"],
                    delivery_note_line=line["delivery_note_line"],
                    article_code=line["article_code"],
                    article_description=line["article_description"],
                    quantity_delivery_note=line["quantity"],
                    sale_lot=line["sale_lot"],
                    line_note=line.get("line_note", ""),
                )
                for line in selected_lines
            ]
        )

        for file_obj in files:
            OrderIncidentAttachment.objects.create(
                incident=incident,
                file=file_obj,
                uploaded_by=user,
            )

    return incident
