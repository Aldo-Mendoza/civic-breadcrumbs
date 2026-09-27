"""
State derivation tests (CLAUDE.md §32, §33).

These are the tests that matter most. State derivation is what the product
claims: if it is wrong, the app confidently tells someone the wrong thing about
their immigration file. Every case from §33 that concerns derivation is here.
"""
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone, translation

from apps.directory.models import Organization
from apps.directory.seed import seed_directory
from apps.journeys import enums
from apps.journeys.models import Breadcrumb, Journey
from apps.journeys.services import recalculate_journey_state
from apps.journeys.state import compute_staleness, derive_journey_state


def aware(year, month, day, hour=9):
    return timezone.make_aware(
        datetime.combine(datetime(year, month, day).date(), time(hour, 0))
    )


class StateTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()
        cls.ircc = Organization.objects.get(short_name="IRCC")
        cls.user = get_user_model().objects.create(username="citizen@example.test")

    def setUp(self):
        self.journey = Journey.objects.create(
            user=self.user,
            title="Study Permit Extension",
            goal="Extend my study permit",
            primary_organization=self.ircc,
        )

    def add(self, **kwargs):
        defaults = {
            "journey": self.journey,
            "kind": enums.BreadcrumbKind.INTERACTION,
            "channel": enums.Channel.PHONE,
            "title": "Called IRCC",
            "organization": self.ircc,
            "organization_name": self.ircc.name,
            "occurred_at": aware(2026, 9, 24),
            "source_type": enums.SourceType.USER_REPORTED,
            "is_confirmed": True,
            "structured_data": {},
        }
        defaults.update(kwargs)
        return Breadcrumb.objects.create(**defaults)

    def derive(self):
        return derive_journey_state(
            self.journey, list(self.journey.breadcrumbs.select_related("organization"))
        )


class EmptyJourneyTests(StateTestCase):
    def test_no_breadcrumbs_is_active_and_says_so_plainly(self):
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.ACTIVE)
        self.assertIn("Nothing has been recorded", state.current_state)
        self.assertEqual(state.next_action_code, enums.NextActionCode.NONE)
        self.assertEqual(state.considered_count, 0)


class CaseAStatusReportedTests(StateTestCase):
    """§33 Case A -- a normal reported status becomes WAITING."""

    def test_reported_processing_derives_waiting(self):
        self.add(
            structured_data={
                "reported_status": enums.ReportedStatus.PROCESSING,
            }
        )
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.WAITING)
        self.assertEqual(state.next_action_code, enums.NextActionCode.WAIT)
        self.assertEqual(state.latest_reported_status, enums.ReportedStatus.PROCESSING)

    def test_state_is_phrased_as_a_record_not_a_live_fact(self):
        """
        Tense discipline (§18).

        The system has no authoritative live data, so it must never say "your
        application is processing". Getting this wrong would mislead someone
        about their status, which is the most consequential thing this product
        could do badly.
        """
        self.add(structured_data={"reported_status": enums.ReportedStatus.PROCESSING})
        state = self.derive()
        lowered = state.current_state.lower()
        self.assertIn("recorded", lowered)
        self.assertIn("reported", lowered)
        for forbidden in (
            "your application is currently",
            "is currently processing",
            "your status is",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_provenance_is_always_cited(self):
        breadcrumb = self.add(
            structured_data={"reported_status": enums.ReportedStatus.PROCESSING}
        )
        state = self.derive()
        self.assertEqual(state.evidence_breadcrumb_id, str(breadcrumb.id))
        self.assertEqual(state.evidence_source_type, enums.SourceType.USER_REPORTED)
        self.assertEqual(state.evidence_organization, "IRCC")


class CaseBInstructionTests(StateTestCase):
    """§33 Case B -- a recorded instruction drives the next action."""

    def test_do_not_resubmit_instruction_produces_wait(self):
        self.add(
            structured_data={
                "reported_status": enums.ReportedStatus.PROCESSING,
                "instruction": "Do not submit another application",
                "suggested_next_action": enums.NextActionCode.WAIT,
            }
        )
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.WAITING)
        self.assertEqual(state.next_action_code, enums.NextActionCode.WAIT)
        self.assertIn("Do not submit another application", state.next_action)

    def test_instruction_alone_implies_waiting_without_a_status(self):
        self.add(structured_data={"instruction": "They said to just wait"})
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.WAITING)

    def test_next_action_repeats_the_citizens_instruction_rather_than_inventing_one(self):
        self.add(
            structured_data={
                "instruction": "Upload your proof of enrolment",
                "suggested_next_action": enums.NextActionCode.UPLOAD,
            }
        )
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.ACTION_REQUIRED)
        self.assertIn("Upload your proof of enrolment", state.next_action)


