import textwrap

from django.http import HttpResponse

from core.exporting import format_export_value


def display_user(user):
    if not user:
        return "-"
    return user.email or user.username


def printable_value(value):
    value = format_export_value(value)
    return value if value else "-"


def build_pdf_response(*, filename, title, sections, tables=None, attachments=None):
    lines = [title, ""]
    for section in sections:
        lines.append(section["title"])
        for label, value in section["rows"]:
            value = printable_value(value)
            for wrapped in textwrap.wrap(f"{label}: {value}", width=95) or [""]:
                lines.append(wrapped)
        lines.append("")

    for table in tables or []:
        lines.append(table["title"])
        lines.append(" | ".join(table["headers"]))
        for row in table["rows"]:
            row_text = " | ".join(printable_value(value) for value in row)
            lines.extend(textwrap.wrap(row_text, width=110) or [""])
        lines.append("")

    lines.append("Adjuntos")
    if attachments:
        lines.extend(f"- {name}" for name in attachments)
    else:
        lines.append("-")

    pdf_bytes = _build_basic_pdf(lines)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _build_basic_pdf(lines):
    pages = [lines[index : index + 45] for index in range(0, len(lines), 45)] or [[]]
    objects = [None, "<< /Type /Catalog /Pages 2 0 R >>", None]
    page_refs = []

    next_object_number = 3
    for page_lines in pages:
        page_number = next_object_number
        content_number = next_object_number + 1
        next_object_number += 2
        page_refs.append(f"{page_number} 0 R")
        content = _page_content_stream(page_lines)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
            f"/Contents {content_number} 0 R >>"
        )
        objects.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream")
    objects[2] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>"

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, obj in enumerate(objects[1:], start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n{obj}\nendobj\n".encode("latin-1", errors="replace"))

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode(
            "ascii"
        )
    )
    return bytes(pdf)


def _page_content_stream(lines):
    commands = ["BT", "/F1 10 Tf", "50 800 Td", "14 TL"]
    for line in lines:
        commands.append(f"({_escape_pdf_text(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands)


def _escape_pdf_text(value):
    value = str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return value.encode("latin-1", errors="replace").decode("latin-1")
