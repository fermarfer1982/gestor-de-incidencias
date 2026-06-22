import shutil
import tempfile
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.access import ROLE_ADMINISTRACION, ROLE_ALMACEN, ROLE_COMERCIAL
from core.models import UserAccessProfile, UserRepresentativeScope
from devoluciones.admin import ReturnIncidentAdmin
from devoluciones.models import (
    IncidentAttachment,
    Representative,
    ReturnIncident,
    ReturnIncidentLine,
    ReturnIncidentStatus,
    UserRepresentative,
)
from devoluciones.services import create_return_incident
from erp.dtos import DeliveryNoteDTO, DeliveryNoteHeaderDTO, DeliveryNoteLineDTO


class DevolucionesUrlsTests(TestCase):
    def test_index_requires_login(self):
        response = self.client.get(reverse("devoluciones-index"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class ReturnIncidentModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="admin",
            email="admin@example.com",
            password="secret123",
        )
        self.representative = Representative.objects.create(code="REP001", name="Representante Uno")
        self.user_representative = UserRepresentative.objects.create(
            user=self.user,
            representative=self.representative,
            active=True,
        )

    def test_incident_number_is_generated_with_expected_format(self):
        incident = ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Demo",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Observacion",
            destination="Almacen central",
            status=ReturnIncidentStatus.PENDING,
            total_selected_lines=2,
        )

        year = timezone.now().year
        self.assertEqual(incident.incident_number, f"DEV-{year}-000001")

    def test_user_representative_string_is_readable(self):
        self.assertIn("REP001", str(self.user_representative))

    def test_representative_string_is_readable(self):
        self.assertEqual(str(self.representative), "REP001 - Representante Uno")

    def test_return_incident_line_string_is_readable(self):
        incident = ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Demo",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Observacion",
            destination="Almacen central",
            status=ReturnIncidentStatus.PENDING,
            total_selected_lines=1,
        )
        line = ReturnIncidentLine.objects.create(
            incident=incident,
            delivery_note_number="ALB-100",
            delivery_note_line=1,
            article_code="A1",
            article_description="Articulo 1",
            quantity_delivery_note=Decimal("5.00"),
            quantity_incident=Decimal("2.00"),
            sale_lot="L1",
        )

        self.assertIn("linea 1", str(line))


class LoadInitialRepresentativesCommandTests(TestCase):
    def test_command_creates_representatives_users_and_relationships(self):
        call_command("load_initial_representatives")

        self.assertEqual(Representative.objects.count(), 8)
        self.assertEqual(UserRepresentative.objects.count(), 18)
        self.assertTrue(Group.objects.filter(name=ROLE_COMERCIAL).exists())
        self.assertTrue(Group.objects.filter(name=ROLE_ADMINISTRACION).exists())
        self.assertTrue(
            UserRepresentative.objects.filter(
                user__email="eduardo.diaz@ramiroarnedo.com",
                representative__code="4",
                active=True,
            ).exists()
        )
        self.assertTrue(
            get_user_model()
            .objects.get(email="eduardo.diaz@ramiroarnedo.com")
            .groups.filter(name=ROLE_COMERCIAL)
            .exists()
        )

    def test_command_is_idempotent(self):
        call_command("load_initial_representatives")
        call_command("load_initial_representatives")

        self.assertEqual(Representative.objects.count(), 8)
        self.assertEqual(UserRepresentative.objects.count(), 18)


