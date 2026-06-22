import shutil
import tempfile
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.access import ROLE_ADMINISTRACION, ROLE_ALMACEN, ROLE_COMERCIAL
from core.models import UserAccessProfile, UserRepresentativeScope
from devoluciones.models import Representative, UserRepresentative
from erp.dtos import DeliveryNoteDTO, DeliveryNoteHeaderDTO, DeliveryNoteLineDTO
from transporte.admin import TransportIncidentAdmin
from transporte.models import (
    TransportCarrier,
    TransportIncident,
    TransportIncidentAttachment,
    TransportIncidentStatus,
    TransportIncidentType,
    TransportShipmentDirection,
)


@override_settings(DJANGO_USE_SQLITE=True)
class TransportIncidentFlowTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.commercial_group = Group.objects.create(name=ROLE_COMERCIAL)
        self.admin_group = Group.objects.create(name=ROLE_ADMINISTRACION)
        self.warehouse_group = Group.objects.create(name=ROLE_ALMACEN)
        self.user = get_user_model().objects.create_user(
            username="transport-user",
            email="transport-user@example.com",
            password="secret123",
        )
        self.user.groups.add(self.commercial_group)
        self.representative = Representative.objects.create(code="REP002", name="Representante Dos")
        UserRepresentative.objects.create(user=self.user, representative=self.representative, active=True)
        profile = UserAccessProfile.objects.create(
            user=self.user,
            role=ROLE_COMERCIAL,
            all_representatives=False,
            active=True,
        )
        UserRepresentativeScope.objects.create(profile=profile, representative=self.representative, active=True)
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

    def build_delivery_note(self, representative_code="REP002"):
        return DeliveryNoteDTO(
            header=DeliveryNoteHeaderDTO(
                delivery_note_number="ALB-100",
                delivery_note_date=date(2026, 3, 24),
                customer_name="Cliente Transporte",
                representative_code=representative_code,
            ),
            lines=[
                DeliveryNoteLineDTO(
                    delivery_note_line=1,
                    article_code="A1",
                    article_description="Articulo 1",
                    quantity=Decimal("1.00"),
                    sale_lot="L1",
                )
            ],
        )

    def base_form_data(self, *, has_delivery_note="no", representative_code=""):
        data = {
            "has_delivery_note": has_delivery_note,
            "description": "Caja golpeada en transporte",
            "carrier": TransportCarrier.MRW,
            "incident_type": TransportIncidentType.DAMAGED_GOODS,
            "shipment_direction": TransportShipmentDirection.SHIPMENT,
            "tracking_number": "TRK-1",
            "internal_reference": "INT-1",
            "country": "España",
            "province": "La Rioja",
            "municipality": "Calahorra",
            "sender": "Ramiro Arnedo",
            "recipient": "Cliente",
            "shipping_date": "2026-04-01",
            "incident_date": "2026-04-02",
        }
        if representative_code:
            data["representative_code"] = representative_code
        return data

    @patch("transporte.views.get_delivery_note_for_representative")
    def test_create_with_delivery_note_by_global_user(self, service_mock):
        warehouse = self.create_access_user(username="warehouse-transport", role=ROLE_ALMACEN)
        self.client.force_login(warehouse)
        service_mock.return_value = self.build_delivery_note()
        self.client.post(
            reverse("transport-incident-create"),
            data={"action": "search_delivery_note", "search-delivery_note_number": "ALB-100"},
        )

        response = self.client.post(
            reverse("transport-incident-create"),
            data=self.base_form_data(has_delivery_note="yes"),
        )

        incident = TransportIncident.objects.get()
        self.assertRedirects(response, reverse("transport-incident-detail", kwargs={"pk": incident.pk}))
        self.assertTrue(incident.has_delivery_note)
        self.assertEqual(incident.delivery_note_number, "ALB-100")
        self.assertEqual(incident.representative_code, self.representative.code)
        service_mock.assert_called_once_with(None, "ALB-100")

    @patch("transporte.views.get_delivery_note_for_representative")
    def test_create_with_delivery_note_by_restricted_user_inside_scope(self, service_mock):
        service_mock.return_value = self.build_delivery_note()
        self.client.post(
            reverse("transport-incident-create"),
            data={"action": "search_delivery_note", "search-delivery_note_number": "ALB-100"},
        )

        response = self.client.post(
            reverse("transport-incident-create"),
            data=self.base_form_data(has_delivery_note="yes"),
        )

        incident = TransportIncident.objects.get()
        self.assertRedirects(response, reverse("transport-incident-detail", kwargs={"pk": incident.pk}))
        self.assertEqual(incident.representative_code, self.representative.code)
        service_mock.assert_called_once_with(self.representative.code, "ALB-100")

    def test_create_with_delivery_note_outside_scope_is_blocked(self):
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        session = self.client.session
        session["transporte.delivery_note"] = {
            "header": {
                "delivery_note_number": "ALB-999",
                "delivery_note_date": "2026-04-01",
                "customer_name": "Cliente Fuera",
                "representative_code": other_representative.code,
            },
            "search_representative": {"code": other_representative.code, "name": other_representative.name},
        }
        session.save()

        response = self.client.post(
            reverse("transport-incident-create"),
            data=self.base_form_data(has_delivery_note="yes"),
        )

        self.assertRedirects(response, reverse("access-denied"))
        self.assertFalse(TransportIncident.objects.exists())

    def test_create_without_delivery_note_by_global_user(self):
        warehouse = self.create_access_user(username="warehouse-transport-no-note", role=ROLE_ALMACEN)
        self.client.force_login(warehouse)

        response = self.client.post(
            reverse("transport-incident-create"),
            data=self.base_form_data(has_delivery_note="no"),
        )

        incident = TransportIncident.objects.get()
        self.assertRedirects(response, reverse("transport-incident-detail", kwargs={"pk": incident.pk}))
        self.assertFalse(incident.has_delivery_note)
        self.assertIsNone(incident.representative_code)

    def test_create_without_delivery_note_restricted_user_requires_scoped_representative(self):
        response = self.client.post(
            reverse("transport-incident-create"),
            data=self.base_form_data(has_delivery_note="no"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Debes elegir un representante")

        response = self.client.post(
            reverse("transport-incident-create"),
            data=self.base_form_data(has_delivery_note="no", representative_code=self.representative.code),
        )
        incident = TransportIncident.objects.get()
        self.assertRedirects(response, reverse("transport-incident-detail", kwargs={"pk": incident.pk}))
        self.assertEqual(incident.representative_code, self.representative.code)

    def test_list_is_filtered_by_role_scope(self):
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        allowed = TransportIncident.objects.create(
            created_by=self.user,
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            description="Permitida",
            carrier=TransportCarrier.MRW,
            incident_type=TransportIncidentType.DELAY,
            shipment_direction=TransportShipmentDirection.SHIPMENT,
            tracking_number="1",
            internal_reference="1",
            province="La Rioja",
            municipality="Calahorra",
            sender="A",
            recipient="B",
            shipping_date=date(2026, 4, 1),
            incident_date=date(2026, 4, 2),
        )
        blocked = TransportIncident.objects.create(
            created_by=self.user,
            representative_code=other_representative.code,
            representative_name=other_representative.name,
            description="Bloqueada",
            carrier=TransportCarrier.GLS,
            incident_type=TransportIncidentType.DELAY,
            shipment_direction=TransportShipmentDirection.SHIPMENT,
            tracking_number="2",
            internal_reference="2",
            province="La Rioja",
            municipality="Calahorra",
            sender="A",
            recipient="B",
            shipping_date=date(2026, 4, 1),
            incident_date=date(2026, 4, 2),
        )

        response = self.client.get(reverse("transport-incidents"))

        self.assertContains(response, allowed.incident_number)
        self.assertNotContains(response, blocked.incident_number)

    def test_transport_csv_export_includes_transport_fields_and_respects_scope(self):
        other_representative = Representative.objects.create(code="REP999", name="Otro")
        TransportIncident.objects.create(
            created_by=self.user,
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            description="Permitida export",
            carrier=TransportCarrier.DHL,
            incident_type=TransportIncidentType.LOST_PACKAGE,
            shipment_direction=TransportShipmentDirection.SHIPMENT,
            tracking_number="TRACK-OK",
            internal_reference="REF-OK",
            resolution_notes="Localizado",
            province="La Rioja",
            municipality="Calahorra",
            sender="A",
            recipient="B",
            shipping_date=date(2026, 4, 1),
            incident_date=date(2026, 4, 2),
        )
        TransportIncident.objects.create(
            created_by=self.user,
            representative_code=other_representative.code,
            representative_name=other_representative.name,
            description="Bloqueada export",
            carrier=TransportCarrier.GLS,
            incident_type=TransportIncidentType.DELAY,
            shipment_direction=TransportShipmentDirection.SHIPMENT,
            tracking_number="TRACK-NO",
            internal_reference="REF-NO",
            province="La Rioja",
            municipality="Calahorra",
            sender="A",
            recipient="B",
            shipping_date=date(2026, 4, 1),
            incident_date=date(2026, 4, 2),
        )

        response = self.client.get(reverse("transport-incident-export", kwargs={"export_format": "csv"}))
        content = response.content.decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertIn("transportista", content)
        self.assertIn("tipo de incidencia", content)
        self.assertIn("DHL", content)
        self.assertIn("Bulto perdido", content)
        self.assertIn("TRACK-OK", content)
        self.assertIn("REF-OK", content)
        self.assertIn("Localizado", content)
        self.assertNotIn("TRACK-NO", content)

    def test_change_status_to_in_progress(self):
        incident = self.create_transport_incident_for_scope()

        response = self.client.post(
            reverse("transport-incident-detail", kwargs={"pk": incident.pk}),
            data={"status": TransportIncidentStatus.IN_PROGRESS, "resolution_notes": ""},
        )

        self.assertRedirects(response, reverse("transport-incident-detail", kwargs={"pk": incident.pk}))
        incident.refresh_from_db()
        self.assertEqual(incident.status, TransportIncidentStatus.IN_PROGRESS)

    def test_close_with_resolution_notes(self):
        incident = self.create_transport_incident_for_scope()

        response = self.client.post(
            reverse("transport-incident-detail", kwargs={"pk": incident.pk}),
            data={"status": TransportIncidentStatus.CLOSED, "resolution_notes": "Transportista indemniza el envío."},
        )

        self.assertRedirects(response, reverse("transport-incident-detail", kwargs={"pk": incident.pk}))
        incident.refresh_from_db()
        self.assertEqual(incident.status, TransportIncidentStatus.CLOSED)
        self.assertEqual(incident.closed_by, self.user)
        self.assertIsNotNone(incident.closed_at)

    def test_close_requires_resolution_notes(self):
        incident = self.create_transport_incident_for_scope()

        response = self.client.post(
            reverse("transport-incident-detail", kwargs={"pk": incident.pk}),
            data={"status": TransportIncidentStatus.CLOSED, "resolution_notes": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Debes indicar cómo se ha solucionado")
        incident.refresh_from_db()
        self.assertEqual(incident.status, TransportIncidentStatus.PENDING)

    def test_non_superuser_delete_is_denied_in_admin(self):
        warehouse = self.create_access_user(username="warehouse-transport-delete", role=ROLE_ALMACEN)
        model_admin = TransportIncidentAdmin(TransportIncident, AdminSite())

        self.assertFalse(model_admin.has_delete_permission(type("Request", (), {"user": warehouse})()))

    def test_printable_detail_is_available_inside_scope(self):
        incident = self.create_transport_incident_for_scope()
        incident.resolution_notes = "Resuelto transporte"
        incident.save(update_fields=["resolution_notes"])
        TransportIncidentAttachment.objects.create(
            incident=incident,
            file=SimpleUploadedFile("transporte.txt", b"contenido"),
            uploaded_by=self.user,
        )

        response = self.client.get(reverse("transport-incident-print", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incidencia de transporte")
        self.assertContains(response, "Resuelto transporte")
        self.assertContains(response, "transporte.txt")

    def test_pdf_detail_is_available_inside_scope(self):
        incident = self.create_transport_incident_for_scope()

        response = self.client.get(reverse("transport-incident-pdf", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_printable_detail_is_denied_outside_scope(self):
        incident = TransportIncident.objects.create(
            created_by=self.user,
            representative_code="REP999",
            representative_name="Otro",
            description="Bloqueada imprimir",
            carrier=TransportCarrier.GLS,
            incident_type=TransportIncidentType.DELAY,
            shipment_direction=TransportShipmentDirection.SHIPMENT,
            tracking_number="TRK-999",
            internal_reference="INT-999",
            province="La Rioja",
            municipality="Calahorra",
            sender="A",
            recipient="B",
            shipping_date=date(2026, 4, 1),
            incident_date=date(2026, 4, 2),
        )

        response = self.client.get(reverse("transport-incident-print", kwargs={"pk": incident.pk}))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(reverse("transport-incident-pdf", kwargs={"pk": incident.pk})).status_code, 404)

    def create_transport_incident_for_scope(self):
        return TransportIncident.objects.create(
            created_by=self.user,
            representative_code=self.representative.code,
            representative_name=self.representative.name,
            description="Incidencia",
            carrier=TransportCarrier.MRW,
            incident_type=TransportIncidentType.DELAY,
            shipment_direction=TransportShipmentDirection.SHIPMENT,
            tracking_number="TRK",
            internal_reference="INT",
            province="La Rioja",
            municipality="Calahorra",
            sender="A",
            recipient="B",
            shipping_date=date(2026, 4, 1),
            incident_date=date(2026, 4, 2),
        )