class ActionRequiredTests(StateTestCase):
    def test_outstanding_request_for_a_document_requires_action(self):
        self.add(
            occurred_at=aware(2026, 9, 25),
            structured_data={
                "reported_status": enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED,
                "instruction": "Send a copy of your passport",
                "suggested_next_action": enums.NextActionCode.PROVIDE_DOCUMENT,
            },
        )
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.ACTION_REQUIRED)
        self.assertEqual(
            state.next_action_code, enums.NextActionCode.PROVIDE_DOCUMENT
        )

    def test_a_later_status_supersedes_an_earlier_outstanding_action(self):
        """
        An instruction is not forever.

        If the citizen was asked for a document on the 20th and then told on the
        24th that the file is processing, they are waiting -- not still chasing
        the document. Telling them to act would send them to a phone queue for
        nothing.
        """
        self.add(
            occurred_at=aware(2026, 9, 20),
            structured_data={
                "instruction": "Send a copy of your passport",
                "suggested_next_action": enums.NextActionCode.PROVIDE_DOCUMENT,
            },
        )
        self.add(
            occurred_at=aware(2026, 9, 24),
            title="Called IRCC again",
            structured_data={"reported_status": enums.ReportedStatus.PROCESSING},
        )
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.WAITING)


class TerminalOutcomeTests(StateTestCase):
    def test_approval_completes_the_journey(self):
        self.add(
            kind=enums.BreadcrumbKind.STATUS_UPDATE,
            structured_data={"reported_status": enums.ReportedStatus.APPROVED},
        )
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.COMPLETED)
        self.assertEqual(state.next_action_code, enums.NextActionCode.NONE)

    def test_refusal_does_not_produce_advice(self):
        """
        A refusal is a legal matter. The product must not suggest an appeal or
        any other course of action (§4.2) -- it reports what was recorded.
        """
        self.add(
            kind=enums.BreadcrumbKind.STATUS_UPDATE,
            structured_data={"reported_status": enums.ReportedStatus.REFUSED},
        )
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.COMPLETED)
        self.assertIn("No further action has been recorded", state.next_action)
        self.assertNotIn("appeal", state.next_action.lower())


class CaseGAIIsNotEvidenceTests(StateTestCase):
    """§33 Case G -- generated content must never affect derived state."""

    def test_ai_interpretation_breadcrumbs_are_excluded_from_derivation(self):
        self.add(structured_data={"reported_status": enums.ReportedStatus.PROCESSING})
        self.add(
            occurred_at=aware(2026, 9, 30),
            title="Generated summary",
            source_type=enums.SourceType.AI_INTERPRETATION,
            structured_data={
                "reported_status": enums.ReportedStatus.APPROVED,
                "suggested_next_action": enums.NextActionCode.NONE,
            },
        )
        state = self.derive()
        # The newer AI row claims approval; it must be ignored entirely.
        self.assertEqual(state.status, enums.JourneyStatus.WAITING)
        self.assertEqual(state.considered_count, 1)

    def test_unconfirmed_drafts_are_excluded_from_derivation(self):
        self.add(structured_data={"reported_status": enums.ReportedStatus.PROCESSING})
        self.add(
            occurred_at=aware(2026, 9, 30),
            title="Unconfirmed draft",
            is_confirmed=False,
            structured_data={
                "reported_status": enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED,
                "suggested_next_action": enums.NextActionCode.UPLOAD,
            },
        )
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.WAITING)


