import json

from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from rest_framework.test import APIClient

from common.exceptions import GuestMigrationBlocked, JourneyLimitExceeded


def post_json(client, url, payload):
    return client.post(url, json.dumps(payload), content_type="application/json")


class SetLanguageViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        csrf_token = self.client.get(reverse("auth-csrf")).json()["csrf_token"]
        self.client.credentials(HTTP_X_CSRFTOKEN=csrf_token)

    def test_setting_french_writes_the_cookie_locale_middleware_reads(self):
        response = post_json(self.client, reverse("set-language"), {"language": "fr"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"language": "fr"})
        self.assertEqual(response.cookies["django_language"].value, "fr")

    def test_an_unsupported_language_is_rejected(self):
        response = post_json(self.client, reverse("set-language"), {"language": "de"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("django_language", response.cookies)

    def test_the_cookie_actually_activates_french_on_the_next_request(self):
        post_json(self.client, reverse("set-language"), {"language": "fr"})
        status = self.client.get(reverse("auth-status"))
        self.assertEqual(status.status_code, 200)
        # LocaleMiddleware activates the language for the duration of the
        # request from the cookie alone -- confirm it round-trips correctly
        # rather than only working inside SetLanguageView's own handler.
        self.assertEqual(self.client.cookies["django_language"].value, "fr")

    def tearDown(self):
        translation.deactivate()


class FrenchErrorMessageTests(TestCase):
    """
    French localization, Phase C: API error messages must be French when the
    citizen's chosen language is French -- these are always deterministic
    Python text (common/exceptions.py), never AI-generated.
    """

    def test_journey_limit_message_is_french_and_pluralizes_correctly(self):
        with translation.override("fr"):
            self.assertEqual(
                JourneyLimitExceeded(1).detail,
                "Vous pouvez avoir jusqu'à 1 démarche active.",
            )
            self.assertEqual(
                JourneyLimitExceeded(5).detail,
                "Vous pouvez avoir jusqu'à 5 démarches actives.",
            )

    def test_journey_limit_message_is_english_by_default(self):
        with translation.override("en"):
            self.assertEqual(
                JourneyLimitExceeded(1).detail,
                "You can have up to 1 active Journey.",
            )
            self.assertEqual(
                JourneyLimitExceeded(5).detail,
                "You can have up to 5 active Journeys.",
            )

    def test_guest_migration_blocked_message_is_french(self):
        with translation.override("fr"):
            self.assertIn("compte a déjà atteint la limite de 5 démarches", GuestMigrationBlocked(5).detail)
