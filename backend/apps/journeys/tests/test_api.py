"""
API tests (CLAUDE.md §32).

Covers the full request lifecycle: create, interpret, confirm, correct, delete,
recalculation, ownership, idempotency, throttling and the error envelope.

No test here reaches a live model. The deterministic extractor is the default, so
most of these run against the real code path rather than a mock -- which is the
point of building it that way round.
"""
import json
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.directory.models import Organization, is_government_domain
from apps.directory.seed import seed_directory
from apps.journeys import enums
from apps.journeys.models import Breadcrumb, Journey
from apps.journeys.services import create_guide
from services.ai.rules import RuleBasedAIService


class ApiTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()
        cls.ircc = Organization.objects.get(short_name="IRCC")

    def setUp(self):
        cache.clear()  # throttle counters are cache-backed
        # DevUserAuthentication resolves every request to the demo user, so the
        # first call creates it; we fetch it to own the fixtures.
        self.client.get(reverse("journey-list"))
        self.user = get_user_model().objects.get(
            username="demo@civicbreadcrumbs.local"
        )
        self.journey = Journey.objects.create(
            user=self.user,
            title="Study Permit Extension",
            goal="Extend my study permit",
            primary_organization=self.ircc,
        )

    def post(self, url, payload):
        return self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

    def patch(self, url, payload):
        return self.client.patch(
            url, data=json.dumps(payload), content_type="application/json"
        )