class CaseHEditRecalculationTests(StateTestCase):
    """§33 Case H -- correcting a breadcrumb re-derives the journey."""

    def test_correcting_a_status_changes_the_journey_state(self):
        breadcrumb = self.add(
            structured_data={"reported_status": enums.ReportedStatus.PROCESSING}
        )
        self.assertEqual(
            recalculate_journey_state(self.journey).status,
            enums.JourneyStatus.WAITING,
        )

        breadcrumb.structured_data = {
            "reported_status": enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED,
            "instruction": "Provide your proof of funds",
            "suggested_next_action": enums.NextActionCode.PROVIDE_DOCUMENT,
        }
        breadcrumb.save(update_fields=["structured_data"])

        state = recalculate_journey_state(self.journey)
        self.assertEqual(state.status, enums.JourneyStatus.ACTION_REQUIRED)
        self.journey.refresh_from_db()
        self.assertEqual(self.journey.status, enums.JourneyStatus.ACTION_REQUIRED)
        self.assertIn("proof of funds", self.journey.next_action)


class CaseIDeleteFallbackTests(StateTestCase):
    """§33 Case I -- deleting the newest status falls back to earlier evidence."""

    def test_deleting_latest_status_reverts_to_previous_evidence(self):
        self.add(
            occurred_at=aware(2026, 9, 18),
            kind=enums.BreadcrumbKind.ACTION,
            channel=enums.Channel.WEB,
            title="Application submitted",
            structured_data={"reported_status": enums.ReportedStatus.SUBMITTED},
        )
        latest = self.add(
            occurred_at=aware(2026, 9, 24),
            structured_data={
                "reported_status": enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED,
                "instruction": "Send your transcript",
                "suggested_next_action": enums.NextActionCode.PROVIDE_DOCUMENT,
            },
        )
        self.assertEqual(
            recalculate_journey_state(self.journey).status,
            enums.JourneyStatus.ACTION_REQUIRED,
        )

        latest.delete()
        state = recalculate_journey_state(self.journey)
        self.assertEqual(state.status, enums.JourneyStatus.WAITING)
        self.assertEqual(state.latest_reported_status, enums.ReportedStatus.SUBMITTED)
        self.assertEqual(state.latest_instruction, "")


class DerivationPurityTests(StateTestCase):
    def test_derivation_is_order_independent(self):
        """Input order must not change the answer; only timestamps may."""
        self.add(
            occurred_at=aware(2026, 9, 18),
            structured_data={"reported_status": enums.ReportedStatus.SUBMITTED},
        )
        self.add(
            occurred_at=aware(2026, 9, 24),
            structured_data={"reported_status": enums.ReportedStatus.PROCESSING},
        )
        breadcrumbs = list(self.journey.breadcrumbs.select_related("organization"))
        forward = derive_journey_state(self.journey, breadcrumbs)
        backward = derive_journey_state(self.journey, list(reversed(breadcrumbs)))
        self.assertEqual(forward.as_dict(), backward.as_dict())

    def test_derivation_does_not_write_to_the_database(self):
        self.add(structured_data={"reported_status": enums.ReportedStatus.PROCESSING})
        before = self.journey.updated_at
        derive_journey_state(
            self.journey, list(self.journey.breadcrumbs.all())
        )
        self.journey.refresh_from_db()
        self.assertEqual(before, self.journey.updated_at)

    def test_same_day_events_break_ties_by_creation_order(self):
        """Two calls on one day: the one recorded later wins."""
        same_day = aware(2026, 9, 24)
        self.add(
            occurred_at=same_day,
            structured_data={"reported_status": enums.ReportedStatus.PROCESSING},
        )
        self.add(
            occurred_at=same_day,
            title="Called IRCC back",
            structured_data={
                "reported_status": enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED,
                "suggested_next_action": enums.NextActionCode.PROVIDE_DOCUMENT,
            },
        )
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.ACTION_REQUIRED)


class ReferenceCollectionTests(StateTestCase):
    def test_references_are_collected_for_the_handoff(self):
        self.add(structured_data={"reference": "DEMO-1", "reported_status": "PROCESSING"})
        self.add(
            occurred_at=aware(2026, 9, 25),
            title="Second call",
            structured_data={"reference": "DEMO-1"},
        )
        state = self.derive()
        self.assertEqual(state.references, ("DEMO-1",))


