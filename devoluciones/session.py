from datetime import date, datetime
from decimal import Decimal

DELIVERY_NOTE_SESSION_KEY = "devoluciones.delivery_note"
SELECTED_LINES_SESSION_KEY = "devoluciones.selected_lines"


def _serialize_scalar(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def store_delivery_note(request, delivery_note, representative):
    delivery_note_data = {
        "header": {
            "delivery_note_number": _serialize_scalar(delivery_note.header.delivery_note_number),
            "delivery_note_date": _serialize_scalar(delivery_note.header.delivery_note_date),
            "customer_name": _serialize_scalar(delivery_note.header.customer_name),
            "customer_fiscal_address": _serialize_scalar(delivery_note.header.customer_fiscal_address),
            "representative_code": _serialize_scalar(delivery_note.header.representative_code),
        },
        "lines": [
            {
                "delivery_note_line": _serialize_scalar(line.delivery_note_line),
                "article_code": _serialize_scalar(line.article_code),
                "article_description": _serialize_scalar(line.article_description),
                "quantity": _serialize_scalar(line.quantity),
                "sale_lot": _serialize_scalar(line.sale_lot),
                "unit_of_measure": _serialize_scalar(line.unit_of_measure),
                "packaging": _serialize_scalar(line.packaging),
            }
            for line in delivery_note.lines
        ],
    }
    delivery_note_data["search_representative"] = {
        "code": _serialize_scalar(representative.code),
        "name": _serialize_scalar(representative.name),
    }
    request.session[DELIVERY_NOTE_SESSION_KEY] = delivery_note_data
    request.session.modified = True


def get_delivery_note_data(request):
    return request.session.get(DELIVERY_NOTE_SESSION_KEY)


def clear_delivery_note(request):
    request.session.pop(DELIVERY_NOTE_SESSION_KEY, None)
    request.session.modified = True


def store_selected_lines(request, selected_lines):
    serialized_lines = []
    for line in selected_lines:
        serialized_line = dict(line)
        serialized_line["quantity"] = _serialize_scalar(serialized_line["quantity"])
        serialized_line["quantity_incident"] = _serialize_scalar(serialized_line["quantity_incident"])
        serialized_lines.append(serialized_line)
    request.session[SELECTED_LINES_SESSION_KEY] = serialized_lines
    request.session.modified = True


def get_selected_lines_data(request):
    return request.session.get(SELECTED_LINES_SESSION_KEY, [])


def clear_selected_lines(request):
    request.session.pop(SELECTED_LINES_SESSION_KEY, None)
    request.session.modified = True


def clear_incident_creation_session(request):
    clear_delivery_note(request)
    clear_selected_lines(request)
