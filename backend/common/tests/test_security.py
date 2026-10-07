"""Security regression tests use synthetic records and no live provider calls."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.journeys.models import Journey
from common.auth import DevUserAuthentication


class SecurityBoundaryTests(TestCase):
    @override_settings(DEBUG=False, DEV_AUTH_ENABLED=True, RUNNING_TESTS=False)
    def test_dev_identity_is_disabled_outside_debug_and_test_runner(self):
        self.assertIsNone(DevUserAuthentication().authenticate(None))
        self.assertFalse(get_user_model().objects.exists())

    def test_private_responses_are_not_cacheable_and_vary_by_identity(self):
        user = get_user_model().objects.create_user(username="synthetic-owner")
        journey = Journey.objects.create(user=user, title="Synthetic private record")
        client = APIClient()
        client.force_authenticate(user, token={"kind": "auth0"})
        for name, args in (("journey-list", []), ("journey-detail", [journey.pk]),
                           ("journey-state", [journey.pk])):
            with self.subTest(name=name):
                response = client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.get("Cache-Control", ""))
                self.assertIn("private", response.get("Cache-Control", ""))
                self.assertIn("Authorization", response.get("Vary", ""))
                self.assertIn("Cookie", response.get("Vary", ""))

    @override_settings(AUTH0_DOMAIN="tenant.example.auth0.com")
    def test_browser_policy_limits_scripts_and_data_destinations(self):
        response = self.client.get(reverse("demo"))
        policy = response.get("Content-Security-Policy", "")
        self.assertIn("script-src 'self'", policy)
        self.assertNotIn("'unsafe-inline'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("https://tenant.example.auth0.com", policy)
        self.assertIn("no-store", response.get("Cache-Control", ""))
        self.assertNotContains(response, 'src="https://cdn.auth0.com/')
        self.assertContains(response, "vendor/auth0-spa-js.production.js")

    def test_cross_account_access_is_blocked_on_all_private_read_routes(self):
        owner = get_user_model().objects.create_user(username="owner")
        attacker = get_user_model().objects.create_user(username="attacker")
        journey = Journey.objects.create(user=owner, title="Private")
        client = APIClient()
        client.force_authenticate(attacker, token={"kind": "auth0"})
        for name in ("journey-detail", "journey-guide", "breadcrumb-list", "journey-state",
                     "journey-stuck", "journey-responsible-organization", "journey-official-sources"):
            with self.subTest(name=name):
                self.assertEqual(client.get(reverse(name, args=[journey.pk])).status_code, 404)

    @override_settings(DEV_AUTH_ENABLED=False)
    def test_disabled_guest_cannot_read_private_records(self):
        from common.models import GuestSession

        client = APIClient()
        self.assertEqual(client.get(reverse("journey-list")).status_code, 200)
        user = GuestSession.objects.get().user
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertEqual(client.get(reverse("journey-list")).status_code, 401)
