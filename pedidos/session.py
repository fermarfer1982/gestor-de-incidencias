from datetime import date, datetime
from decimal import Decimal

ORDER_DELIVERY_NOTE_SESSION_KEY = "pedidos.delivery_note"
ORDER_SELECTED_LINES_SESSION_KEY = "pedidos.selected_lines"


def _serialize_scalar(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def store_order_delivery_note(request, delivery_note, representative):
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
        "search_representative": {
            "code": _serialize_scalar(representative.code),
            "name": _serialize_scalar(representative.name),
        },
    }
    request.session[ORDER_DELIVERY_NOTE_SESSION_KEY] = delivery_note_data
    request.session.modified = True


def get_order_delivery_note_data(request):
    return request.session.get(ORDER_DELIVERY_NOTE_SESSION_KEY)


def clear_order_delivery_note(request):
    request.session.pop(ORDER_DELIVERY_NOTE_SESSION_KEY, None)
    request.session.modified = True


def store_order_selected_lines(request, selected_lines):
    serialized_lines = []
    for line in selected_lines:
        serialized_line = dict(line)
        serialized_line["quantity"] = _serialize_scalar(serialized_line["quantity"])
        serialized_line["line_note"] = _serialize_scalar(serialized_line.get("line_note", ""))
        serialized_lines.append(serialized_line)
    request.session[ORDER_SELECTED_LINES_SESSION_KEY] = serialized_lines
    request.session.modified = True


def get_order_selected_lines_data(request):
    return request.session.get(ORDER_SELECTED_LINES_SESSION_KEY, [])


def clear_order_selected_lines(request):
    request.session.pop(ORDER_SELECTED_LINES_SESSION_KEY, None)
    request.session.modified = True


def clear_order_incident_creation_session(request):
    clear_order_delivery_note(request)
    clear_order_selected_lines(request)
