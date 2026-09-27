"""
Organization resolution (CLAUDE.md §21) must work the same in French and
English -- a citizen writing in French should get exactly the same guide-step
official-source links as one writing in English, not a degraded experience.
"""
from django.test import TestCase

from apps.directory.seed import seed_directory
from apps.directory.selectors import match_organization_by_topic


class OrganizationTopicMatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()

    def test_an_english_topic_phrase_resolves_to_the_right_organization(self):
        org = match_organization_by_topic("I want to extend my study permit")
        self.assertIsNotNone(org)
        self.assertEqual(org.short_name, "IRCC")

    def test_a_french_topic_phrase_resolves_to_the_same_organization(self):
        org = match_organization_by_topic(
            "Je souhaite prolonger mon permis d'études"
        )
        self.assertIsNotNone(org)
        self.assertEqual(org.short_name, "IRCC")

    def test_a_french_health_card_phrase_resolves_to_ontario(self):
        org = match_organization_by_topic("Je dois renouveler ma carte santé")
        self.assertIsNotNone(org)
        self.assertEqual(org.short_name, "Ontario")

    def test_unrecognised_text_resolves_to_nothing_in_either_language(self):
        self.assertIsNone(match_organization_by_topic("I like to bake bread"))
        self.assertIsNone(match_organization_by_topic("J'aime faire du pain"))
