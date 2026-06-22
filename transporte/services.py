from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_date, parse_datetime

from transporte.models import TransportIncident, TransportIncidentAttachment


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


def create_transport_incident(*, user, representative, delivery_note, form_data, files):
    has_delivery_note = form_data["has_delivery_note"] == "yes"
    if has_delivery_note and not delivery_note:
        raise ValidationError("Debes buscar un albarán antes de crear la incidencia.")

    delivery_note_header = delivery_note["header"] if delivery_note else {}
    with transaction.atomic():
        incident = TransportIncident.objects.create(
            created_by=user,
            has_delivery_note=has_delivery_note,
            delivery_note_number=delivery_note_header.get("delivery_note_number"),
            delivery_note_date=_parse_delivery_note_date(delivery_note_header.get("delivery_note_date")),
            customer_name=delivery_note_header.get("customer_name"),
            representative_code=representative.code if representative else None,
            representative_name=representative.name if representative else None,
            description=form_data["description"],
            carrier=form_data["carrier"],
            incident_type=form_data["incident_type"],
            shipment_direction=form_data["shipment_direction"],
            tracking_number=form_data["tracking_number"],
            internal_reference=form_data["internal_reference"],
            country=form_data["country"],
            province=form_data["province"],
            municipality=form_data["municipality"],
            sender=form_data["sender"],
            recipient=form_data["recipient"],
            shipping_date=form_data["shipping_date"],
            incident_date=form_data["incident_date"],
        )

        for file_obj in files:
            TransportIncidentAttachment.objects.create(
                incident=incident,
                file=file_obj,
                uploaded_by=user,
            )

    return incident