class MultiOrganizationTests(StateTestCase):
    def test_state_names_the_organization_from_the_latest_status(self):
        """
        The cross-institution case: the citizen deals with a university and a
        federal department in one journey, and the derived state must attribute
        the status to whoever actually reported it.
        """
        university = Organization.objects.get(short_name="International Office")
        self.add(
            occurred_at=aware(2026, 9, 22),
            channel=enums.Channel.EMAIL,
            title="Emailed International Office",
            organization=university,
            organization_name=university.name,
            structured_data={"instruction": "Nothing further needed from us"},
        )
        self.add(
            occurred_at=aware(2026, 9, 24),
            structured_data={"reported_status": enums.ReportedStatus.PROCESSING},
        )
        state = self.derive()
        self.assertEqual(state.evidence_organization, "IRCC")
        self.assertIn("IRCC", state.current_state)


class FutureDatedEvidenceTests(StateTestCase):
    def test_future_dated_breadcrumb_is_still_the_latest(self):
        """
        A mistyped year should not silently corrupt the answer; derivation orders
        strictly by time, and the UI is expected to flag implausible dates during
        review rather than the domain silently dropping evidence.
        """
        self.add(structured_data={"reported_status": enums.ReportedStatus.PROCESSING})
        future = timezone.now() + timedelta(days=400)
        self.add(
            occurred_at=future,
            title="Mistyped year",
            structured_data={
                "reported_status": enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED,
                "suggested_next_action": enums.NextActionCode.UPLOAD,
            },
        )
        state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.ACTION_REQUIRED)


class StalenessTests(StateTestCase):
    """
    Proactive check-ins. Deterministic, zero AI calls (§4.2: this may only ever
    describe the citizen's own recording gap, never a government timeline).
    """

    def backdate(self, breadcrumb, when):
        """created_at is auto_now_add; set it directly for a deterministic test."""
        Breadcrumb.objects.filter(pk=breadcrumb.pk).update(created_at=when)
        breadcrumb.refresh_from_db()
        return breadcrumb

    def test_no_breadcrumbs_is_never_stale(self):
        result = compute_staleness(
            enums.JourneyStatus.WAITING, [], now=timezone.now()
        )
        self.assertFalse(result.is_stale)
        self.assertIsNone(result.days_since_last_recorded)

    def test_completed_journey_is_never_stale_no_matter_how_old(self):
        breadcrumb = self.add(
            structured_data={"reported_status": enums.ReportedStatus.APPROVED}
        )
        old = timezone.now() - timedelta(days=400)
        self.backdate(breadcrumb, old)
        result = compute_staleness(
            enums.JourneyStatus.COMPLETED, [breadcrumb], now=timezone.now()
        )
        self.assertFalse(result.is_stale)

    def test_action_required_is_not_stale_just_under_the_threshold(self):
        breadcrumb = self.add()
        now = timezone.now()
        self.backdate(breadcrumb, now - timedelta(days=2, hours=23))
        result = compute_staleness(
            enums.JourneyStatus.ACTION_REQUIRED, [breadcrumb], now=now
        )
        self.assertFalse(result.is_stale)

    def test_action_required_is_stale_at_the_threshold(self):
        breadcrumb = self.add()
        now = timezone.now()
        self.backdate(breadcrumb, now - timedelta(days=3))
        result = compute_staleness(
            enums.JourneyStatus.ACTION_REQUIRED, [breadcrumb], now=now
        )
        self.assertTrue(result.is_stale)
        self.assertIn("3 days", result.message)

    def test_waiting_uses_a_longer_threshold_than_action_required(self):
        breadcrumb = self.add()
        now = timezone.now()
        # Past the ACTION_REQUIRED threshold (3d) but not the WAITING one (10d).
        self.backdate(breadcrumb, now - timedelta(days=5))
        result = compute_staleness(
            enums.JourneyStatus.WAITING, [breadcrumb], now=now
        )
        self.assertFalse(result.is_stale)

        self.backdate(breadcrumb, now - timedelta(days=10))
        result = compute_staleness(
            enums.JourneyStatus.WAITING, [breadcrumb], now=now
        )
        self.assertTrue(result.is_stale)

    def test_staleness_uses_created_at_not_occurred_at(self):
        """
        Backdating old history today must read as "just recorded something,"
        not as stale -- staleness is about the citizen's own recording cadence,
        not the date they claim the event happened.
        """
        breadcrumb = self.add(occurred_at=aware(2020, 1, 1))
        now = timezone.now()
        result = compute_staleness(
            enums.JourneyStatus.WAITING, [breadcrumb], now=now
        )
        self.assertFalse(result.is_stale)

    def test_staleness_message_never_mentions_government_or_processing_time(self):
        """
        §4.2: this may only ever describe the citizen's own recording gap. A
        message that implied an official processing-time expectation would be
        inventing a fact the product has no authority to state.
        """
        breadcrumb = self.add()
        now = timezone.now()
        self.backdate(breadcrumb, now - timedelta(days=30))
        result = compute_staleness(
            enums.JourneyStatus.ACTION_REQUIRED, [breadcrumb], now=now
        )
        lowered = result.message.lower()
        for forbidden in ("ircc", "government", "processing time", "business day"):
            self.assertNotIn(forbidden, lowered)

    def test_ai_generated_breadcrumbs_do_not_count_toward_recency(self):
        """Only counts_as_evidence rows participate -- an AI row backdated to
        "now" must not mask a genuinely stale journey."""
        old = self.add()
        now = timezone.now()
        self.backdate(old, now - timedelta(days=30))
        recent_ai = self.add(
            title="Generated note",
            source_type=enums.SourceType.AI_INTERPRETATION,
        )
        result = compute_staleness(
            enums.JourneyStatus.ACTION_REQUIRED, [old, recent_ai], now=now
        )
        self.assertTrue(result.is_stale)


