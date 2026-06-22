import shutil
import tempfile
import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.access import ROLE_ADMINISTRACION, ROLE_ALMACEN, ROLE_COMERCIAL
from core.models import UserAccessProfile, UserRepresentativeScope
from devoluciones.models import Representative, UserRepresentative
from erp.dtos import DeliveryNoteDTO, DeliveryNoteHeaderDTO, DeliveryNoteLineDTO
from pedidos.admin import OrderIncidentAdmin
from pedidos.models import OrderIncident, OrderIncidentAttachment, OrderIncidentLine, OrderIncidentStatus
from pedidos.services import create_order_incident


class OrderIncidentModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="order-user",
            email="order-user@example.com",
            password="secret123",
        )
        self.representative = Representative.objects.create(code="REP001", name="Representante Uno")

    def test_incident_number_is_generated_with_expected_format(self):
        incident = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Pedido",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            general_observations="Observacion",
            total_selected_lines=1,
        )

        year = timezone.now().year
        self.assertEqual(incident.incident_number, f"PED-{year}-000001")

    def test_line_string_is_readable(self):
        incident = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            customer_name="Cliente Pedido",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            total_selected_lines=1,
        )
        line = OrderIncidentLine.objects.create(
            incident=incident,
            delivery_note_number="ALB-100",
            delivery_note_line=1,
            article_code="A1",
            article_description="Articulo 1",
            quantity_delivery_note=Decimal("5.00"),
            sale_lot="L1",
            line_note="Nota",
        )

        self.assertIn("linea 1", str(line))


@override_settings(DJANGO_USE_SQLITE=True)
class OrderIncidentServiceTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.user = get_user_model().objects.create_user(
            username="order-service",
            email="order-service@example.com",
            password="secret123",
        )
        self.representative = Representative.objects.create(code="REP010", name="Representante Servicio")

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_create_order_incident_persists_header_lines_notes_and_attachments(self):
        incident = create_order_incident(
            user=self.user,
            representative=self.representative,
            delivery_note={
                "header": {
                    "delivery_note_number": "ALB-500",
                    "delivery_note_date": "2026-03-24",
                    "customer_name": "Cliente Servicio",
                    "customer_fiscal_address": "Direccion",
                },
                "lines": [],
            },
            selected_lines=[
                {
                    "delivery_note_line": 1,
                    "article_code": "A1",
                    "article_description": "Articulo 1",
                    "quantity": "4.00",
                    "sale_lot": "L1",
                    "line_note": "Nota linea",
                }
            ],
            general_observations="Observaciones generales",
            files=[SimpleUploadedFile("pedido.txt", b"contenido", content_type="text/plain")],
        )

        self.assertEqual(incident.created_by, self.user)
        self.assertEqual(incident.lines.count(), 1)
        self.assertEqual(incident.lines.get().line_note, "Nota linea")
        self.assertEqual(incident.attachments.count(), 1)
        self.assertEqual(incident.total_selected_lines, 1)

    def test_create_order_incident_requires_selected_lines(self):
        with self.assertRaises(ValidationError):
            create_order_incident(
                user=self.user,
                representative=self.representative,
                delivery_note={
                    "header": {
                        "delivery_note_number": "ALB-999",
                        "delivery_note_date": "2026-03-24",
                        "customer_name": "Cliente Sin Lineas",
                    },
                    "lines": [],
                },
                selected_lines=[],
                general_observations="Obs",
                files=[],
            )


