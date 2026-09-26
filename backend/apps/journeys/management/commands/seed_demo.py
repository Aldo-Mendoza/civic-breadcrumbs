"""
Deterministic demo seed (CLAUDE.md §34, §35).

Run this early and often. It exists for three reasons:

1. **Demo resilience.** The seeded journey exercises the timeline, current state,
   "you left off here", "I am stuck", the responsible organization, official
   sources and the handoff without a single model call. A provider outage during
   the presentation costs nothing (§35).
2. **Parallel frontend work.** Real, shaped data exists from the first hour, so
   the client can be built against it rather than against fixtures.
3. **Honest test data.** Everything here is synthetic. No real SIN, passport
   number, application identifier or private correspondence goes anywhere near
   the demo (§29, §30). The reference number below is deliberately fake.

Idempotent: re-running updates the same records rather than duplicating them.
Pass --reset to rebuild the demo journey from scratch.
"""
from datetime import date, datetime, time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.directory.models import Organization
from apps.directory.seed import seed_directory
from apps.journeys import enums
from apps.journeys.models import Breadcrumb, Journey
from apps.journeys.services import recalculate_journey_state

#: Anchored to the spec's timeline (§34). Recent enough that the demo reads as
#: "this happened over the last week".
TIMELINE_YEAR = 2026

DEMO_JOURNEY_TITLE = "Study Permit Extension"

#: Synthetic. Not a real IRCC application number format in use.
DEMO_REFERENCE = "DEMO-4417829"


def _aware(year, month, day, hour=9, minute=0):
    return timezone.make_aware(datetime.combine(date(year, month, day), time(hour, minute)))


def _breadcrumbs(ircc, university):
    """
    The seeded journey: an international student extending a study permit.

    The shape matters for the demo. By the end, the latest evidence is a reported
    status of PROCESSING plus an instruction not to reapply, so derivation lands
    on WAITING with next action WAIT -- which lets the presenter show the system
    correctly saying "no action is needed from you", the answer a chatbot is
    least likely to give confidently.
    """
    return [
        {
            "kind": enums.BreadcrumbKind.ACTION,
            "channel": enums.Channel.WEB,
            "title": "Application submitted",
            "raw_text": (
                "I submitted my study permit extension application through the "
                "online portal."
            ),
            "organization": ircc,
            "occurred_at": _aware(TIMELINE_YEAR, 9, 18, 10, 15),
            "source_type": enums.SourceType.USER_REPORTED,
            "structured_data": {
                "reported_status": enums.ReportedStatus.SUBMITTED,
                "instruction": "",
                "suggested_next_action": enums.NextActionCode.WAIT,
                "reference": DEMO_REFERENCE,
                "extractor": "seed",
            },
        },
        {
            "kind": enums.BreadcrumbKind.STATUS_UPDATE,
            "channel": enums.Channel.EMAIL,
            "title": "Confirmation received",
            "raw_text": (
                "I got an automatic email confirming they received my "
                "application."
            ),
            "organization": ircc,
            "occurred_at": _aware(TIMELINE_YEAR, 9, 18, 10, 42),
            "source_type": enums.SourceType.USER_REPORTED,
            "structured_data": {
                "reported_status": enums.ReportedStatus.RECEIVED,
                "instruction": "",
                "suggested_next_action": enums.NextActionCode.WAIT,
                "reference": DEMO_REFERENCE,
                "extractor": "seed",
            },
        },
        {
            "kind": enums.BreadcrumbKind.INTERACTION,
            "channel": enums.Channel.EMAIL,
            "title": "Emailed International Office",
            "raw_text": (
                "I emailed the university international office to ask whether "
                "they needed anything else from me while I wait."
            ),
            "organization": university,
            "occurred_at": _aware(TIMELINE_YEAR, 9, 22, 14, 5),
            "source_type": enums.SourceType.USER_REPORTED,
            "structured_data": {
                "reported_status": enums.ReportedStatus.UNKNOWN,
                "instruction": (
                    "No additional document is needed from the university right now"
                ),
                "suggested_next_action": enums.NextActionCode.NONE,
                "extractor": "seed",
            },
        },
        {
            "kind": enums.BreadcrumbKind.INTERACTION,
            "channel": enums.Channel.PHONE,
            "title": "Called IRCC",
            "raw_text": (
                "I called IRCC this morning and they told me my application is "
                "still processing and that I should not submit another one."
            ),
            "organization": ircc,
            "occurred_at": _aware(TIMELINE_YEAR, 9, 24, 9, 30),
            "source_type": enums.SourceType.USER_REPORTED,
            "structured_data": {
                "reported_status": enums.ReportedStatus.PROCESSING,
                "instruction": "Do not submit another application",
                "suggested_next_action": enums.NextActionCode.WAIT,
                "reference": DEMO_REFERENCE,
                "confidence": 0.95,
                "extractor": "seed",
            },
        },
    ]


class Command(BaseCommand):
    help = "Seed the curated directory and a synthetic demo journey."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete and rebuild the demo journey before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        seed_directory(stdout=self.stdout)

        ircc = Organization.objects.get(short_name="IRCC")
        university = Organization.objects.get(short_name="International Office")

        user_model = get_user_model()
        email = settings.DEV_USER_EMAIL
        user, user_created = user_model.objects.get_or_create(
            username=email, defaults={"email": email}
        )
        if user_created:
            # Unusable password: the demo user is not a login route.
            user.set_unusable_password()
            user.save(update_fields=["password"])

        if options["reset"]:
            deleted, _ = Journey.objects.filter(
                user=user, title=DEMO_JOURNEY_TITLE
            ).delete()
            if deleted:
                self.stdout.write("Removed the previous demo journey.")

        journey, created = Journey.objects.get_or_create(
            user=user,
            title=DEMO_JOURNEY_TITLE,
            defaults={
                "goal": (
                    "Extend my study permit so I can keep studying legally in "
                    "Canada"
                ),
                "primary_organization": ircc,
            },
        )
        if not created:
            journey.primary_organization = ircc
            journey.save(update_fields=["primary_organization"])

        for entry in _breadcrumbs(ircc, university):
            Breadcrumb.objects.update_or_create(
                journey=journey,
                title=entry["title"],
                defaults={
                    "kind": entry["kind"],
                    "channel": entry["channel"],
                    "raw_text": entry["raw_text"],
                    "organization": entry["organization"],
                    "organization_name": entry["organization"].name,
                    "occurred_at": entry["occurred_at"],
                    "source_type": entry["source_type"],
                    "structured_data": entry["structured_data"],
                    "is_confirmed": True,
                },
            )

        state = recalculate_journey_state(journey)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo journey ready."))
        self.stdout.write("  user:          " + user.username)
        self.stdout.write("  journey:       " + journey.title)
        self.stdout.write("  journey id:    " + str(journey.id))
        self.stdout.write("  breadcrumbs:   " + str(journey.breadcrumbs.count()))
        self.stdout.write("  status:        " + state.status)
        self.stdout.write("  current state: " + state.current_state)
        self.stdout.write("  next action:   " + state.next_action)
        self.stdout.write("")
        self.stdout.write("All demo data is synthetic. Reference " + DEMO_REFERENCE)
