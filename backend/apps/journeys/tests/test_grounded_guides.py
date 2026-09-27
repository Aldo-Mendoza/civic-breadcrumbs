from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.directory.models import Organization
from apps.directory.seed import seed_directory
from apps.journeys.models import Journey
from apps.journeys.services import create_guide
from services.ai.schemas import GuideStepDraft, JourneyDraft


class GroundedGuideTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()
        cls.user = get_user_model().objects.create_user(username="grounding-test")
        cls.ircc = Organization.objects.get(short_name="IRCC")

    def journey(self):
        return Journey.objects.create(
            user=self.user,
            title="Study permit extension",
            goal="Extend my study permit",
            primary_organization=self.ircc,
        )

    def draft(self, step):
        return JourneyDraft(
            title="Study permit extension",
            goal="Extend my study permit",
            extractor="gemini",
            guide_steps=[
                step,
                GuideStepDraft(title="Record progress", description="Record what you do."),
                GuideStepDraft(title="Keep confirmations", description="Keep your confirmations."),
            ],
        )

    def test_model_can_only_attach_a_section_id_django_supplied(self):
        unsupplied = self.ircc.official_sources.get(topic="contact").sections.get()
        step = GuideStepDraft(
            title="Submit form 123 within 10 days",
            description="You must submit the required document.",
            # This is a genuine database ID, but it was not in the bounded
            # context selected for this particular model call.
            source_ids=[str(unsupplied.id)],
        )
        guide = create_guide(
            self.journey(), self.draft(step), allowed_source_ids=[]
        )
        saved = guide.steps.get(position=1)
        self.assertIsNone(saved.official_source)
        self.assertIn("could not be verified", saved.description)

    def test_valid_section_id_creates_an_immutable_precise_citation(self):
        section = self.ircc.official_sources.get(topic="study permit").sections.get()
        step = GuideStepDraft(
            title="Review the study permit process",
            description="Use the supplied official guidance.",
            source_ids=[str(section.id)],
        )
        guide = create_guide(
            self.journey(), self.draft(step), allowed_source_ids=[section.id]
        )
        saved = guide.steps.get(position=1)
        self.assertEqual(saved.official_source_section, section)
        self.assertEqual(saved.citation_heading, section.heading)
        self.assertEqual(saved.citation_excerpt, section.text)
        citation_url = saved.citation_url

        section.delete()
        saved.refresh_from_db()
        self.assertIsNone(saved.official_source_section)
        self.assertEqual(saved.citation_url, citation_url)
        self.assertTrue(saved.citation_excerpt)

    def test_no_round_robin_source_is_attached_to_an_unmatched_topic(self):
        step = GuideStepDraft(
            title="Record your progress",
            description="Keep a note of what you do.",
            topic="unrelated topic",
        )
        guide = create_guide(self.journey(), self.draft(step))
        self.assertIsNone(guide.steps.get(position=1).official_source)