class FrenchStateDerivationTests(StateTestCase):
    """
    French localization, Phase C: state derivation must read as genuine
    French, not English with translated labels bolted on, when the citizen's
    chosen language is French (django.utils.translation active locale).
    """

    def test_empty_state_is_french(self):
        with translation.override("fr"):
            state = self.derive()
        self.assertIn("Rien n'a encore été enregistré", state.current_state)
        self.assertIn("Enregistrez ce qui s'est passé", state.next_action)

    def test_waiting_state_is_french_including_the_organization_clause(self):
        self.add(structured_data={"reported_status": enums.ReportedStatus.PROCESSING})
        with translation.override("fr"):
            state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.WAITING)
        self.assertIn("Votre dernière interaction enregistrée avec", state.current_state)
        self.assertIn("toujours en traitement", state.current_state)
        self.assertIn("Attendez une mise à jour", state.next_action)

    def test_completed_state_is_french(self):
        self.add(structured_data={"reported_status": enums.ReportedStatus.APPROVED})
        with translation.override("fr"):
            state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.COMPLETED)
        self.assertIn("a rapporté le résultat comme étant", state.current_state)
        self.assertIn("approuvé", state.current_state)

    def test_explicit_instruction_is_prefixed_in_french(self):
        self.add(
            structured_data={
                "suggested_next_action": enums.NextActionCode.UPLOAD,
                "instruction": "Envoyez une copie de votre passeport",
            }
        )
        with translation.override("fr"):
            state = self.derive()
        self.assertEqual(state.status, enums.JourneyStatus.ACTION_REQUIRED)
        self.assertTrue(state.next_action.startswith("Fournissez ce qui a été demandé : "))

    def test_default_locale_is_unaffected(self):
        """English behaviour must be untouched by the French catalog existing."""
        state = self.derive()
        self.assertIn("Nothing has been recorded", state.current_state)


class FrenchStalenessTests(StateTestCase):
    def test_staleness_message_is_french(self):
        breadcrumb = self.add()
        now = timezone.now()
        breadcrumb.created_at = now - timedelta(days=30)
        breadcrumb.save(update_fields=["created_at"])
        with translation.override("fr"):
            result = compute_staleness(
                enums.JourneyStatus.ACTION_REQUIRED, [breadcrumb], now=now
            )
        self.assertIn("Vous n'avez rien enregistré de nouveau depuis", result.message)
