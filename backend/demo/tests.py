from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class PrivacyPageTests(SimpleTestCase):
    @override_settings(PRIVACY_CONTACT_EMAIL="privacy-test@example.com")
    def test_privacy_page_discloses_key_data_practices(self):
        response = self.client.get(reverse("privacy"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Google Gemini")
        self.assertContains(response, "sessionid")
        self.assertContains(response, "Auth0")
        self.assertContains(response, "Render")
        self.assertContains(response, "sell or rent personal information")
        self.assertContains(response, "privacy-test@example.com")
        self.assertNotContains(response, "auth0-spa-js.production.js")

    def test_main_site_footer_links_to_privacy_page(self):
        response = self.client.get(reverse("demo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("privacy")}"')
        self.assertContains(response, "Privacy policy")