@override_settings(DJANGO_USE_SQLITE=True)
class ReturnIncidentServiceTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.user = get_user_model().objects.create_user(
            username="service-user",
            email="service@example.com",
            password="secret123",
        )
        self.representative = Representative.objects.create(code="REP010", name="Representante Servicio")

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_create_return_incident_persists_header_lines_and_attachments(self):
        incident = create_return_incident(
            user=self.user,
            representative=self.representative,
            delivery_note={
                "header": {
                    "delivery_note_number": "ALB-500",
                    "delivery_note_date": "2026-03-24",
                    "customer_name": "Cliente Servicio",
                },
                "lines": [],
            },
            selected_lines=[
                {
                    "delivery_note_line": 1,
                    "article_code": "A1",
                    "article_description": "Articulo 1",
                    "quantity": "4.00",
                    "quantity_incident": "2.00",
                    "sale_lot": "L1",
                }
            ],
            observations="Observaciones servicio",
            destination="Destino servicio",
            files=[SimpleUploadedFile("prueba.txt", b"contenido", content_type="text/plain")],
        )

        self.assertEqual(incident.created_by, self.user)
        self.assertEqual(incident.lines.count(), 1)
        self.assertEqual(incident.attachments.count(), 1)
        self.assertEqual(incident.total_selected_lines, 1)

    def test_attachment_string_is_readable(self):
        incident = create_return_incident(
            user=self.user,
            representative=self.representative,
            delivery_note={
                "header": {
                    "delivery_note_number": "ALB-501",
                    "delivery_note_date": "2026-03-24",
                    "customer_name": "Cliente Servicio",
                },
                "lines": [],
            },
            selected_lines=[
                {
                    "delivery_note_line": 1,
                    "article_code": "A1",
                    "article_description": "Articulo 1",
                    "quantity": "4.00",
                    "quantity_incident": "2.00",
                    "sale_lot": "L1",
                }
            ],
            observations="Obs",
            destination="Destino",
            files=[SimpleUploadedFile("adjunto.txt", b"contenido", content_type="text/plain")],
        )

        attachment = incident.attachments.get()
        self.assertIn(incident.incident_number, str(attachment))

    def test_create_return_incident_requires_selected_lines(self):
        with self.assertRaises(ValidationError):
            create_return_incident(
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
                observations="Obs",
                destination="Destino",
                files=[],
            )

    def test_create_return_incident_blocks_duplicate_open_incident_for_same_delivery_note_lines(self):
        create_return_incident(
            user=self.user,
            representative=self.representative,
            delivery_note={
                "header": {
                    "delivery_note_number": "ALB-777",
                    "delivery_note_date": "2026-03-24",
                    "customer_name": "Cliente Duplicado",
                },
                "lines": [],
            },
            selected_lines=[
                {
                    "delivery_note_line": 1,
                    "article_code": "A1",
                    "article_description": "Articulo 1",
                    "quantity": "4.00",
                    "quantity_incident": "2.00",
                    "sale_lot": "L1",
                }
            ],
            observations="Primera",
            destination="Destino",
            files=[],
        )

        with self.assertRaises(ValidationError):
            create_return_incident(
                user=self.user,
                representative=self.representative,
                delivery_note={
                    "header": {
                        "delivery_note_number": "ALB-777",
                        "delivery_note_date": "2026-03-24",
                        "customer_name": "Cliente Duplicado",
                    },
                    "lines": [],
                },
                selected_lines=[
                    {
                        "delivery_note_line": 1,
                        "article_code": "A1",
                        "article_description": "Articulo 1",
                        "quantity": "4.00",
                        "quantity_incident": "1.00",
                        "sale_lot": "L1",
                    }
                ],
                observations="Segunda",
                destination="Destino",
                files=[],
            )

    def test_create_return_incident_allows_same_delivery_note_lines_when_previous_is_closed(self):
        incident = create_return_incident(
            user=self.user,
            representative=self.representative,
            delivery_note={
                "header": {
                    "delivery_note_number": "ALB-778",
                    "delivery_note_date": "2026-03-24",
                    "customer_name": "Cliente Cerrado",
                },
                "lines": [],
            },
            selected_lines=[
                {
                    "delivery_note_line": 1,
                    "article_code": "A1",
                    "article_description": "Articulo 1",
                    "quantity": "4.00",
                    "quantity_incident": "2.00",
                    "sale_lot": "L1",
                }
            ],
            observations="Primera",
            destination="Destino",
            files=[],
        )
        incident.status = ReturnIncidentStatus.CLOSED
        incident.save(update_fields=["status"])

        new_incident = create_return_incident(
            user=self.user,
            representative=self.representative,
            delivery_note={
                "header": {
                    "delivery_note_number": "ALB-778",
                    "delivery_note_date": "2026-03-24",
                    "customer_name": "Cliente Cerrado",
                },
                "lines": [],
            },
            selected_lines=[
                {
                    "delivery_note_line": 1,
                    "article_code": "A1",
                    "article_description": "Articulo 1",
                    "quantity": "4.00",
                    "quantity_incident": "1.00",
                    "sale_lot": "L1",
                }
            ],
            observations="Segunda",
            destination="Destino",
            files=[],
        )

        self.assertNotEqual(incident.pk, new_incident.pk)


