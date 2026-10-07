import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.journeys.models import Journey
from common.models import GuestSession


def post_json(client, url, payload):
    return client.post(url, json.dumps(payload), content_type="application/json")


@override_settings(DEV_AUTH_ENABLED=False)
class GuestAccessTests(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(GUEST_MAX_ACTIVE_JOURNEYS=1)
    def test_reopening_an_archive_respects_quota_and_rolls_back(self):
        client = APIClient()
        first = post_json(client, reverse("journey-list"), {"title": "One"}).json()["id"]
        url = reverse("journey-detail", args=[first])
        self.assertEqual(client.patch(url, {"status": "ARCHIVED"}, format="json").json()["status"], "ARCHIVED")
        self.assertEqual(post_json(client, reverse("journey-list"), {"title": "Two"}).status_code, 201)
        blocked = client.patch(url, {"status": "ACTIVE", "title": "Changed"}, format="json")
        self.assertEqual(blocked.status_code, 409)
        journey = Journey.objects.get(pk=first)
        self.assertEqual(journey.status, "ARCHIVED")
        self.assertEqual(journey.title, "One")

    def test_guests_are_isolated_by_server_session(self):
        first, second = APIClient(), APIClient()
        created = post_json(first, reverse("journey-list"), {"title": "Private", "goal": "A"})
        self.assertEqual(created.status_code, 201)
        journey_id = created.json()["id"]
        self.assertEqual(second.get(reverse("journey-detail", args=[journey_id])).status_code, 404)
        self.assertEqual(second.get(reverse("journey-list")).json()["results"], [])

    def test_guest_cookie_writes_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        blocked = post_json(client, reverse("journey-list"), {"title": "Blocked"})
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(GuestSession.objects.count(), 0)
        self.assertEqual(get_user_model().objects.count(), 0)

        token = client.get(reverse("auth-csrf")).json()["csrf_token"]
        allowed = client.post(
            reverse("journey-list"),
            json.dumps({"title": "Allowed"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(allowed.status_code, 201)

    @override_settings(GUEST_MAX_ACTIVE_JOURNEYS=1)
    def test_guest_can_have_only_one_active_journey(self):
        client = APIClient()
        self.assertEqual(post_json(client, reverse("journey-list"), {"title": "One"}).status_code, 201)
        blocked = post_json(client, reverse("journey-list"), {"title": "Two"})
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["error"]["code"], "JOURNEY_LIMIT_REACHED")

    def test_expired_guest_data_is_deleted_and_not_reused(self):
        client = APIClient()
        created = post_json(client, reverse("journey-list"), {"title": "Temporary"})
        journey_id = created.json()["id"]
        guest = GuestSession.objects.get()
        guest.expires_at = timezone.now() - timedelta(seconds=1)
        guest.save(update_fields=["expires_at"])
        self.assertEqual(client.get(reverse("journey-detail", args=[journey_id])).status_code, 404)
        self.assertFalse(Journey.objects.filter(pk=journey_id).exists())

    @override_settings(
        GUEST_AI_REQUESTS_PER_MINUTE=100,
        GUEST_AI_DAILY_LIMIT=2,
        GLOBAL_AI_DAILY_LIMIT=100,
    )
    def test_guest_ai_allowance_is_independent_from_journey_limit(self):
        client = APIClient()
        journey_id = post_json(client, reverse("journey-list"), {"title": "One"}).json()["id"]
        url = reverse("breadcrumb-interpret", args=[journey_id])
        payload = {"text": "I called IRCC and they said it is still processing."}
        self.assertEqual(post_json(client, url, payload).status_code, 200)
        self.assertEqual(post_json(client, url, payload).status_code, 200)
        self.assertEqual(post_json(client, url, payload).status_code, 429)

    @override_settings(
        GUEST_AI_REQUESTS_PER_MINUTE=100,
        GUEST_AI_DAILY_LIMIT=100,
        GLOBAL_AI_DAILY_LIMIT=2,
    )
    def test_global_ai_limit_protects_the_shared_project(self):
        clients_and_journeys = []
        for title in ("First", "Second", "Third"):
            client = APIClient()
            journey_id = post_json(client, reverse("journey-list"), {"title": title}).json()["id"]
            clients_and_journeys.append((client, journey_id))
        statuses = []
        for client, journey_id in clients_and_journeys:
            statuses.append(
                post_json(
                    client,
                    reverse("breadcrumb-interpret", args=[journey_id]),
                    {"text": "I called IRCC today."},
                ).status_code
            )
        self.assertEqual(statuses, [200, 200, 429])


@override_settings(DEV_AUTH_ENABLED=False, USER_MAX_ACTIVE_JOURNEYS=2)
class AccountQuotaAndMigrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="account", password=None)

    def account_client(self):
        client = APIClient()
        client.force_authenticate(self.user, token={"kind": "auth0"})
        return client

    def test_authenticated_quota_is_configurable(self):
        client = self.account_client()
        for title in ("One", "Two"):
            self.assertEqual(post_json(client, reverse("journey-list"), {"title": title}).status_code, 201)
        self.assertEqual(post_json(client, reverse("journey-list"), {"title": "Three"}).status_code, 409)

    def test_guest_migration_is_idempotent_and_does_not_duplicate(self):
        client = APIClient()
        created = post_json(client, reverse("journey-list"), {"title": "Guest work"})
        journey_id = created.json()["id"]
        client.force_authenticate(self.user, token={"kind": "auth0"})
        first = client.post(reverse("auth-migrate-guest"))
        second = client.post(reverse("auth-migrate-guest"))
        self.assertEqual(first.json()["status"], "migrated")
        self.assertEqual(second.json()["status"], "already_migrated")
        self.assertEqual(Journey.objects.filter(pk=journey_id, user=self.user).count(), 1)
        self.assertEqual(Journey.objects.filter(user=self.user).count(), 1)

    @override_settings(USER_MAX_ACTIVE_JOURNEYS=1)
    def test_full_account_preserves_guest_journey_for_retry(self):
        Journey.objects.create(user=self.user, title="Existing", goal="")
        client = APIClient()
        created = post_json(client, reverse("journey-list"), {"title": "Guest work"})
        journey_id = created.json()["id"]
        guest_owner_id = Journey.objects.get(pk=journey_id).user_id
        client.force_authenticate(self.user, token={"kind": "auth0"})
        blocked = client.post(reverse("auth-migrate-guest"))
        self.assertEqual(blocked.status_code, 409)
        self.assertTrue(blocked.json()["error"]["guest_data_preserved"])
        self.assertEqual(Journey.objects.get(pk=journey_id).user_id, guest_owner_id)

    def test_authenticated_user_cannot_read_or_write_another_account_journey(self):
        other = get_user_model().objects.create_user(username="other", password=None)
        journey = Journey.objects.create(user=other, title="Other", goal="private")
        client = self.account_client()
        url = reverse("journey-detail", args=[journey.id])
        self.assertEqual(client.get(url).status_code, 404)
        self.assertEqual(client.patch(url, {"title": "stolen"}, format="json").status_code, 404)


@override_settings(
    DEV_AUTH_ENABLED=False,
    AUTH0_DOMAIN="tenant.example.auth0.com",
    AUTH0_ISSUER="https://tenant.example.auth0.com/",
    AUTH0_AUDIENCE="https://api.civic.test",
)
class Auth0JWTTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_key = cls.private_key.public_key()

    def token(self, **overrides):
        now = timezone.now()
        claims = {
            "iss": "https://tenant.example.auth0.com/",
            "aud": "https://api.civic.test",
            "sub": "google-oauth2|opaque-auth0-subject",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        }
        claims.update(overrides)
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": "test"})

    def request(self, token):
        client = APIClient()
        with patch(
            "jwt.PyJWKClient.get_signing_key_from_jwt",
            return_value=SimpleNamespace(key=self.public_key),
        ):
            return client.get(reverse("journey-list"), HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_valid_token_resolves_account_from_validated_subject(self):
        self.assertEqual(self.request(self.token()).status_code, 200)
        self.assertEqual(get_user_model().objects.filter(auth_identity__subject="google-oauth2|opaque-auth0-subject").count(), 1)

    def test_expired_token_is_rejected(self):
        expired = int((timezone.now() - timedelta(minutes=1)).timestamp())
        self.assertEqual(self.request(self.token(exp=expired)).status_code, 401)

    def test_wrong_audience_is_rejected(self):
        self.assertEqual(self.request(self.token(aud="wrong-api")).status_code, 401)
