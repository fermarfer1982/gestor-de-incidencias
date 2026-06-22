from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from core.access import ROLE_ADMINISTRACION, ROLE_ALMACEN, ROLE_COMERCIAL
from core.models import UserAccessProfile, UserRepresentativeScope
from devoluciones.models import Representative, UserRepresentative


class HomeViewTests(TestCase):
    def add_group(self, user, group_name):
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)

    def add_profile(self, user, role, representatives=None, all_representatives=False):
        profile = UserAccessProfile.objects.create(
            user=user,
            role=role,
            all_representatives=all_representatives,
            active=True,
        )
        for representative in representatives or []:
            UserRepresentativeScope.objects.create(profile=profile, representative=representative, active=True)
        return profile

    def test_home_redirects_when_user_is_anonymous(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_superuser_without_representative_can_access_home(self):
        user = get_user_model().objects.create_superuser(
            username="admin-root",
            email="root@example.com",
            password="secret123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)

    def test_home_redirects_to_access_denied_without_valid_role(self):
        user = get_user_model().objects.create_user(
            username="user-no-rep",
            email="norep@example.com",
            password="secret123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertRedirects(response, reverse("access-denied"))

    def test_commercial_without_active_representative_is_denied(self):
        user = get_user_model().objects.create_user(
            username="commercial-no-rep",
            email="commercial-no-rep@example.com",
            password="secret123",
        )
        self.add_group(user, ROLE_COMERCIAL)
        self.add_profile(user, ROLE_COMERCIAL)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertRedirects(response, reverse("access-denied"))

    def test_home_is_accessible_with_active_representative(self):
        user = get_user_model().objects.create_user(
            username="user-with-rep",
            email="rep@example.com",
            password="secret123",
        )
        self.add_group(user, ROLE_COMERCIAL)
        representative = Representative.objects.create(code="REP001", name="Representante Uno")
        UserRepresentative.objects.create(user=user, representative=representative, active=True)
        self.add_profile(user, ROLE_COMERCIAL, representatives=[representative])
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)

    def test_administracion_without_representative_can_access_home(self):
        user = get_user_model().objects.create_user(
            username="admin-role",
            email="admin-role@example.com",
            password="secret123",
        )
        self.add_group(user, ROLE_ADMINISTRACION)
        self.add_profile(user, ROLE_ADMINISTRACION, all_representatives=True)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)

    def test_almacen_without_representative_can_access_home(self):
        user = get_user_model().objects.create_user(
            username="warehouse-role",
            email="warehouse-role@example.com",
            password="secret123",
        )
        self.add_group(user, ROLE_ALMACEN)
        self.add_profile(user, ROLE_ALMACEN, all_representatives=True)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)


class EmailLoginTests(TestCase):
    def test_user_can_login_with_email_backend(self):
        password = "secret123"
        get_user_model().objects.create_user(
            username="email-user",
            email="email@example.com",
            password=password,
        )

        response = self.client.post(
            reverse("login"),
            data={"username": "email@example.com", "password": password},
        )

        self.assertEqual(response.status_code, 302)
