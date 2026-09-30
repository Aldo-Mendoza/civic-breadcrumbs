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
        self.assertContains(response, f'href="{reverse("terms")}"')
        self.assertContains(response, "Terms of Service")


class TermsPageTests(SimpleTestCase):
    @override_settings(PRIVACY_CONTACT_EMAIL="terms-test@example.com")
    def test_terms_page_contains_core_terms(self):
        response = self.client.get(reverse("terms"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acceptable use and misuse rules")
        self.assertContains(response, "you retain ownership of Your Content")
        self.assertContains(response, "Limitation of liability")
        self.assertContains(response, "non-waivable consumer right")
        self.assertContains(response, "not a government service")
        self.assertContains(response, "terms-test@example.com")
        self.assertContains(response, f'href="{reverse("privacy")}"')
        self.assertNotContains(response, "auth0-spa-js.production.js")

    def test_privacy_page_footer_links_to_terms(self):
        response = self.client.get(reverse("privacy"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("terms")}"')
