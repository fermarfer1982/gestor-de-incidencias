from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class DeliveryNoteHeaderDTO:
    delivery_note_number: str
    delivery_note_date: date | None
    customer_name: str
    representative_code: str
    customer_fiscal_address: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class DeliveryNoteLineDTO:
    delivery_note_line: int
    article_code: str
    article_description: str
    quantity: Decimal
    sale_lot: str
    unit_of_measure: str = ""
    packaging: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class DeliveryNoteDTO:
    header: DeliveryNoteHeaderDTO
    lines: list[DeliveryNoteLineDTO]

    def to_dict(self):
        return {
            "header": self.header.to_dict(),
            "lines": [line.to_dict() for line in self.lines],
        }