@override_settings(DJANGO_USE_SQLITE=True)
class OrderIncidentFlowTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

        self.commercial_group = Group.objects.create(name=ROLE_COMERCIAL)
        self.admin_group = Group.objects.create(name=ROLE_ADMINISTRACION)
        self.warehouse_group = Group.objects.create(name=ROLE_ALMACEN)
        self.user = get_user_model().objects.create_user(
            username="order-flow",
            email="order-flow@example.com",
            password="secret123",
        )
        self.user.groups.add(self.commercial_group)
        self.representative = Representative.objects.create(code="REP002", name="Representante Dos")
        UserRepresentative.objects.create(user=self.user, representative=self.representative, active=True)
        self.user_profile = UserAccessProfile.objects.create(
            user=self.user,
            role=ROLE_COMERCIAL,
            all_representatives=False,
            active=True,
        )
        UserRepresentativeScope.objects.create(
            profile=self.user_profile,
            representative=self.representative,
            active=True,
        )
        self.client.force_login(self.user)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def create_access_user(self, *, username, role, representatives=None, all_representatives=False):
        user = get_user_model().objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="secret123",
            is_staff=True,
        )
        group = {
            ROLE_COMERCIAL: self.commercial_group,
            ROLE_ADMINISTRACION: self.admin_group,
            ROLE_ALMACEN: self.warehouse_group,
        }[role]
        user.groups.add(group)
        profile = UserAccessProfile.objects.create(
            user=user,
            role=role,
            all_representatives=all_representatives,
            active=True,
        )
        for representative in representatives or []:
            UserRepresentativeScope.objects.create(profile=profile, representative=representative, active=True)
        return user

    def build_delivery_note(self):
        return DeliveryNoteDTO(
            header=DeliveryNoteHeaderDTO(
                delivery_note_number="ALB-100",
                delivery_note_date=date(2026, 3, 24),
                customer_name="Cliente Pedido",
                representative_code="REP002",
                customer_fiscal_address="Direccion Pedido",
            ),
            lines=[
                DeliveryNoteLineDTO(
                    delivery_note_line=1,
                    article_code="A1",
                    article_description="Articulo 1",
                    quantity=Decimal("5.00"),
                    sale_lot="L1",
                ),
                DeliveryNoteLineDTO(
                    delivery_note_line=2,
                    article_code="A2",
                    article_description="Articulo 2",
                    quantity=Decimal("3.00"),
                    sale_lot="L2",
                ),
            ],
        )

    @patch("pedidos.views.get_delivery_note_for_representative")
    def test_search_uses_authenticated_user_scope(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()

        response = self.client.post(
            reverse("pedidos-index"),
            data={"delivery_note_number": "ALB-100", "representative_code": "REP999"},
        )

        self.assertRedirects(response, reverse("order-delivery-note-result"))
        get_delivery_note_for_representative_mock.assert_called_once_with(self.representative.code, "ALB-100")

    @patch("pedidos.views.get_delivery_note_for_representative")
    def test_almacen_can_search_without_choosing_representative(self, get_delivery_note_for_representative_mock):
        warehouse_user = self.create_access_user(username="warehouse-order-search", role=ROLE_ALMACEN)
        self.client.force_login(warehouse_user)
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()

        response = self.client.post(reverse("pedidos-index"), data={"delivery_note_number": "ALB-100"})

        self.assertRedirects(response, reverse("order-delivery-note-result"))
        get_delivery_note_for_representative_mock.assert_called_once_with(None, "ALB-100")

    @patch("pedidos.views.get_delivery_note_for_representative")
    def test_superuser_can_search_without_choosing_representative(self, get_delivery_note_for_representative_mock):
        superuser = get_user_model().objects.create_superuser(
            username="super-order-search",
            email="super-order-search@example.com",
            password="secret123",
        )
        self.client.force_login(superuser)
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()

        response = self.client.post(reverse("pedidos-index"), data={"delivery_note_number": "ALB-100"})

        self.assertRedirects(response, reverse("order-delivery-note-result"))
        get_delivery_note_for_representative_mock.assert_called_once_with(None, "ALB-100")

    @patch("pedidos.views.get_delivery_note_for_representative")
    def test_search_shows_message_when_delivery_note_not_found(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = None

        response = self.client.post(reverse("pedidos-index"), data={"delivery_note_number": "ALB-404"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No se ha encontrado el albarán para el representante indicado")

    @patch("pedidos.views.get_delivery_note_for_representative")
    def test_full_flow_creates_order_incident_lines_notes_and_attachments(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()

        self.assertRedirects(
            self.client.post(reverse("pedidos-index"), data={"delivery_note_number": "ALB-100"}),
            reverse("order-delivery-note-result"),
        )
        result_response = self.client.get(reverse("order-delivery-note-result"))
        self.assertEqual(result_response.status_code, 200)
        self.assertContains(result_response, "Cliente Pedido")
        self.assertContains(result_response, "Nota línea")
        self.assertNotContains(result_response, "Cantidad incidencia")
        self.assertNotContains(result_response, "Devoluciones")

        self.assertRedirects(
            self.client.post(
                reverse("order-delivery-note-result"),
                data={
                    "selected_lines": ["0", "1"],
                    "line_note_0": "Falta material",
                    "line_note_1": "Revisar precio",
                },
            ),
            reverse("order-incident-create"),
        )
        session = self.client.session
        self.assertEqual(len(session["pedidos.selected_lines"]), 2)
        self.assertEqual(session["pedidos.selected_lines"][0]["line_note"], "Falta material")
        self.assertNotIn("quantity_incident", session["pedidos.selected_lines"][0])

        file_one = SimpleUploadedFile("pedido1.txt", b"adjunto 1", content_type="text/plain")
        response = self.client.post(
            reverse("order-incident-create"),
            data={
                "general_observations": "Observacion general",
                "attachments": [file_one],
            },
        )

        incident = OrderIncident.objects.get()
        self.assertRedirects(response, reverse("order-incident-detail", kwargs={"pk": incident.pk}))
        self.assertEqual(incident.created_by, self.user)
        self.assertEqual(incident.customer_name, "Cliente Pedido")
        self.assertEqual(incident.total_selected_lines, 2)
        self.assertEqual(incident.lines.count(), 2)
        self.assertEqual(incident.attachments.count(), 1)
        self.assertEqual(OrderIncidentAttachment.objects.count(), 1)
        self.assertTrue(incident.lines.filter(line_note="Falta material").exists())

        detail_response = self.client.get(reverse("order-incident-detail", kwargs={"pk": incident.pk}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, incident.incident_number)
        self.assertContains(detail_response, "Observacion general")
        self.assertContains(detail_response, "Falta material")
        self.assertContains(detail_response, "pedido1")

        list_response = self.client.get(reverse("order-incidents"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, incident.incident_number)

    @patch("pedidos.views.get_delivery_note_for_representative")
    def test_selection_requires_at_least_one_line(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()
        self.client.post(reverse("pedidos-index"), data={"delivery_note_number": "ALB-100"})

        response = self.client.post(reverse("order-delivery-note-result"), data={})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Debes seleccionar al menos una línea")

    @patch("pedidos.views.get_delivery_note_for_representative")
    def test_order_result_does_not_render_quantity_incident_field(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()
        self.client.post(reverse("pedidos-index"), data={"delivery_note_number": "ALB-100"})

        response = self.client.get(reverse("order-delivery-note-result"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Cantidad incidencia")
        self.assertNotContains(response, "quantity_incident_0")

    def test_create_revalidates_representative_from_session(self):
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        session = self.client.session
        session["pedidos.delivery_note"] = {
            "header": {
                "delivery_note_number": "ALB-999",
                "delivery_note_date": "2026-03-24",
                "customer_name": "Cliente Manipulado",
                "customer_fiscal_address": "",
                "representative_code": other_representative.code,
            },
            "lines": [],
            "search_representative": {
                "code": other_representative.code,
                "name": other_representative.name,
            },
        }
        session["pedidos.selected_lines"] = [
            {
                "delivery_note_line": 1,
                "article_code": "A1",
                "article_description": "Articulo 1",
                "quantity": "5.00",
                "sale_lot": "L1",
                "line_note": "Manipulada",
            }
        ]
        session.save()

        response = self.client.post(
            reverse("order-incident-create"),
            data={"general_observations": "Intento fuera de alcance"},
        )

        self.assertRedirects(response, reverse("access-denied"))
        self.assertFalse(OrderIncident.objects.filter(customer_name="Cliente Manipulado").exists())

    def test_commercial_list_and_detail_are_filtered_by_representative_code(self):
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        allowed = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Permitido",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            total_selected_lines=1,
        )
        blocked = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Bloqueado",
            representative_code=other_representative.code,
            representative_name=other_representative.name,
            total_selected_lines=1,
        )

        list_response = self.client.get(reverse("order-incidents"))
        self.assertContains(list_response, "Cliente Permitido")
        self.assertNotContains(list_response, "Cliente Bloqueado")
        self.assertEqual(self.client.get(reverse("order-incident-detail", kwargs={"pk": allowed.pk})).status_code, 200)
        self.assertEqual(self.client.get(reverse("order-incident-detail", kwargs={"pk": blocked.pk})).status_code, 404)

    def test_printable_detail_is_available_inside_scope(self):
        incident = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Pedido Imprimible",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            general_observations="Observación pedido",
            resolution_notes="Resuelto pedido",
            total_selected_lines=1,
        )
        OrderIncidentLine.objects.create(
            incident=incident,
            delivery_note_number="ALB-100",
            delivery_note_line=1,
            article_code="A1",
            article_description="Articulo 1",
            quantity_delivery_note=Decimal("5.00"),
            sale_lot="L1",
            line_note="Nota línea",
        )
        OrderIncidentAttachment.objects.create(
            incident=incident,
            file=SimpleUploadedFile("pedido.txt", b"contenido"),
            uploaded_by=self.user,
        )

        response = self.client.get(reverse("order-incident-print", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incidencia de pedido")
        self.assertContains(response, "Cliente Pedido Imprimible")
        self.assertContains(response, "pedido.txt")

    def test_pdf_detail_is_available_inside_scope(self):
        incident = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Pedido PDF",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            total_selected_lines=0,
        )

        response = self.client.get(reverse("order-incident-pdf", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_printable_detail_is_denied_outside_scope(self):
        incident = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Pedido Bloqueado",
            representative_code="REP999",
            representative_name="Otro",
            total_selected_lines=0,
        )

        response = self.client.get(reverse("order-incident-print", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(reverse("order-incident-pdf", kwargs={"pk": incident.pk})).status_code, 404)

    def test_almacen_list_shows_all_incidents(self):
        warehouse_user = self.create_access_user(username="warehouse-orders", role=ROLE_ALMACEN)
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            customer_name="Cliente Comercial",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            total_selected_lines=1,
        )
        OrderIncident.objects.create(
            created_by=warehouse_user,
            delivery_note_number="ALB-999",
            customer_name="Cliente Global",
            representative_code=other_representative.code,
            representative_name=other_representative.name,
            total_selected_lines=1,
        )
        self.client.force_login(warehouse_user)

        response = self.client.get(reverse("order-incidents"))

        self.assertContains(response, "Cliente Comercial")
        self.assertContains(response, "Cliente Global")

    def test_administracion_with_one_representative_is_filtered(self):
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        admin_user = self.create_access_user(
            username="admin-orders",
            role=ROLE_ADMINISTRACION,
            representatives=[self.representative],
        )
        OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            customer_name="Cliente Permitido",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            total_selected_lines=1,
        )
        OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            customer_name="Cliente No Permitido",
            representative_code=other_representative.code,
            representative_name=other_representative.name,
            total_selected_lines=1,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("order-incidents"))

        self.assertContains(response, "Cliente Permitido")
        self.assertNotContains(response, "Cliente No Permitido")

    def test_order_excel_export_contains_expected_content(self):
        OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            customer_name="Cliente Excel Pedido",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            resolution_notes="Pedido revisado",
            total_selected_lines=1,
        )

        response = self.client.get(reverse("order-incident-export", kwargs={"export_format": "xlsx"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        with zipfile.ZipFile(BytesIO(response.content)) as workbook:
            worksheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("Cliente Excel Pedido", worksheet)
        self.assertIn("pedidos", worksheet)
        self.assertIn("Pedido revisado", worksheet)

    def test_change_status_from_open_to_in_progress(self):
        incident = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            customer_name="Cliente Estado",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            total_selected_lines=1,
        )

        response = self.client.post(
            reverse("order-incident-detail", kwargs={"pk": incident.pk}),
            data={
                "status": OrderIncidentStatus.IN_PROGRESS,
                "resolution_notes": "",
            },
        )

        self.assertRedirects(response, reverse("order-incident-detail", kwargs={"pk": incident.pk}))
        incident.refresh_from_db()
        self.assertEqual(incident.status, OrderIncidentStatus.IN_PROGRESS)
        self.assertIsNone(incident.closed_at)
        self.assertIsNone(incident.closed_by)

    def test_close_with_resolution_notes_updates_traceability(self):
        incident = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            customer_name="Cliente Cierre",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            total_selected_lines=1,
        )

        response = self.client.post(
            reverse("order-incident-detail", kwargs={"pk": incident.pk}),
            data={
                "status": OrderIncidentStatus.CLOSED,
                "resolution_notes": "Se corrigió el pedido y se informó al cliente.",
            },
        )

        self.assertRedirects(response, reverse("order-incident-detail", kwargs={"pk": incident.pk}))
        incident.refresh_from_db()
        self.assertEqual(incident.status, OrderIncidentStatus.CLOSED)
        self.assertEqual(incident.resolution_notes, "Se corrigió el pedido y se informó al cliente.")
        self.assertIsNotNone(incident.closed_at)
        self.assertEqual(incident.closed_by, self.user)

    def test_close_requires_resolution_notes(self):
        incident = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            customer_name="Cliente Sin Resolucion",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            total_selected_lines=1,
        )

        response = self.client.post(
            reverse("order-incident-detail", kwargs={"pk": incident.pk}),
            data={
                "status": OrderIncidentStatus.CLOSED,
                "resolution_notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Debes indicar cómo se ha solucionado")
        incident.refresh_from_db()
        self.assertEqual(incident.status, OrderIncidentStatus.PENDING)
        self.assertIsNone(incident.closed_at)
        self.assertIsNone(incident.closed_by)

    def test_status_update_outside_representative_scope_is_blocked(self):
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        incident = OrderIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            customer_name="Cliente Fuera Alcance",
            representative_code=other_representative.code,
            representative_name=other_representative.name,
            total_selected_lines=1,
        )

        response = self.client.post(
            reverse("order-incident-detail", kwargs={"pk": incident.pk}),
            data={
                "status": OrderIncidentStatus.IN_PROGRESS,
                "resolution_notes": "",
            },
        )

        self.assertEqual(response.status_code, 404)
        incident.refresh_from_db()
        self.assertEqual(incident.status, OrderIncidentStatus.PENDING)

    def test_non_superuser_delete_is_denied_in_admin(self):
        warehouse_user = self.create_access_user(username="warehouse-delete-orders", role=ROLE_ALMACEN)
        model_admin = OrderIncidentAdmin(OrderIncident, AdminSite())

        self.assertFalse(model_admin.has_delete_permission(type("Request", (), {"user": warehouse_user})()))

    def test_superuser_delete_is_allowed_in_admin(self):
        superuser = get_user_model().objects.create_superuser(
            username="super-delete-orders",
            email="super-delete-orders@example.com",
            password="secret123",
        )
        model_admin = OrderIncidentAdmin(OrderIncident, AdminSite())

        self.assertTrue(model_admin.has_delete_permission(type("Request", (), {"user": superuser})()))
