from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.access import ROLE_ADMINISTRACION, ROLE_COMERCIAL
from core.models import UserAccessProfile, UserRepresentativeScope
from devoluciones.models import Representative
from erp.client import SQLServerClient
from erp.exceptions import ERPIntegrationError, SQLServerConnectionError, SQLServerQueryError
from erp.services import (
    DELIVERY_NOTE_QUERY,
    GLOBAL_DELIVERY_NOTE_QUERY,
    get_delivery_note_for_representative,
    get_delivery_note_for_user,
)


class ErpUrlsTests(TestCase):
    def test_index_page_exists(self):
        response = self.client.get(reverse("erp-index"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_index_redirects_to_access_denied_without_active_representative(self):
        user = get_user_model().objects.create_user(
            username="erp-no-rep",
            email="erp-no-rep@example.com",
            password="secret123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("erp-index"))

        self.assertRedirects(response, reverse("access-denied"))

    def test_index_is_accessible_for_administracion_without_representative(self):
        user = get_user_model().objects.create_user(
            username="erp-admin-role",
            email="erp-admin-role@example.com",
            password="secret123",
        )
        group = Group.objects.create(name=ROLE_ADMINISTRACION)
        user.groups.add(group)
        UserAccessProfile.objects.create(
            user=user,
            role=ROLE_ADMINISTRACION,
            all_representatives=True,
            active=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("erp-index"))

        self.assertEqual(response.status_code, 200)


class SQLServerClientTests(SimpleTestCase):
    @patch("erp.client.mssql_python.connect")
    def test_fetch_all_returns_list_of_dicts(self, connect_mock):
        connection_mock = MagicMock()
        cursor_mock = MagicMock()
        cursor_mock.description = [("numero_albaran",), ("linea_albaran",)]
        cursor_mock.fetchall.return_value = [("ALB-1", 1), ("ALB-1", 2)]
        connection_mock.cursor.return_value = cursor_mock
        connect_mock.return_value = connection_mock

        client = SQLServerClient(connection_string="Driver=Test;Server=sql;")

        rows = client.fetch_all("SELECT numero_albaran, linea_albaran FROM test WHERE id = ?", ("ALB-1",))

        self.assertEqual(
            rows,
            [
                {"numero_albaran": "ALB-1", "linea_albaran": 1},
                {"numero_albaran": "ALB-1", "linea_albaran": 2},
            ],
        )
        cursor_mock.execute.assert_called_once_with(
            "SELECT numero_albaran, linea_albaran FROM test WHERE id = ?",
            "ALB-1",
        )
        self.assertEqual(connection_mock.timeout, client.query_timeout)
        connection_mock.close.assert_called_once()

    @patch("erp.client.mssql_python.connect", side_effect=RuntimeError("boom"))
    def test_connection_error_is_wrapped(self, _connect_mock):
        client = SQLServerClient(connection_string="Driver=Test;Server=sql;")

        with self.assertRaises(SQLServerConnectionError):
            client.fetch_all("SELECT 1", ())

    @patch("erp.client.mssql_python.connect")
    def test_query_error_is_wrapped(self, connect_mock):
        connection_mock = MagicMock()
        cursor_mock = MagicMock()
        cursor_mock.execute.side_effect = RuntimeError("query failed")
        connection_mock.cursor.return_value = cursor_mock
        connect_mock.return_value = connection_mock
        client = SQLServerClient(connection_string="Driver=Test;Server=sql;")

        with self.assertRaises(SQLServerQueryError):
            client.fetch_all("SELECT 1", ())


class DeliveryNoteServiceTests(SimpleTestCase):
    def test_service_returns_header_and_lines(self):
        client = MagicMock()
        client.fetch_all.return_value = [
            {
                "numero_albaran": "ALB-100",
                "fecha_albaran": date(2026, 3, 24),
                "cliente": "Cliente Demo",
                "enviado_a": "Direccion Envio Demo",
                "codigo_representante": "REP001",
                "linea_albaran": 1,
                "codigo_articulo": "A1",
                "descripcion_articulo": "Articulo 1",
                "cantidad": Decimal("2.00"),
                "unidad_medida": "KG",
                "envase": "Caja 10",
                "lote_venta": "LOTE-605",
            },
            {
                "numero_albaran": "ALB-100",
                "fecha_albaran": date(2026, 3, 24),
                "cliente": "Cliente Demo",
                "enviado_a": "Direccion Envio Demo",
                "codigo_representante": "REP001",
                "linea_albaran": 2,
                "codigo_articulo": "A2",
                "descripcion_articulo": "Articulo 2",
                "cantidad": Decimal("1.00"),
                "unidad_medida": "KG",
                "envase": "Caja 20",
                "lote_venta": "LOTE-595 A",
            },
        ]

        delivery_note = get_delivery_note_for_representative("REP001", "ALB-100", client=client)

        self.assertEqual(delivery_note.header.delivery_note_number, "ALB-100")
        self.assertEqual(delivery_note.header.representative_code, "REP001")
        self.assertEqual(delivery_note.header.customer_name, "Cliente Demo")
        self.assertEqual(delivery_note.header.customer_fiscal_address, "Direccion Envio Demo")
        self.assertEqual(len(delivery_note.lines), 2)
        self.assertEqual(delivery_note.lines[0].delivery_note_line, 1)
        self.assertEqual(delivery_note.lines[0].unit_of_measure, "KG")
        self.assertEqual(delivery_note.lines[0].packaging, "Caja 10")
        self.assertEqual(delivery_note.lines[0].sale_lot, "LOTE-605")
        self.assertEqual(delivery_note.lines[1].delivery_note_line, 2)
        self.assertEqual(delivery_note.lines[1].packaging, "Caja 20")
        self.assertEqual(delivery_note.lines[1].sale_lot, "LOTE-595 A")
        client.fetch_all.assert_called_once_with(DELIVERY_NOTE_QUERY, ("REP001", "ALB-100"))

    def test_service_normalizes_numeric_string_filters(self):
        client = MagicMock()
        client.fetch_all.return_value = [
            {
                "numero_albaran": 143071,
                "fecha_albaran": date(2026, 3, 24),
                "cliente": "Cliente Demo",
                "enviado_a": "Direccion Envio Demo",
                "codigo_representante": 4,
                "linea_albaran": 1,
                "codigo_articulo": "A1",
                "descripcion_articulo": "Articulo 1",
                "cantidad": Decimal("2.00"),
                "unidad_medida": "KG",
                "envase": "Caja 10",
                "lote_venta": "LOTE-595",
            }
        ]

        delivery_note = get_delivery_note_for_representative(" 4 ", " 143071 ", client=client)

        self.assertEqual(delivery_note.header.delivery_note_number, 143071)
        client.fetch_all.assert_called_once_with(DELIVERY_NOTE_QUERY, (4, 143071))

    def test_service_can_search_without_representative_filter(self):
        client = MagicMock()
        client.fetch_all.return_value = [
            {
                "numero_albaran": "ALB-100",
                "fecha_albaran": date(2026, 3, 24),
                "cliente": "Cliente Demo",
                "enviado_a": "Direccion Envio Demo",
                "codigo_representante": "REP001",
                "linea_albaran": 1,
                "codigo_articulo": "A1",
                "descripcion_articulo": "Articulo 1",
                "cantidad": Decimal("2.00"),
                "unidad_medida": "KG",
                "envase": "Caja 10",
                "lote_venta": "LOTE-595",
            }
        ]

        delivery_note = get_delivery_note_for_representative(None, "ALB-100", client=client)

        self.assertEqual(delivery_note.header.representative_code, "REP001")
        client.fetch_all.assert_called_once_with(GLOBAL_DELIVERY_NOTE_QUERY, ("ALB-100",))

    def test_service_deduplicates_same_line_article_and_lot_combination(self):
        client = MagicMock()
        client.fetch_all.return_value = [
            {
                "numero_albaran": "ALB-100",
                "fecha_albaran": date(2026, 3, 24),
                "cliente": "Cliente Demo",
                "enviado_a": "Direccion Envio Demo",
                "codigo_representante": "REP001",
                "linea_albaran": 1,
                "codigo_articulo": "A1",
                "descripcion_articulo": "Articulo 1",
                "cantidad": Decimal("2.00"),
                "unidad_medida": "KG",
                "envase": "Caja 10",
                "lote_venta": "LOTE-595",
            },
            {
                "numero_albaran": "ALB-100",
                "fecha_albaran": date(2026, 3, 24),
                "cliente": "Cliente Demo",
                "enviado_a": "Direccion Envio Demo",
                "codigo_representante": "REP001",
                "linea_albaran": 1,
                "codigo_articulo": "A1",
                "descripcion_articulo": "Articulo 1",
                "cantidad": Decimal("2.00"),
                "unidad_medida": "KG",
                "envase": "Caja 10",
                "lote_venta": "LOTE-595",
            },
        ]

        delivery_note = get_delivery_note_for_representative("REP001", "ALB-100", client=client)

        self.assertEqual(len(delivery_note.lines), 1)

    @patch("erp.services.logger")
    def test_service_logs_lookup_parameters_and_line_count(self, logger_mock):
        client = MagicMock()
        client.fetch_all.return_value = [
            {
                "numero_albaran": "ALB-100",
                "fecha_albaran": date(2026, 3, 24),
                "cliente": "Cliente Demo",
                "enviado_a": "Direccion Envio Demo",
                "codigo_representante": "REP001",
                "linea_albaran": 1,
                "codigo_articulo": "A1",
                "descripcion_articulo": "Articulo 1",
                "cantidad": Decimal("2.00"),
                "unidad_medida": "KG",
                "envase": "Caja 10",
                "lote_venta": "LOTE-595",
            }
        ]

        get_delivery_note_for_representative("REP001", "ALB-100", client=client)

        self.assertEqual(logger_mock.debug.call_count, 2)

    def test_service_returns_none_when_albaran_not_found(self):
        client = MagicMock()
        client.fetch_all.return_value = []

        delivery_note = get_delivery_note_for_representative("REP001", "ALB-404", client=client)

        self.assertIsNone(delivery_note)


class DeliveryNoteForUserTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="erp-user",
            email="erp@example.com",
            password="secret123",
        )

    @patch("erp.services.get_delivery_note_for_representative")
    def test_service_uses_access_profile_scope_to_resolve_representative(self, service_mock):
        representative = Representative.objects.create(code="REP003", name="Representante Tres")
        group = Group.objects.create(name=ROLE_COMERCIAL)
        self.user.groups.add(group)
        profile = UserAccessProfile.objects.create(
            user=self.user,
            role=ROLE_COMERCIAL,
            all_representatives=False,
            active=True,
        )
        UserRepresentativeScope.objects.create(profile=profile, representative=representative, active=True)

        get_delivery_note_for_user(self.user, "ALB-200")

        service_mock.assert_called_once_with("REP003", "ALB-200", client=None)

    def test_service_raises_error_without_active_representative(self):
        with self.assertRaises(ERPIntegrationError):
            get_delivery_note_for_user(self.user, "ALB-200")
