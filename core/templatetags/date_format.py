from datetime import date, datetime

from django import template
from django.utils.dateparse import parse_date, parse_datetime

register = template.Library()


@register.filter
def spanish_date(value):
    if not value:
        return "-"

    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    if isinstance(value, str):
        parsed_datetime = parse_datetime(value)
        if parsed_datetime:
            return parsed_datetime.strftime("%d/%m/%Y")

        parsed_date = parse_date(value)
        if parsed_date:
            return parsed_date.strftime("%d/%m/%Y")

    return value