@override_settings(DJANGO_USE_SQLITE=True)
class DeliveryNoteFlowTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

        self.user = get_user_model().objects.create_user(
            username="user-search",
            email="search@example.com",
            password="secret123",
        )
        self.commercial_group = Group.objects.create(name=ROLE_COMERCIAL)
        self.admin_group = Group.objects.create(name=ROLE_ADMINISTRACION)
        self.warehouse_group = Group.objects.create(name=ROLE_ALMACEN)
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

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def build_delivery_note(self):
        return DeliveryNoteDTO(
            header=DeliveryNoteHeaderDTO(
                delivery_note_number="ALB-100",
                delivery_note_date=date(2026, 3, 24),
                customer_name="Cliente Demo",
                representative_code="REP002",
                customer_fiscal_address="Fiscal Demo",
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

    def build_delivery_note_with_datetime(self):
        return DeliveryNoteDTO(
            header=DeliveryNoteHeaderDTO(
                delivery_note_number="143071",
                delivery_note_date=datetime(2026, 3, 25, 10, 30, 0),
                customer_name="Cliente Datetime",
                representative_code="REP002",
                customer_fiscal_address="Fiscal Datetime",
            ),
            lines=[
                DeliveryNoteLineDTO(
                    delivery_note_line=1,
                    article_code="A1",
                    article_description="Articulo 1",
                    quantity=Decimal("5.00"),
                    sale_lot="L1",
                ),
            ],
        )

    def test_search_redirects_to_access_denied_without_active_representative(self):
        UserRepresentativeScope.objects.filter(profile=self.user_profile).update(active=False)

        response = self.client.get(reverse("devoluciones-index"))

        self.assertRedirects(response, reverse("access-denied"))

    def test_dashboard_view_is_accessible_with_active_representative(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard de incidencias")

    def test_commercial_incidents_list_shows_representative_incidents(self):
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Propio",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        other_user = get_user_model().objects.create_user(
            username="other-list",
            email="other-list@example.com",
            password="secret123",
        )
        ReturnIncident.objects.create(
            created_by=other_user,
            delivery_note_number="ALB-101",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Mismo Representante",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        ReturnIncident.objects.create(
            created_by=other_user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Ajeno",
            representative_code="REP999",
            representative_name="Otro",
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )

        response = self.client.get(reverse("my-return-incidents"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Propio")
        self.assertContains(response, "Cliente Mismo Representante")
        self.assertNotContains(response, "Cliente Ajeno")

    def test_return_csv_export_respects_scope_and_status_filter(self):
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Export Permitido",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            status=ReturnIncidentStatus.CLOSED,
            resolution_notes="Resuelta",
            total_selected_lines=1,
        )
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-101",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Export Abierta",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            status=ReturnIncidentStatus.PENDING,
            total_selected_lines=1,
        )
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Export Bloqueado",
            representative_code="REP999",
            representative_name="Otro",
            observations="Obs",
            destination="Destino",
            status=ReturnIncidentStatus.CLOSED,
            total_selected_lines=1,
        )

        response = self.client.get(
            reverse("return-incident-export", kwargs={"export_format": "csv"}),
            {"status": "closed"},
        )
        content = response.content.decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertIn("incidencias_devoluciones.csv", response["Content-Disposition"])
        self.assertIn("Cliente Export Permitido", content)
        self.assertIn("devoluciones", content)
        self.assertIn("Resuelta", content)
        self.assertNotIn("Cliente Export Abierta", content)
        self.assertNotIn("Cliente Export Bloqueado", content)

    def test_administracion_incidents_list_shows_all_incidents(self):
        admin_user = self.create_access_user(
            username="admin-list",
            role=ROLE_ADMINISTRACION,
            all_representatives=True,
        )
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Comercial",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        ReturnIncident.objects.create(
            created_by=admin_user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Otro Rep",
            representative_code=other_representative.code,
            representative_name=other_representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("my-return-incidents"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Comercial")
        self.assertContains(response, "Cliente Otro Rep")

    def test_administracion_with_one_representative_only_sees_that_representative(self):
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        admin_user = self.create_access_user(
            username="admin-one-rep",
            role=ROLE_ADMINISTRACION,
            representatives=[self.representative],
        )
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Permitido",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente No Permitido",
            representative_code=other_representative.code,
            representative_name=other_representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("my-return-incidents"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Permitido")
        self.assertNotContains(response, "Cliente No Permitido")

    def test_comercial_with_all_representatives_true_is_still_restricted(self):
        self.user_profile.all_representatives = True
        self.user_profile.save(update_fields=["all_representatives"])
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Permitido",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente No Permitido",
            representative_code=other_representative.code,
            representative_name=other_representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )

        response = self.client.get(reverse("my-return-incidents"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Permitido")
        self.assertNotContains(response, "Cliente No Permitido")

    def test_administracion_with_multiple_representatives_sees_those_representatives(self):
        second_representative = Representative.objects.create(code="REP003", name="Tres")
        third_representative = Representative.objects.create(code="REP999", name="Otro")
        admin_user = self.create_access_user(
            username="admin-multi-rep",
            role=ROLE_ADMINISTRACION,
            representatives=[self.representative, second_representative],
        )
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Rep Uno",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-101",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Rep Dos",
            representative_code=second_representative.code,
            representative_name=second_representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Rep Tres",
            representative_code=third_representative.code,
            representative_name=third_representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("my-return-incidents"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Rep Uno")
        self.assertContains(response, "Cliente Rep Dos")
        self.assertNotContains(response, "Cliente Rep Tres")

    def test_almacen_incidents_list_shows_all_incidents(self):
        warehouse_user = self.create_access_user(
            username="warehouse-list",
            role=ROLE_ALMACEN,
            all_representatives=True,
        )
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Comercial",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        ReturnIncident.objects.create(
            created_by=warehouse_user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Almacen Global",
            representative_code=other_representative.code,
            representative_name=other_representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        self.client.force_login(warehouse_user)

        response = self.client.get(reverse("my-return-incidents"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Comercial")
        self.assertContains(response, "Cliente Almacen Global")

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_search_uses_authenticated_user_context(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()

        response = self.client.post(
            reverse("devoluciones-index"),
            data={"delivery_note_number": "ALB-100", "representative_code": "REP999"},
        )

        self.assertRedirects(response, reverse("delivery-note-result"))
        get_delivery_note_for_representative_mock.assert_called_once_with(self.representative.code, "ALB-100")

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_search_shows_clear_message_when_delivery_note_not_found(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = None

        response = self.client.post(
            reverse("devoluciones-index"),
            data={"delivery_note_number": "ALB-404"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No se ha encontrado el albarán para el representante indicado")

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_search_persists_delivery_note_with_datetime_in_session(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note_with_datetime()

        response = self.client.post(
            reverse("devoluciones-index"),
            data={"delivery_note_number": "143071"},
        )

        self.assertRedirects(response, reverse("delivery-note-result"))
        session = self.client.session
        self.assertEqual(session["devoluciones.delivery_note"]["header"]["delivery_note_date"], "2026-03-25T10:30:00")
        result_response = self.client.get(reverse("delivery-note-result"))
        self.assertEqual(result_response.status_code, 200)
        self.assertContains(result_response, "Cliente Datetime")

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_superuser_can_search_without_choosing_representative(self, get_delivery_note_for_representative_mock):
        superuser = get_user_model().objects.create_superuser(
            username="super-admin",
            email="super@example.com",
            password="secret123",
        )
        self.client.force_login(superuser)
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()

        response = self.client.post(
            reverse("devoluciones-index"),
            data={"delivery_note_number": "ALB-100"},
        )

        self.assertRedirects(response, reverse("delivery-note-result"))
        get_delivery_note_for_representative_mock.assert_called_once_with(None, "ALB-100")

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_almacen_can_search_without_choosing_representative(self, get_delivery_note_for_representative_mock):
        warehouse_user = self.create_access_user(username="warehouse-search", role=ROLE_ALMACEN)
        self.client.force_login(warehouse_user)
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()

        response = self.client.post(
            reverse("devoluciones-index"),
            data={"delivery_note_number": "ALB-100"},
        )

        self.assertRedirects(response, reverse("delivery-note-result"))
        get_delivery_note_for_representative_mock.assert_called_once_with(None, "ALB-100")

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_superuser_can_search_choosing_representative(self, get_delivery_note_for_representative_mock):
        superuser = get_user_model().objects.create_superuser(
            username="super-admin-ok",
            email="super-ok@example.com",
            password="secret123",
        )
        self.client.force_login(superuser)
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()

        response = self.client.post(
            reverse("devoluciones-index"),
            data={"representative_code": self.representative.code, "delivery_note_number": "ALB-100"},
        )

        self.assertRedirects(response, reverse("delivery-note-result"))
        get_delivery_note_for_representative_mock.assert_called_once_with(self.representative.code, "ALB-100")

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_full_flow_creates_incident_lines_and_attachments(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()

        search_response = self.client.post(
            reverse("devoluciones-index"),
            data={"delivery_note_number": "ALB-100"},
        )
        self.assertRedirects(search_response, reverse("delivery-note-result"))

        result_response = self.client.get(reverse("delivery-note-result"))
        self.assertEqual(result_response.status_code, 200)
        self.assertTemplateUsed(result_response, "devoluciones/result.html")
        self.assertContains(result_response, "Cliente Demo")
        self.assertContains(result_response, "ALB-100")
        self.assertContains(result_response, "24/03/2026")
        self.assertContains(result_response, "Articulo 1")
        self.assertContains(result_response, "Resumen de selección")
        self.assertContains(result_response, "Fiscal Demo")

        selection_response = self.client.post(
            reverse("delivery-note-result"),
            data={
                "selected_lines": ["0", "1"],
                "quantity_incident_0": "2.00",
                "quantity_incident_1": "1.00",
            },
        )
        self.assertRedirects(selection_response, reverse("return-incident-create"))
        session = self.client.session
        self.assertEqual(len(session["devoluciones.selected_lines"]), 2)
        self.assertEqual(session["devoluciones.selected_lines"][0]["quantity_incident"], "2.00")

        create_response = self.client.get(reverse("return-incident-create"))
        self.assertEqual(create_response.status_code, 200)
        self.assertContains(create_response, "Líneas seleccionadas")

        file_one = SimpleUploadedFile("foto1.txt", b"adjunto 1", content_type="text/plain")
        file_two = SimpleUploadedFile("foto2.txt", b"adjunto 2", content_type="text/plain")
        create_post_response = self.client.post(
            reverse("return-incident-create"),
            data={
                "observations": "Mercancía dañada",
                "destination": "Delegación-Almería",
                "attachments": [file_one, file_two],
            },
        )

        incident = ReturnIncident.objects.get()
        self.assertRedirects(
            create_post_response,
            reverse("return-incident-detail", kwargs={"pk": incident.pk}),
        )
        self.assertEqual(incident.created_by, self.user)
        self.assertEqual(incident.customer_name, "Cliente Demo")
        self.assertEqual(incident.total_selected_lines, 2)
        self.assertEqual(incident.lines.count(), 2)
        self.assertEqual(incident.attachments.count(), 2)
        self.assertEqual(IncidentAttachment.objects.count(), 2)

        detail_response = self.client.get(reverse("return-incident-detail", kwargs={"pk": incident.pk}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, incident.incident_number)
        self.assertContains(detail_response, "Mercancía dañada")
        self.assertContains(detail_response, "Adjuntos")
        self.assertContains(detail_response, "Cliente Demo")
        self.assertContains(detail_response, "Fiscal Demo")
        self.assertContains(detail_response, "Delegación-Almería")
        self.assertContains(detail_response, "A1")
        self.assertContains(detail_response, "foto1")

        list_response = self.client.get(reverse("my-return-incidents"))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, incident.incident_number)

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_create_incident_keeps_date_when_delivery_note_header_comes_as_datetime(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note_with_datetime()

        self.client.post(reverse("devoluciones-index"), data={"delivery_note_number": "143071"})
        self.client.post(
            reverse("delivery-note-result"),
            data={
                "selected_lines": ["0"],
                "quantity_incident_0": "2.00",
            },
        )
        response = self.client.post(
            reverse("return-incident-create"),
            data={
                "observations": "Fecha datetime",
                "destination": "Delegación-Almería",
            },
        )

        incident = ReturnIncident.objects.get()
        self.assertRedirects(response, reverse("return-incident-detail", kwargs={"pk": incident.pk}))
        self.assertEqual(str(incident.delivery_note_date), "2026-03-25")

    def test_create_incident_revalidates_representative_from_session(self):
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        session = self.client.session
        session["devoluciones.delivery_note"] = {
            "header": {
                "delivery_note_number": "ALB-999",
                "delivery_note_date": "2026-03-24",
                "customer_name": "Cliente Manipulado",
                "customer_fiscal_address": "",
                "representative_code": other_representative.code,
            },
            "lines": [
                {
                    "delivery_note_line": 1,
                    "article_code": "A1",
                    "article_description": "Articulo 1",
                    "quantity": "5.00",
                    "sale_lot": "L1",
                    "unit_of_measure": "",
                    "packaging": "",
                }
            ],
            "search_representative": {
                "code": other_representative.code,
                "name": other_representative.name,
            },
        }
        session["devoluciones.selected_lines"] = [
            {
                "delivery_note_line": 1,
                "article_code": "A1",
                "article_description": "Articulo 1",
                "quantity": "5.00",
                "quantity_incident": "1.00",
                "sale_lot": "L1",
                "unit_of_measure": "",
                "packaging": "",
            }
        ]
        session.save()

        response = self.client.post(
            reverse("return-incident-create"),
            data={
                "observations": "Intento fuera de alcance",
                "destination": "Delegación-Almería",
            },
        )

        self.assertRedirects(response, reverse("access-denied"))
        self.assertFalse(ReturnIncident.objects.filter(customer_name="Cliente Manipulado").exists())

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_result_view_requires_previous_search(self, _get_delivery_note_for_representative_mock):
        self.client.session.flush()
        self.client.force_login(self.user)

        response = self.client.get(reverse("delivery-note-result"))

        self.assertRedirects(response, reverse("devoluciones-index"))

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_create_view_requires_selected_lines(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()
        self.client.post(reverse("devoluciones-index"), data={"delivery_note_number": "ALB-100"})

        response = self.client.get(reverse("return-incident-create"))

        self.assertRedirects(response, reverse("delivery-note-result"))

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_selection_validates_quantity_against_delivery_note(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()
        self.client.post(reverse("devoluciones-index"), data={"delivery_note_number": "ALB-100"})

        response = self.client.post(
            reverse("delivery-note-result"),
            data={
                "selected_lines": ["0"],
                "quantity_incident_0": "99.00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no puede superar la cantidad del albarán")

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_selection_requires_at_least_one_checked_line(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()
        self.client.post(reverse("devoluciones-index"), data={"delivery_note_number": "ALB-100"})

        response = self.client.post(reverse("delivery-note-result"), data={})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Debes seleccionar al menos una línea")

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_selection_requires_quantity_for_selected_line(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()
        self.client.post(reverse("devoluciones-index"), data={"delivery_note_number": "ALB-100"})

        response = self.client.post(
            reverse("delivery-note-result"),
            data={
                "selected_lines": ["0"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Indica la cantidad de incidencia")

    def test_commercial_incident_detail_shows_same_representative_records(self):
        other_user = get_user_model().objects.create_user(
            username="other-user",
            email="other@example.com",
            password="secret123",
        )
        incident = ReturnIncident.objects.create(
            created_by=other_user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Mismo Representante",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )

        response = self.client.get(reverse("return-incident-detail", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Mismo Representante")

    def test_commercial_incident_detail_hides_other_representative_records(self):
        other_user = get_user_model().objects.create_user(
            username="other-user-other-rep",
            email="other-rep@example.com",
            password="secret123",
        )
        incident = ReturnIncident.objects.create(
            created_by=other_user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Otro Representante",
            representative_code="REP999",
            representative_name="Otro Rep",
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )

        response = self.client.get(reverse("return-incident-detail", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 404)

    def test_printable_detail_is_available_inside_scope(self):
        incident = ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Imprimible",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs imprimible",
            destination="Delegación-Almería",
            resolution_notes="Resuelto",
            total_selected_lines=1,
        )
        ReturnIncidentLine.objects.create(
            incident=incident,
            delivery_note_number="ALB-100",
            delivery_note_line=1,
            article_code="A1",
            article_description="Articulo 1",
            quantity_delivery_note=Decimal("5.00"),
            quantity_incident=Decimal("2.00"),
            sale_lot="L1",
        )
        IncidentAttachment.objects.create(
            incident=incident,
            file=SimpleUploadedFile("devolucion.txt", b"contenido"),
            uploaded_by=self.user,
        )

        response = self.client.get(reverse("return-incident-print", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incidencia de devolución")
        self.assertContains(response, "Cliente Imprimible")
        self.assertContains(response, "devolucion.txt")

    def test_pdf_detail_is_available_inside_scope(self):
        incident = ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente PDF",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Delegación-Almería",
            total_selected_lines=0,
        )

        response = self.client.get(reverse("return-incident-pdf", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_printable_detail_is_denied_outside_scope(self):
        incident = ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Bloqueado Imprimir",
            representative_code="REP999",
            representative_name="Otro Rep",
            observations="Obs",
            destination="Delegación-Almería",
            total_selected_lines=0,
        )

        response = self.client.get(reverse("return-incident-print", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(reverse("return-incident-pdf", kwargs={"pk": incident.pk})).status_code, 404)

    def test_administracion_incident_detail_shows_any_representative_record(self):
        admin_user = self.create_access_user(
            username="admin-detail",
            role=ROLE_ADMINISTRACION,
            all_representatives=True,
        )
        incident = ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Global",
            representative_code="REP999",
            representative_name="Otro Rep",
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("return-incident-detail", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente Global")

    def test_change_status_from_open_to_in_progress(self):
        incident = ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Estado",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )

        response = self.client.post(
            reverse("return-incident-detail", kwargs={"pk": incident.pk}),
            data={
                "status": ReturnIncidentStatus.IN_PROGRESS,
                "resolution_notes": "",
            },
        )

        self.assertRedirects(response, reverse("return-incident-detail", kwargs={"pk": incident.pk}))
        incident.refresh_from_db()
        self.assertEqual(incident.status, ReturnIncidentStatus.IN_PROGRESS)
        self.assertIsNone(incident.closed_at)
        self.assertIsNone(incident.closed_by)

    def test_close_with_resolution_notes_updates_traceability(self):
        incident = ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Cierre",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )

        response = self.client.post(
            reverse("return-incident-detail", kwargs={"pk": incident.pk}),
            data={
                "status": ReturnIncidentStatus.CLOSED,
                "resolution_notes": "Se recibió la mercancía y se cerró la devolución.",
            },
        )

        self.assertRedirects(response, reverse("return-incident-detail", kwargs={"pk": incident.pk}))
        incident.refresh_from_db()
        self.assertEqual(incident.status, ReturnIncidentStatus.CLOSED)
        self.assertEqual(incident.resolution_notes, "Se recibió la mercancía y se cerró la devolución.")
        self.assertIsNotNone(incident.closed_at)
        self.assertEqual(incident.closed_by, self.user)

    def test_close_requires_resolution_notes(self):
        incident = ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-100",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Sin Resolucion",
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )

        response = self.client.post(
            reverse("return-incident-detail", kwargs={"pk": incident.pk}),
            data={
                "status": ReturnIncidentStatus.CLOSED,
                "resolution_notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Debes indicar cómo se ha solucionado")
        incident.refresh_from_db()
        self.assertEqual(incident.status, ReturnIncidentStatus.PENDING)
        self.assertIsNone(incident.closed_at)
        self.assertIsNone(incident.closed_by)

    def test_status_update_outside_representative_scope_is_blocked(self):
        incident = ReturnIncident.objects.create(
            created_by=self.user,
            delivery_note_number="ALB-999",
            delivery_note_date=timezone.localdate(),
            customer_name="Cliente Fuera Alcance",
            representative_code="REP999",
            representative_name="Otro Rep",
            observations="Obs",
            destination="Destino",
            total_selected_lines=1,
        )

        response = self.client.post(
            reverse("return-incident-detail", kwargs={"pk": incident.pk}),
            data={
                "status": ReturnIncidentStatus.IN_PROGRESS,
                "resolution_notes": "",
            },
        )

        self.assertEqual(response.status_code, 404)
        incident.refresh_from_db()
        self.assertEqual(incident.status, ReturnIncidentStatus.PENDING)

    def test_non_superuser_delete_is_denied_in_admin(self):
        warehouse_user = self.create_access_user(
            username="warehouse-delete",
            role=ROLE_ALMACEN,
            all_representatives=True,
        )
        model_admin = ReturnIncidentAdmin(ReturnIncident, AdminSite())

        self.assertFalse(model_admin.has_delete_permission(type("Request", (), {"user": warehouse_user})()))

    def test_superuser_delete_is_allowed_in_admin(self):
        superuser = get_user_model().objects.create_superuser(
            username="super-delete",
            email="super-delete@example.com",
            password="secret123",
        )
        model_admin = ReturnIncidentAdmin(ReturnIncident, AdminSite())

        self.assertTrue(model_admin.has_delete_permission(type("Request", (), {"user": superuser})()))

    @patch("devoluciones.views.get_delivery_note_for_representative")
    def test_full_flow_blocks_duplicate_open_incident(self, get_delivery_note_for_representative_mock):
        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()

        self.client.post(reverse("devoluciones-index"), data={"delivery_note_number": "ALB-100"})
        self.client.post(
            reverse("delivery-note-result"),
            data={
                "selected_lines": ["0"],
                "quantity_incident_0": "2.00",
            },
        )
        self.client.post(
            reverse("return-incident-create"),
            data={
                "observations": "Primera incidencia",
                "destination": "Delegación-Almería",
            },
        )

        get_delivery_note_for_representative_mock.return_value = self.build_delivery_note()
        self.client.post(reverse("devoluciones-index"), data={"delivery_note_number": "ALB-100"})
        self.client.post(
            reverse("delivery-note-result"),
            data={
                "selected_lines": ["0"],
                "quantity_incident_0": "1.00",
            },
        )
        response = self.client.post(
            reverse("return-incident-create"),
            data={
                "observations": "Duplicada",
                "destination": "Delegación-Almería",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe una incidencia abierta para este albarán")