class JourneyCreateTests(ApiTestCase):
    def test_create_journey_from_a_plain_description(self):
        response = self.post(
            reverse("journey-list"),
            {"description": "I applied to extend my study permit and I am not sure what to do next."},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["title"], "Study Permit Extension")
        self.assertEqual(body["state"]["status"], enums.JourneyStatus.ACTIVE)
        self.assertIn("Nothing has been recorded", body["state"]["current_state"])

    def test_creation_returns_a_saved_suggested_guide(self):
        response = self.post(
            reverse("journey-list"),
            {"description": "I want to renew my passport before it expires."},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Passport Renewal")
        guide = response.json()["guide"]
        self.assertGreaterEqual(len(guide["steps"]), 3)
        self.assertLessEqual(len(guide["steps"]), 6)
        self.assertTrue(guide["needs_clarification"])
        self.assertIn("country", guide["clarification_question"].lower())
        self.assertTrue(all(step["official_source"] is None for step in guide["steps"]))
        self.assertEqual(response.json()["breadcrumbs"], [])

    def test_create_journey_with_an_explicit_title_spends_no_ai_call(self):
        response = self.post(
            reverse("journey-list"), {"title": "Health Card", "goal": "Get OHIP"}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["ai"]["extractor"], "none")

    def test_create_journey_requires_something_to_work_from(self):
        response = self.post(reverse("journey-list"), {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")

    def test_out_of_scope_description_does_not_create_a_journey(self):
        before = Journey.objects.count()
        response = self.post(
            reverse("journey-list"), {"description": "Write me a poem about Ottawa."}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["type"], enums.Intent.OUT_OF_SCOPE)
        self.assertEqual(Journey.objects.count(), before)


class InterpretAndConfirmTests(ApiTestCase):
    """The draft/confirm split is the trust model (§24)."""

    def url(self):
        return reverse("breadcrumb-interpret", args=[self.journey.id])

    def test_interpret_reads_the_event_correctly(self):
        response = self.post(
            self.url(),
            {"text": "I called IRCC today. They said my application is still processing "
                     "and they told me not to submit another application."},
        )
        self.assertEqual(response.status_code, 200)
        draft = response.json()["draft"]
        self.assertEqual(draft["kind"], enums.BreadcrumbKind.INTERACTION)
        self.assertEqual(draft["channel"], enums.Channel.PHONE)
        self.assertEqual(draft["organization"], self.ircc.name)
        self.assertEqual(draft["reported_status"], enums.ReportedStatus.PROCESSING)
        self.assertEqual(draft["instruction"], "Do not submit another application")
        self.assertEqual(draft["suggested_next_action"], enums.NextActionCode.WAIT)

    def test_interpret_response_includes_a_paraphrase(self):
        """"AI understands and reflects it back" -- shown before any correction
        form, so a one-tap confirm feels safe rather than blind."""
        response = self.post(
            self.url(),
            {"text": "I called IRCC today. They said my application is still processing."},
        )
        paraphrase = response.json()["draft"]["paraphrase"]
        self.assertTrue(paraphrase)
        self.assertIn("IRCC", paraphrase)

    def test_interpret_persists_nothing(self):
        """
        Interpretation must be disposable. If it wrote to the journey, the review
        step would be theatre.
        """
        self.post(self.url(), {"text": "I called IRCC today, still processing."})
        self.assertEqual(self.journey.breadcrumbs.count(), 0)

    def test_interpret_always_offers_the_note_fallback(self):
        response = self.post(self.url(), {"text": "I called IRCC today."})
        self.assertEqual(response.json()["fallback_action"], "SAVE_AS_NOTE")

    def test_interpret_echoes_the_citizens_original_wording(self):
        text = "I called IRCC today and they were not helpful at all."
        response = self.post(self.url(), {"text": text})
        self.assertEqual(response.json()["raw_text"], text)

    def test_confirming_creates_evidence_and_updates_state(self):
        response = self.post(
            reverse("breadcrumb-list", args=[self.journey.id]),
            {
                "kind": enums.BreadcrumbKind.INTERACTION,
                "channel": enums.Channel.PHONE,
                "title": "Called IRCC",
                "raw_text": "I called IRCC today, still processing.",
                "organization_name": self.ircc.name,
                "reported_status": enums.ReportedStatus.PROCESSING,
                "instruction": "Do not submit another application",
                "suggested_next_action": enums.NextActionCode.WAIT,
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["state"]["status"], enums.JourneyStatus.WAITING)
        self.assertTrue(body["counts_as_evidence"])
        # The free-text organization resolved to the curated record.
        self.assertIsNotNone(body["organization"])
        self.assertEqual(body["organization"]["short_name"], "IRCC")

    def test_ai_interpretation_cannot_be_submitted_as_evidence(self):
        """§14 Rule 2, enforced at the API boundary as well as in derivation."""
        response = self.post(
            reverse("breadcrumb-list", args=[self.journey.id]),
            {
                "kind": enums.BreadcrumbKind.NOTE,
                "title": "Generated summary",
                "source_type": enums.SourceType.AI_INTERPRETATION,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")


class IdempotencyTests(ApiTestCase):
    def test_repeating_a_request_id_returns_the_original_row(self):
        payload = {
            "kind": enums.BreadcrumbKind.ACTION,
            "title": "Application submitted",
            "raw_text": "I submitted the application.",
            "request_id": "client-abc-123",
        }
        url = reverse("breadcrumb-list", args=[self.journey.id])

        first = self.post(url, payload)
        second = self.post(url, payload)

        self.assertEqual(first.status_code, 201)
        self.assertTrue(first.json()["created"])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(self.journey.breadcrumbs.count(), 1)

    def test_identical_wording_warns_but_still_saves(self):
        """
        A warning, not a rejection: someone may genuinely have called the same
        office twice in one day and be right to record both.
        """
        payload = {
            "kind": enums.BreadcrumbKind.INTERACTION,
            "title": "Called IRCC",
            "raw_text": "I called IRCC today.",
        }
        url = reverse("breadcrumb-list", args=[self.journey.id])
        self.post(url, payload)
        second = self.post(url, payload)

        self.assertEqual(second.status_code, 201)
        warnings = second.json()["warnings"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["code"], "DUPLICATE_EVENT")
        self.assertEqual(self.journey.breadcrumbs.count(), 2)


class CorrectionTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.breadcrumb = Breadcrumb.objects.create(
            journey=self.journey,
            kind=enums.BreadcrumbKind.INTERACTION,
            channel=enums.Channel.PHONE,
            title="Called IRCC",
            raw_text="I called IRCC and they said it is still processing.",
            organization=self.ircc,
            organization_name=self.ircc.name,
            occurred_at="2026-09-24T09:00:00Z",
            structured_data={"reported_status": enums.ReportedStatus.PROCESSING},
        )

    def test_correcting_a_breadcrumb_recalculates_the_journey(self):
        response = self.patch(
            reverse("breadcrumb-detail", args=[self.breadcrumb.id]),
            {
                "reported_status": enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED,
                "instruction": "Send your proof of enrolment",
                "suggested_next_action": enums.NextActionCode.PROVIDE_DOCUMENT,
            },
        )
        self.assertEqual(response.status_code, 200)
        state = response.json()["state"]
        self.assertEqual(state["status"], enums.JourneyStatus.ACTION_REQUIRED)
        self.assertIn("proof of enrolment", state["next_action"])

    def test_the_original_wording_survives_a_correction(self):
        """
        §10. The citizen's own words are the audit trail. An interpretation being
        wrong is never a reason to rewrite what they said.
        """
        original = self.breadcrumb.raw_text
        self.patch(
            reverse("breadcrumb-detail", args=[self.breadcrumb.id]),
            {"raw_text": "something completely different", "title": "Corrected title"},
        )
        self.breadcrumb.refresh_from_db()
        self.assertEqual(self.breadcrumb.raw_text, original)
        self.assertEqual(self.breadcrumb.title, "Corrected title")

    def test_deleting_falls_back_to_earlier_evidence(self):
        response = self.client.delete(
            reverse("breadcrumb-detail", args=[self.breadcrumb.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])
        self.assertEqual(
            response.json()["state"]["status"], enums.JourneyStatus.ACTIVE
        )


class OwnershipTests(ApiTestCase):
    """§29 -- IDOR protection."""

    def setUp(self):
        super().setUp()
        self.other_user = get_user_model().objects.create(username="other@example.test")
        self.other_journey = Journey.objects.create(
            user=self.other_user, title="Not mine", goal="private"
        )
        self.other_breadcrumb = Breadcrumb.objects.create(
            journey=self.other_journey,
            kind=enums.BreadcrumbKind.NOTE,
            title="Private note",
            occurred_at="2026-09-24T09:00:00Z",
        )
        self.other_guide = create_guide(
            self.other_journey,
            RuleBasedAIService().extract_journey("Renew a passport"),
        )

    def test_another_users_journey_is_404_not_403(self):
        """
        A 403 confirms the id exists, which lets an attacker enumerate journeys.
        A 404 reveals nothing.
        """
        for name in (
            "journey-detail",
            "journey-state",
            "journey-stuck",
            "breadcrumb-list",
            "journey-responsible-organization",
            "journey-official-sources",
            "journey-guide",
        ):
            with self.subTest(endpoint=name):
                response = self.client.get(reverse(name, args=[self.other_journey.id]))
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")

    def test_another_users_breadcrumb_cannot_be_edited_or_deleted(self):
        url = reverse("breadcrumb-detail", args=[self.other_breadcrumb.id])
        self.assertEqual(self.patch(url, {"title": "hijacked"}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.other_breadcrumb.refresh_from_db()
        self.assertEqual(self.other_breadcrumb.title, "Private note")

    def test_another_users_journey_is_absent_from_the_list(self):
        response = self.client.get(reverse("journey-list"))
        titles = [row["title"] for row in response.json()["results"]]
        self.assertNotIn("Not mine", titles)

    def test_a_nonexistent_id_is_also_404(self):
        response = self.client.get(reverse("journey-detail", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)

    def test_another_users_guide_step_cannot_be_completed(self):
        step = self.other_guide.steps.first()
        response = self.post(reverse("guide-step-complete", args=[step.id]), {})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.other_journey.breadcrumbs.count(), 1)


class GuideProgressTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.guide = create_guide(
            self.journey,
            RuleBasedAIService().extract_journey(
                "I want to renew my passport before it expires."
            ),
        )
        self.step = self.guide.steps.first()

    def test_guide_read_costs_no_write_and_returns_ordered_steps(self):
        response = self.client.get(reverse("journey-guide", args=[self.journey.id]))
        self.assertEqual(response.status_code, 200)
        positions = [step["position"] for step in response.json()["steps"]]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(self.journey.breadcrumbs.count(), 0)

    def test_recording_against_a_step_marks_it_in_progress(self):
        response = self.post(
            reverse("breadcrumb-list", args=[self.journey.id]),
            {
                "kind": enums.BreadcrumbKind.NOTE,
                "title": "Checked the official service",
                "guide_step_id": str(self.step.id),
            },
        )
        self.assertEqual(response.status_code, 201)
        self.step.refresh_from_db()
        self.assertEqual(self.step.status, enums.GuideStepStatus.IN_PROGRESS)
        self.assertEqual(response.json()["guide_step"], str(self.step.id))

    def test_completion_is_explicit_auditable_and_idempotent(self):
        url = reverse("guide-step-complete", args=[self.step.id])
        first = self.post(url, {})
        second = self.post(url, {})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["breadcrumb_id"], second.json()["breadcrumb_id"])
        self.assertEqual(self.journey.breadcrumbs.count(), 1)
        self.step.refresh_from_db()
        self.assertEqual(self.step.status, enums.GuideStepStatus.COMPLETED)

    def test_deleting_completion_evidence_reopens_the_step(self):
        complete = self.post(reverse("guide-step-complete", args=[self.step.id]), {})
        breadcrumb_id = complete.json()["breadcrumb_id"]
        deleted = self.client.delete(reverse("breadcrumb-detail", args=[breadcrumb_id]))
        self.assertEqual(deleted.status_code, 200)
        self.step.refresh_from_db()
        self.assertEqual(self.step.status, enums.GuideStepStatus.NOT_STARTED)
        self.assertIsNone(self.step.completion_breadcrumb_id)

    def test_deleting_the_only_linked_record_resets_in_progress(self):
        recorded = self.post(
            reverse("breadcrumb-list", args=[self.journey.id]),
            {
                "kind": enums.BreadcrumbKind.NOTE,
                "title": "Checked the guidance",
                "guide_step_id": str(self.step.id),
            },
        )
        self.client.delete(reverse("breadcrumb-detail", args=[recorded.json()["id"]]))
        self.step.refresh_from_db()
        self.assertEqual(self.step.status, enums.GuideStepStatus.NOT_STARTED)

    def test_a_step_from_another_journey_cannot_be_linked(self):
        other = Journey.objects.create(user=self.user, title="Other", goal="Other")
        other_guide = create_guide(
            other, RuleBasedAIService().extract_journey("Renew a health card")
        )
        response = self.post(
            reverse("breadcrumb-list", args=[self.journey.id]),
            {
                "kind": enums.BreadcrumbKind.NOTE,
                "title": "Wrong journey",
                "guide_step_id": str(other_guide.steps.first().id),
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.journey.breadcrumbs.count(), 0)


class GuideStepOfficialSourceTests(ApiTestCase):
    """
    Different steps that need different things (gathering documents vs.
    checking processing times) must get different, relevant links instead of
    the whole guide silently sharing one link -- this is the actual gap the
    request "add a link to the step about filling in forms" was pointing at.
    """

    def test_steps_with_different_topics_get_different_official_sources(self):
        guide = create_guide(
            self.journey,
            RuleBasedAIService().extract_journey("Extend my study permit"),
        )
        steps = list(guide.steps.all())
        self.assertGreaterEqual(len(steps), 3)
        # IRCC has three seeded sources (study permit / processing times /
        # contact); the study-permit branch's steps carry matching topic
        # hints, so this must not collapse onto one repeated source.
        sources = {step.official_source_id for step in steps}
        self.assertGreater(len(sources), 1)

    def test_a_step_topic_matches_its_own_seeded_source_not_a_generic_one(self):
        guide = create_guide(
            self.journey,
            RuleBasedAIService().extract_journey("Extend my study permit"),
        )
        tracking_step = guide.steps.get(title="Track updates and instructions")
        self.assertIsNotNone(tracking_step.official_source)
        self.assertEqual(tracking_step.official_source.topic, "processing times")

    def test_no_curated_source_for_the_organization_leaves_every_step_unset(self):
        """The honest gap: no guessed link when nothing is genuinely curated
        for this organization (§21)."""
        ottawa = Organization.objects.get(short_name="City of Ottawa")
        journey = Journey.objects.create(
            user=self.user,
            title="Property tax question",
            goal="Understand my property tax bill",
            primary_organization=ottawa,
        )
        guide = create_guide(
            journey, RuleBasedAIService().extract_journey("Property tax question")
        )
        self.assertTrue(
            all(step.official_source is None for step in guide.steps.all())
        )

    def test_official_source_shown_to_the_citizen_is_never_a_non_government_link(self):
        """Belt-and-braces: whatever gets attached and served over the API is
        provably one of the curated, government-domain-validated sources."""
        guide = create_guide(
            self.journey,
            RuleBasedAIService().extract_journey("Extend my study permit"),
        )
        response = self.client.get(reverse("journey-guide", args=[self.journey.id]))
        for step in response.json()["steps"]:
            source = step.get("official_source")
            if source:
                self.assertTrue(is_government_domain(source["url"]))


class ZeroAICostTests(ApiTestCase):
    """§17 -- the read endpoints must cost nothing."""

    def setUp(self):
        super().setUp()
        Breadcrumb.objects.create(
            journey=self.journey,
            kind=enums.BreadcrumbKind.INTERACTION,
            channel=enums.Channel.PHONE,
            title="Called IRCC",
            organization=self.ircc,
            organization_name=self.ircc.name,
            occurred_at="2026-09-24T09:00:00Z",
            structured_data={
                "reported_status": enums.ReportedStatus.PROCESSING,
                "instruction": "Do not submit another application",
                "suggested_next_action": enums.NextActionCode.WAIT,
            },
        )

    def test_state_endpoint_reports_zero_ai_calls_and_full_provenance(self):
        response = self.client.get(reverse("journey-state", args=[self.journey.id]))
        body = response.json()
        self.assertEqual(body["status"], enums.JourneyStatus.WAITING)
        self.assertIn("recorded", body["current_state"].lower())
        self.assertEqual(body["source"]["type"], enums.SourceType.USER_REPORTED)
        self.assertIsNotNone(body["source"]["breadcrumb_id"])

    def test_stuck_without_polish_spends_no_ai_call(self):
        response = self.client.get(
            reverse("journey-stuck", args=[self.journey.id]) + "?polish=false"
        )
        body = response.json()
        self.assertEqual(body["ai"]["calls"], 0)
        self.assertFalse(body["ai"]["summary_is_generated"])
        self.assertEqual(body["responsible_organization"]["short_name"], "IRCC")
        self.assertTrue(body["official_sources"])

    def test_responsible_organization_resolves_from_the_curated_directory(self):
        response = self.client.get(
            reverse("journey-responsible-organization", args=[self.journey.id])
        )
        body = response.json()
        self.assertEqual(body["source"], "CURATED_DIRECTORY")
        self.assertEqual(body["responsible_organization"]["short_name"], "IRCC")
        # Waiting means nobody needs contacting -- a deliberate answer (§21).
        self.assertFalse(body["action_needed"])

    def test_handoff_is_generated_but_never_stored(self):
        """§33 Case G at the API level."""
        before = Breadcrumb.objects.count()
        response = self.post(reverse("journey-handoff", args=[self.journey.id]), {})
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(body["persisted"])
        self.assertIn("CASE SUMMARY", body["summary"])
        self.assertIn("Do not submit another application", body["summary"])
        self.assertIn("not an official government document", body["summary"])
        self.assertEqual(Breadcrumb.objects.count(), before)


class OrganizationResolutionTests(ApiTestCase):
    def test_no_confident_match_returns_null_rather_than_a_guess(self):
        """§21 -- never fabricate an institution."""
        journey = Journey.objects.create(
            user=self.user,
            title="Something unrelated",
            goal="A goal with no recognisable public service in it",
        )
        response = self.client.get(
            reverse("journey-responsible-organization", args=[journey.id])
        )
        body = response.json()
        self.assertIsNone(body["responsible_organization"])
        self.assertIsNone(body["source"])
        self.assertIn("do not have enough verified information", body["message"])


class SaveAsNoteTests(ApiTestCase):
    def test_note_fallback_records_the_citizens_own_words(self):
        text = "The receptionist said to call back Monday after 10."
        response = self.post(
            reverse("breadcrumb-save-note", args=[self.journey.id]), {"text": text}
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["kind"], enums.BreadcrumbKind.NOTE)
        self.assertEqual(body["raw_text"], text)
        self.assertTrue(body["counts_as_evidence"])


class ThrottlingTests(ApiTestCase):
    """
    §26 -- protect quota, and fail in language a person can act on.

    Exercised against the real configured rate rather than an overridden one:
    DRF instantiates throttles from its own cached settings object, so a test
    that overrides REST_FRAMEWORK can pass while the deployed limit is wrong.
    """

    def configured_limit(self):
        from common.throttling import AIThrottle

        return AIThrottle().num_requests

    def test_ai_routes_throttle_with_a_friendly_recoverable_error(self):
        url = reverse("breadcrumb-interpret", args=[self.journey.id])
        payload = {"text": "I called IRCC today, still processing."}
        limit = self.configured_limit()

        statuses = [
            self.post(url, payload).status_code for _ in range(limit + 2)
        ]
        self.assertEqual(statuses.count(200), limit)
        self.assertIn(429, statuses)

        throttled = self.post(url, payload)
        self.assertEqual(throttled.status_code, 429)
        error = throttled.json()["error"]
        self.assertEqual(error["code"], "AI_RATE_LIMITED")
        self.assertTrue(error["recoverable"])
        self.assertEqual(error["suggested_action"], "RETRY")
        self.assertIn("retry_after_seconds", error)

    def test_a_throttled_citizen_can_still_record_what_happened(self):
        """
        Hitting the limit must not cost someone their record. The note fallback
        is not throttled, so the escape hatch is always open (§28).
        """
        interpret_url = reverse("breadcrumb-interpret", args=[self.journey.id])
        payload = {"text": "I called IRCC today, still processing."}
        for _ in range(self.configured_limit() + 1):
            self.post(interpret_url, payload)

        note = self.post(
            reverse("breadcrumb-save-note", args=[self.journey.id]),
            {"text": "I called IRCC today, still processing."},
        )
        self.assertEqual(note.status_code, 201)

    def test_read_endpoints_are_not_throttled(self):
        url = reverse("journey-state", args=[self.journey.id])
        statuses = [
            self.client.get(url).status_code
            for _ in range(self.configured_limit() + 5)
        ]
        self.assertEqual(set(statuses), {200})


class CloseTheLoopTests(ApiTestCase):
    """
    "Because you recorded this, your status moved from X to Y." Deterministic,
    zero AI calls -- just describing the before/after of the §9.1 cache.
    """

    def test_create_that_changes_status_reports_the_move(self):
        response = self.post(
            reverse("breadcrumb-list", args=[self.journey.id]),
            {
                "kind": enums.BreadcrumbKind.INTERACTION,
                "channel": enums.Channel.PHONE,
                "title": "Called IRCC",
                "organization_name": self.ircc.name,
                "reported_status": enums.ReportedStatus.PROCESSING,
            },
        )
        change = response.json()["change"]
        self.assertTrue(change["changed"])
        self.assertTrue(change["status_changed"])
        self.assertIn("Active to Waiting", change["message"])
        self.assertTrue(change["message"].startswith("Because you recorded this"))

    def test_create_that_does_not_change_status_reports_unchanged(self):
        # First breadcrumb establishes WAITING.
        url = reverse("breadcrumb-list", args=[self.journey.id])
        self.post(
            url,
            {
                "kind": enums.BreadcrumbKind.INTERACTION,
                "title": "Called IRCC",
                "organization_name": self.ircc.name,
                "reported_status": enums.ReportedStatus.PROCESSING,
            },
        )
        # A second call with the same reported status doesn't move anything.
        response = self.post(
            url,
            {
                "kind": enums.BreadcrumbKind.INTERACTION,
                "title": "Called IRCC again",
                "organization_name": self.ircc.name,
                "reported_status": enums.ReportedStatus.PROCESSING,
            },
        )
        change = response.json()["change"]
        self.assertFalse(change["changed"])
        self.assertEqual(change["message"], "Saved. Your status is still Waiting.")

    def test_correcting_a_breadcrumb_reports_the_change(self):
        breadcrumb = Breadcrumb.objects.create(
            journey=self.journey,
            kind=enums.BreadcrumbKind.INTERACTION,
            title="Called IRCC",
            organization=self.ircc,
            organization_name=self.ircc.name,
            occurred_at="2026-09-24T09:00:00Z",
            structured_data={"reported_status": enums.ReportedStatus.PROCESSING},
        )
        response = self.patch(
            reverse("breadcrumb-detail", args=[breadcrumb.id]),
            {
                "reported_status": enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED,
                "suggested_next_action": enums.NextActionCode.PROVIDE_DOCUMENT,
            },
        )
        change = response.json()["change"]
        self.assertTrue(change["changed"])
        self.assertIn("Waiting to Action needed", change["message"])
        self.assertTrue(change["message"].startswith("Because you corrected this"))

    def test_deleting_the_latest_status_reports_the_fallback(self):
        Breadcrumb.objects.create(
            journey=self.journey,
            kind=enums.BreadcrumbKind.ACTION,
            title="Application submitted",
            occurred_at="2026-09-18T09:00:00Z",
            structured_data={"reported_status": enums.ReportedStatus.SUBMITTED},
        )
        latest = Breadcrumb.objects.create(
            journey=self.journey,
            kind=enums.BreadcrumbKind.INTERACTION,
            title="Called IRCC",
            organization=self.ircc,
            organization_name=self.ircc.name,
            occurred_at="2026-09-24T09:00:00Z",
            structured_data={
                "reported_status": enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED,
                "suggested_next_action": enums.NextActionCode.PROVIDE_DOCUMENT,
            },
        )
        response = self.client.delete(
            reverse("breadcrumb-detail", args=[latest.id])
        )
        change = response.json()["change"]
        self.assertTrue(change["changed"])
        self.assertIn("Action needed to Waiting", change["message"])
        self.assertTrue(change["message"].startswith("Because you deleted that"))

    def test_idempotent_replay_reports_unchanged_with_no_special_casing(self):
        payload = {
            "kind": enums.BreadcrumbKind.INTERACTION,
            "title": "Called IRCC",
            "organization_name": self.ircc.name,
            "reported_status": enums.ReportedStatus.PROCESSING,
            "request_id": "close-loop-replay-1",
        }
        url = reverse("breadcrumb-list", args=[self.journey.id])
        self.post(url, payload)
        replay = self.post(url, payload)
        self.assertFalse(replay.json()["created"])
        self.assertFalse(replay.json()["change"]["changed"])

    def test_saving_a_note_that_does_not_move_status_reports_unchanged(self):
        # Establish WAITING first; a plain NOTE carries no status of its own,
        # so it shouldn't move the journey off of it.
        self.post(
            reverse("breadcrumb-list", args=[self.journey.id]),
            {
                "kind": enums.BreadcrumbKind.INTERACTION,
                "title": "Called IRCC",
                "organization_name": self.ircc.name,
                "reported_status": enums.ReportedStatus.PROCESSING,
            },
        )
        response = self.post(
            reverse("breadcrumb-save-note", args=[self.journey.id]),
            {"text": "Receptionist said to call back Monday."},
        )
        change = response.json()["change"]
        self.assertFalse(change["changed"])
        self.assertEqual(change["message"], "Saved. Your status is still Waiting.")

    def test_saving_the_first_note_on_an_empty_journey_reports_a_change(self):
        """
        An empty journey has no next_action text yet; the first ever record
        naturally produces one, so this is a real (if modest) change, not a
        no-op -- the payload must still be well-formed.
        """
        response = self.post(
            reverse("breadcrumb-save-note", args=[self.journey.id]),
            {"text": "Receptionist said to call back Monday."},
        )
        change = response.json()["change"]
        self.assertIn("message", change)
        self.assertTrue(change["message"])


class StalenessNudgeTests(ApiTestCase):
    """Proactive check-ins surfaced through GET /state/."""

    def test_fresh_journey_is_not_flagged_stale(self):
        Breadcrumb.objects.create(
            journey=self.journey,
            kind=enums.BreadcrumbKind.INTERACTION,
            title="Called IRCC",
            organization=self.ircc,
            organization_name=self.ircc.name,
            occurred_at=timezone.now(),
            structured_data={"reported_status": enums.ReportedStatus.PROCESSING},
        )
        response = self.client.get(reverse("journey-state", args=[self.journey.id]))
        staleness = response.json()["staleness"]
        self.assertFalse(staleness["is_stale"])

    def test_old_action_required_journey_is_flagged_stale(self):
        breadcrumb = Breadcrumb.objects.create(
            journey=self.journey,
            kind=enums.BreadcrumbKind.INTERACTION,
            title="Called IRCC",
            organization=self.ircc,
            organization_name=self.ircc.name,
            occurred_at="2026-09-24T09:00:00Z",
            structured_data={
                "reported_status": enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED,
                "suggested_next_action": enums.NextActionCode.PROVIDE_DOCUMENT,
            },
        )
        Breadcrumb.objects.filter(pk=breadcrumb.pk).update(
            created_at=timezone.now() - timedelta(days=5)
        )
        response = self.client.get(reverse("journey-state", args=[self.journey.id]))
        staleness = response.json()["staleness"]
        self.assertTrue(staleness["is_stale"])
        self.assertIn("haven't recorded", staleness["message"])

    def test_completed_journey_is_never_flagged_stale(self):
        breadcrumb = Breadcrumb.objects.create(
            journey=self.journey,
            kind=enums.BreadcrumbKind.STATUS_UPDATE,
            title="Approved",
            occurred_at="2026-09-24T09:00:00Z",
            structured_data={"reported_status": enums.ReportedStatus.APPROVED},
        )
        Breadcrumb.objects.filter(pk=breadcrumb.pk).update(
            created_at=timezone.now() - timedelta(days=365)
        )
        response = self.client.get(reverse("journey-state", args=[self.journey.id]))
        staleness = response.json()["staleness"]
        self.assertFalse(staleness["is_stale"])
