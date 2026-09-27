"""
The government-domain rule (CLAUDE.md §21): an official-source link must point
to a real Government of Canada or Government of Ontario domain, and must be
attached to a federal or provincial organization. This holds as a structural
property of the model, not a policy statement -- it cannot be bypassed by a
future write path that forgets to check it explicitly.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.directory.models import Jurisdiction, Organization, OfficialSource, is_government_domain
from apps.directory.seed import seed_directory


class GovernmentDomainTests(TestCase):
    def test_canada_ca_and_gc_ca_and_ontario_ca_are_recognised(self):
        for url in (
            "https://www.canada.ca/en/immigration-refugees-citizenship.html",
            "https://ircc.gc.ca/english/",
            "https://www.ontario.ca/page/apply-ohip",
            "https://www.gov.on.ca/something",
        ):
            with self.subTest(url=url):
                self.assertTrue(is_government_domain(url))

    def test_municipal_and_arbitrary_domains_are_not_recognised(self):
        for url in (
            "https://ottawa.ca/en",
            "https://example.com/looks-official",
            "https://www.uottawa.ca/en/students",
        ):
            with self.subTest(url=url):
                self.assertFalse(is_government_domain(url))

    def test_a_domain_that_merely_contains_canada_ca_is_not_fooled(self):
        """
        A naive "canada.ca in url" substring check would be spoofable by a
        domain like canada.ca.evil.com. The real check is hostname equality or
        a genuine subdomain relationship.
        """
        self.assertFalse(is_government_domain("https://canada.ca.evil.com/phish"))
        self.assertFalse(is_government_domain("https://notcanada.ca/x"))
        self.assertTrue(is_government_domain("https://www.canada.ca/x"))


class OfficialSourceValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()

    def test_a_non_government_url_is_rejected(self):
        ircc = Organization.objects.get(short_name="IRCC")
        source = OfficialSource(
            organization=ircc,
            title="Fake",
            url="https://ottawa.ca/not-federal",
            verified_at=timezone.now(),
        )
        with self.assertRaises(ValidationError) as ctx:
            source.full_clean()
        self.assertIn("url", ctx.exception.message_dict)

    def test_a_municipal_organization_cannot_carry_an_official_source(self):
        """
        City of Ottawa remains a valid *responsible organization* answer
        (§21) -- it just can never carry an official-source link, since no
        municipal domain is on the allow-list.
        """
        ottawa = Organization.objects.get(short_name="City of Ottawa")
        source = OfficialSource(
            organization=ottawa,
            title="Fake",
            url="https://www.canada.ca/en/x",
            verified_at=timezone.now(),
        )
        with self.assertRaises(ValidationError) as ctx:
            source.full_clean()
        self.assertIn("organization", ctx.exception.message_dict)

    def test_an_institutional_organization_cannot_carry_an_official_source(self):
        university = Organization.objects.get(short_name="International Office")
        source = OfficialSource(
            organization=university,
            title="Fake",
            url="https://www.canada.ca/en/x",
            verified_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            source.full_clean()

    def test_a_genuine_federal_source_passes(self):
        ircc = Organization.objects.get(short_name="IRCC")
        source = OfficialSource(
            organization=ircc,
            title="Real",
            url="https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada.html",
            verified_at=timezone.now(),
        )
        source.full_clean()  # must not raise

    def test_every_seeded_official_source_passes_the_rule(self):
        """The curated directory itself must already comply -- this is what
        seed_directory()'s own full_clean() call enforces on every run."""
        self.assertGreater(OfficialSource.objects.count(), 0)
        for source in OfficialSource.objects.all():
            with self.subTest(source=source.title):
                source.full_clean()

    def test_reseeding_does_not_falsely_advance_source_freshness(self):
        source = OfficialSource.objects.first()
        old_verified_at = timezone.now() - timedelta(days=30)
        source.verified_at = old_verified_at
        source.refresh_status = "CHANGED"
        source.save(update_fields=["verified_at", "refresh_status"])

        seed_directory()
        source.refresh_from_db()
        self.assertEqual(source.verified_at, old_verified_at)
        self.assertEqual(source.refresh_status, "CHANGED")

    def test_jurisdiction_choices_allow_federal_and_provincial(self):
        self.assertIn(Jurisdiction.FEDERAL, dict(Jurisdiction.choices))
        self.assertIn(Jurisdiction.PROVINCIAL, dict(Jurisdiction.choices))


class FrenchLocalizationTests(TestCase):
    """
    French localization, Phase D: every url_fr in the curated seed must be a
    verified government domain link (same rule as url, never a guessed one),
    and localized_* must actually switch on the active locale.
    """

    @classmethod
    def setUpTestData(cls):
        seed_directory()

    def test_every_seeded_url_fr_passes_the_government_domain_rule(self):
        sources_with_french = OfficialSource.objects.exclude(url_fr="")
        self.assertGreater(sources_with_french.count(), 0)
        for source in sources_with_french:
            with self.subTest(source=source.title):
                source.full_clean()

    def test_organization_localized_fields_switch_on_locale(self):
        from django.utils import translation

        ircc = Organization.objects.get(short_name="IRCC")
        with translation.override("en"):
            self.assertEqual(ircc.localized_official_url, ircc.official_url)
        with translation.override("fr"):
            self.assertEqual(ircc.localized_official_url, ircc.official_url_fr)
            self.assertNotEqual(ircc.official_url_fr, "")

    def test_official_source_localized_fields_switch_on_locale(self):
        from django.utils import translation

        source = OfficialSource.objects.exclude(url_fr="").first()
        with translation.override("en"):
            self.assertEqual(source.localized_url, source.url)
            self.assertEqual(source.localized_title, source.title)
        with translation.override("fr"):
            self.assertEqual(source.localized_url, source.url_fr)
            self.assertEqual(source.localized_title, source.title_fr)

    def test_missing_french_falls_back_to_english_rather_than_guessing(self):
        """University International Office has no verified official_url_fr
        (CLAUDE.md §21: never invent an official link) -- localized_official_url
        must fall back to English, not return a blank or fabricated URL."""
        from django.utils import translation

        university = Organization.objects.get(short_name="International Office")
        self.assertEqual(university.official_url_fr, "")
        with translation.override("fr"):
            self.assertEqual(university.localized_official_url, university.official_url)
            self.assertTrue(university.localized_official_url)
