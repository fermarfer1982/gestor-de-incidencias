from datetime import date, datetime
from decimal import Decimal

TRANSPORT_DELIVERY_NOTE_SESSION_KEY = "transporte.delivery_note"


def _serialize_scalar(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def store_transport_delivery_note(request, delivery_note, representative):
    request.session[TRANSPORT_DELIVERY_NOTE_SESSION_KEY] = {
        "header": {
            "delivery_note_number": _serialize_scalar(delivery_note.header.delivery_note_number),
            "delivery_note_date": _serialize_scalar(delivery_note.header.delivery_note_date),
            "customer_name": _serialize_scalar(delivery_note.header.customer_name),
            "representative_code": _serialize_scalar(delivery_note.header.representative_code),
        },
        "search_representative": {
            "code": _serialize_scalar(representative.code),
            "name": _serialize_scalar(representative.name),
        },
    }
    request.session.modified = True


def get_transport_delivery_note_data(request):
    return request.session.get(TRANSPORT_DELIVERY_NOTE_SESSION_KEY)


def clear_transport_delivery_note(request):
    request.session.pop(TRANSPORT_DELIVERY_NOTE_SESSION_KEY, None)
    request.session.modified = True
