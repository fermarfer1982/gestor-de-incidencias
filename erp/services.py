import logging

from core.access import get_accessible_representative_code
from erp.client import SQLServerClient
from erp.dtos import DeliveryNoteDTO, DeliveryNoteHeaderDTO, DeliveryNoteLineDTO
from erp.exceptions import ERPIntegrationError

logger = logging.getLogger(__name__)

DELIVERY_NOTE_QUERY = """
    SELECT
        ca.ca005 AS numero_albaran,
        ca.ca050 AS fecha_albaran,
        ca.ca170 AS cliente,
        ca.ca270 AS enviado_a,
        ca.ca640 AS codigo_representante,
        la.la006 AS linea_albaran,
        RTRIM(la.la030) AS codigo_articulo,
        RTRIM(pa.ar020) AS descripcion_articulo,
        da.da030 AS cantidad,
        RTRIM(la.la144) AS unidad_medida,
        COALESCE(env.ld040, '') AS envase,
        COALESCE(ah.lote_venta, '') AS lote_venta
    FROM admuser.fcomcal ca
    INNER JOIN admuser.fcomlal la
        ON ca.ca000 = la.la000
       AND ca.ca005 = la.la005
    LEFT JOIN admuser.fcomdal da
        ON la.la005 = da.da005
       AND la.la006 = da.da006
    OUTER APPLY (
        SELECT TOP 1
            CASE
                WHEN NULLIF(REPLACE(LTRIM(RTRIM(a.ah585)), ' ', ''), '') IS NOT NULL
                     AND LEN(REPLACE(LTRIM(RTRIM(a.ah585)), ' ', '')) = 1
                    THEN CONCAT(RTRIM(a.ah595), ' ', REPLACE(LTRIM(RTRIM(a.ah585)), ' ', ''))
                WHEN NULLIF(RTRIM(a.ah605), '') IS NOT NULL THEN RTRIM(a.ah605)
                ELSE RTRIM(a.ah595)
            END AS lote_venta,
            RTRIM(a.ah590) AS ah590
        FROM admuser.falmahl a
        WHERE la.la330 = a.ah000
          AND la.la029 = a.ah009
          AND RTRIM(la.la030) = RTRIM(a.ah010)
          AND RTRIM(da.da020) = RTRIM(a.ah020)
        ORDER BY
            CASE
                WHEN NULLIF(REPLACE(LTRIM(RTRIM(a.ah585)), ' ', ''), '') IS NOT NULL
                     AND LEN(REPLACE(LTRIM(RTRIM(a.ah585)), ' ', '')) = 1
                    THEN CONCAT(RTRIM(a.ah595), ' ', REPLACE(LTRIM(RTRIM(a.ah585)), ' ', ''))
                WHEN NULLIF(RTRIM(a.ah605), '') IS NOT NULL THEN RTRIM(a.ah605)
                ELSE RTRIM(a.ah595)
            END
    ) ah
    OUTER APPLY (
        SELECT TOP 1
            RTRIM(l.ld040) AS ld040
        FROM admuser.fadmlda l
        WHERE l.ld000 = 9172
          AND RTRIM(l.ld030) = RTRIM(ah.ah590)
        ORDER BY RTRIM(l.ld040)
    ) env
    LEFT JOIN admuser.fproart pa
        ON RTRIM(la.la030) = RTRIM(pa.ar000)
    WHERE ca.ca640 = ?
      AND ca.ca005 = ?
    ORDER BY la.la006
"""

GLOBAL_DELIVERY_NOTE_QUERY = DELIVERY_NOTE_QUERY.replace(
    "    WHERE ca.ca640 = ?\n      AND ca.ca005 = ?",
    "    WHERE ca.ca005 = ?",
)


def _normalize_lookup_value(value):
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdigit():
            return int(normalized)
        return normalized
    return value


def _deduplicate_delivery_note_rows(rows):
    unique_rows = {}
    for row in rows:
        key = (
            row["linea_albaran"],
            row["codigo_articulo"],
            row["lote_venta"] or "",
        )
        unique_rows.setdefault(key, row)
    return list(unique_rows.values())


def get_delivery_note_for_representative(representative_code, delivery_note_number, client=None):
    sql_server_client = client or SQLServerClient()
    representative_code = _normalize_lookup_value(representative_code) if representative_code else None
    delivery_note_number = _normalize_lookup_value(delivery_note_number)
    logger.debug(
        "Looking up delivery note for representative",
        extra={
            "representative_code": representative_code,
            "delivery_note_number": delivery_note_number,
        },
    )
    if representative_code:
        rows = sql_server_client.fetch_all(
            DELIVERY_NOTE_QUERY,
            (representative_code, delivery_note_number),
        )
    else:
        rows = sql_server_client.fetch_all(
            GLOBAL_DELIVERY_NOTE_QUERY,
            (delivery_note_number,),
        )
    deduplicated_rows = _deduplicate_delivery_note_rows(rows)
    logger.debug(
        "Delivery note query completed",
        extra={
            "representative_code": representative_code,
            "delivery_note_number": delivery_note_number,
            "raw_line_count": len(rows),
            "line_count": len(deduplicated_rows),
        },
    )

    if not deduplicated_rows:
        logger.info(
            "Delivery note not found for representative",
            extra={
                "representative_code": representative_code,
                "delivery_note_number": delivery_note_number,
            },
        )
        return None

    first_row = deduplicated_rows[0]
    header = DeliveryNoteHeaderDTO(
        delivery_note_number=first_row["numero_albaran"],
        delivery_note_date=first_row["fecha_albaran"],
        customer_name=first_row["cliente"],
        customer_fiscal_address=first_row.get("enviado_a") or "",
        representative_code=first_row["codigo_representante"],
    )
    lines = [
        DeliveryNoteLineDTO(
            delivery_note_line=row["linea_albaran"],
            article_code=row["codigo_articulo"],
            article_description=row["descripcion_articulo"],
            quantity=row["cantidad"],
            sale_lot=row["lote_venta"] or "",
            unit_of_measure=row.get("unidad_medida") or "",
            packaging=row.get("envase") or "",
        )
        for row in deduplicated_rows
    ]
    return DeliveryNoteDTO(header=header, lines=lines)


def get_delivery_note_for_user(user, delivery_note_number, client=None):
    representative_code = get_accessible_representative_code(user)
    if not representative_code:
        raise ERPIntegrationError("El usuario no tiene un único representante activo.")

    return get_delivery_note_for_representative(
        representative_code,
        delivery_note_number,
        client=client,
    )
