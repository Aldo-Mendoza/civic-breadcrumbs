"""
Write paths for the Journey domain.

Views orchestrate; this module holds the behaviour (§7). Nothing here knows about
HTTP, serializers or the Gemini SDK, which is what lets the API shape change
without touching the rules that matter.

The single most important function is ``recalculate_journey_state``: it is called
after every mutation so that the denormalized ``current_state`` and
``next_action`` can never drift from the confirmed evidence they summarise (§9.1).
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.directory.models import OfficialSource
from apps.directory.selectors import match_organization_by_name, match_organization_by_topic

from . import duplicates, enums
from .models import Breadcrumb, Guide, GuideStep, Journey
from .selectors import evidence_breadcrumbs
from .state import derive_journey_state
from common.auth import is_guest_user
from common.exceptions import JourneyLimitExceeded

logger = logging.getLogger("civic.journeys")


def recalculate_journey_state(journey, persist=True):
    """
    Re-derive and cache the journey's state from confirmed evidence.

    Call this after any change to a breadcrumb. Because derivation is pure and
    reads only confirmed, non-AI rows, correcting or deleting a breadcrumb
    automatically produces a correct new state -- there is no incremental update
    path that could get out of step.
    """
    breadcrumbs = list(evidence_breadcrumbs(journey))
    state = derive_journey_state(journey, breadcrumbs)

    if persist:
        journey.status = state.status
        journey.current_state = state.current_state
        journey.next_action = state.next_action
        journey.next_action_code = state.next_action_code
        journey.save(
            update_fields=[
                "status",
                "current_state",
                "next_action",
                "next_action_code",
                "updated_at",
            ]
        )
    return state


def create_guide(journey, draft=None):
    """Persist a bounded suggested plan without turning it into evidence."""
    if draft is None or not getattr(draft, "guide_steps", None):
        from services.ai.rules import RuleBasedAIService

        draft = RuleBasedAIService().extract_journey(
            " ".join(part for part in (journey.title, journey.goal) if part)
        )

    guide, _ = Guide.objects.update_or_create(
        journey=journey,
        defaults={
            "summary": draft.guide_summary,
            "generated_by": draft.extractor,
            "needs_clarification": draft.needs_clarification,
            "clarification_question": draft.clarification_question,
        },
    )
    guide.steps.all().delete()
    organization = journey.primary_organization
    # Strictly scoped to this organization -- unlike official_sources_for()
    # (used elsewhere for a "show something helpful anyway" fallback), a guide
    # step must never borrow a different organization's link just because this
    # one has nothing curated. That would be actively misleading, not merely
    # imprecise (§21).
    candidates = (
        list(OfficialSource.objects.filter(organization=organization, active=True))
        if organization is not None
        else []
    )
    steps = draft.guide_steps[:6]
    assignments = _assign_official_sources(steps, candidates)
    for position, (step, source) in enumerate(zip(steps, assignments), start=1):
        GuideStep.objects.create(
            guide=guide,
            position=position,
            title=step.title,
            description=step.description,
            organization=organization,
            official_source=source,
        )
    return guide


def _assign_official_sources(steps, candidates):
    """
    Pick one official source per guide step, so distinct steps that need
    different things (e.g. "gather documents" vs. "check processing times")
    get distinct, relevant links instead of the whole guide silently sharing
    one link or none at all.

    Preference order per step: (1) an exact topic match against the step's own
    ``topic`` hint, since that's the most specific real signal available;
    (2) otherwise, round-robin across whatever curated sources exist for the
    organization, so steps still show *some* variety rather than collapsing
    onto a single repeated link; (3) ``None`` when there is nothing curated
    for this organization at all -- an honest gap, never a guess (§21).
    """
    if not candidates:
        return [None for _ in steps]

    by_topic = {source.topic.strip().lower(): source for source in candidates if source.topic}
    assignments = []
    fallback_index = 0
    for step in steps:
        topic = (step.topic or "").strip().lower()
        match = by_topic.get(topic) if topic else None
        if match is None and topic:
            # Loose match: either phrase contains the other (e.g. step topic
            # "required documents" against a source topic "documents").
            match = next(
                (
                    source
                    for source in candidates
                    if source.topic
                    and (topic in source.topic.lower() or source.topic.lower() in topic)
                ),
                None,
            )
        if match is None:
            match = candidates[fallback_index % len(candidates)]
            fallback_index += 1
        assignments.append(match)
    return assignments


def create_journey(
    user,
    title,
    goal,
    organization=None,
    organization_name="",
    guide_draft=None,
):
    """Create a journey and derive its (empty) starting state."""
    if organization is None and organization_name:
        organization = match_organization_by_name(organization_name)
    if organization is None:
        organization = match_organization_by_topic(" ".join([title or "", goal or ""]))

    with transaction.atomic():
        # Lock the owner row so concurrent creates cannot both pass the quota
        # check. Authorization and quotas are application rules, not Auth0 rules.
        get_user_model().objects.select_for_update().get(pk=user.pk)
        limit = (
            settings.GUEST_MAX_ACTIVE_JOURNEYS
            if is_guest_user(user)
            else settings.USER_MAX_ACTIVE_JOURNEYS
        )
        active_count = Journey.objects.filter(user=user).exclude(
            status__in=[enums.JourneyStatus.COMPLETED, enums.JourneyStatus.ARCHIVED]
        ).count()
        if active_count >= limit:
            raise JourneyLimitExceeded(limit)
        journey = Journey.objects.create(
            user=user,
            title=(title or "").strip()[:200] or "My journey",
            goal=(goal or "").strip(),
            primary_organization=organization,
        )
        create_guide(journey, guide_draft)
        state = recalculate_journey_state(journey)

    logger.info("journey_created journey_id=%s", journey.id)
    return journey, state


def add_breadcrumb(
    journey,
    *,
    kind,
    title,
    occurred_at=None,
    channel=enums.Channel.UNKNOWN,
    raw_text="",
    organization_name="",
    organization=None,
    source_type=enums.SourceType.USER_REPORTED,
    structured_data=None,
    is_confirmed=True,
    request_id=None,
    check_duplicates=True,
    guide_step=None,
):
    """
    Persist confirmed evidence and recalculate state.

    Returns ``(breadcrumb, created, warnings)``. A repeated ``request_id`` returns
    the original row with ``created=False`` rather than raising, so a retry after
    a timeout is safe (§25).
    """
    existing = duplicates.find_by_request_id(journey, request_id)
    if existing is not None:
        return existing, False, []

    warnings = []
    if check_duplicates and raw_text:
        similar = duplicates.find_similar_recent(journey, raw_text)
        if similar is not None:
            warnings.append(duplicates.duplicate_warning(similar))

    if organization is None and organization_name:
        organization = match_organization_by_name(organization_name)

    payload = dict(structured_data or {})

    try:
        with transaction.atomic():
            breadcrumb = Breadcrumb.objects.create(
                journey=journey,
                guide_step=guide_step,
                kind=kind,
                channel=channel or enums.Channel.UNKNOWN,
                raw_text=raw_text or "",
                title=(title or "").strip()[:300] or "Recorded event",
                organization_name=(organization_name or "").strip()[:200],
                organization=organization,
                occurred_at=occurred_at or timezone.now(),
                source_type=source_type,
                structured_data=payload,
                is_confirmed=is_confirmed,
                request_id=request_id or None,
            )
    except IntegrityError:
        # Two concurrent retries with the same token; the winner's row is correct.
        existing = duplicates.find_by_request_id(journey, request_id)
        if existing is not None:
            return existing, False, warnings
        raise

    recalculate_journey_state(journey)
    if guide_step is not None and guide_step.status == enums.GuideStepStatus.NOT_STARTED:
        guide_step.status = enums.GuideStepStatus.IN_PROGRESS
        guide_step.save(update_fields=["status", "updated_at"])
    logger.info(
        "breadcrumb_created journey_id=%s breadcrumb_id=%s kind=%s source=%s",
        journey.id,
        breadcrumb.id,
        kind,
        source_type,
    )
    return breadcrumb, True, warnings


def update_breadcrumb(breadcrumb, **fields):
    """
    Apply a correction and recalculate the journey.

    ``raw_text`` is deliberately not updatable: the citizen's original words are
    the audit trail, and an interpretation being wrong is not a reason to rewrite
    what they said (§10). Corrections change the structured reading instead.
    """
    allowed = {
        "kind",
        "channel",
        "title",
        "organization_name",
        "occurred_at",
        "source_type",
        "is_confirmed",
    }
    updated = []

    for key, value in fields.items():
        if key in allowed and value is not None:
            setattr(breadcrumb, key, value)
            updated.append(key)

    structured = fields.get("structured_data")
    if structured is not None:
        merged = dict(breadcrumb.structured_data or {})
        merged.update(structured)
        breadcrumb.structured_data = merged
        updated.append("structured_data")

    if "organization_name" in updated:
        breadcrumb.organization = match_organization_by_name(
            breadcrumb.organization_name
        )
        updated.append("organization")

    if updated:
        breadcrumb.save(update_fields=list(set(updated)) + ["updated_at"])

    state = recalculate_journey_state(breadcrumb.journey)
    logger.info(
        "breadcrumb_updated journey_id=%s breadcrumb_id=%s fields=%s",
        breadcrumb.journey_id,
        breadcrumb.id,
        ",".join(sorted(set(updated))),
    )
    return breadcrumb, state


def delete_breadcrumb(breadcrumb):
    """
    Remove a breadcrumb and fall the journey back to earlier evidence.

    No special handling is needed for deleting the newest status: derivation runs
    again over whatever remains (§33 Case I).
    """
    journey = breadcrumb.journey
    breadcrumb_id = breadcrumb.id
    guide_step_id = breadcrumb.guide_step_id
    linked_steps = list(GuideStep.objects.filter(completion_breadcrumb=breadcrumb))
    breadcrumb.delete()
    for step in linked_steps:
        step.status = enums.GuideStepStatus.NOT_STARTED
        step.completion_breadcrumb = None
        step.save(update_fields=["status", "completion_breadcrumb", "updated_at"])
    if guide_step_id and not linked_steps:
        step = GuideStep.objects.filter(pk=guide_step_id).first()
        if (
            step
            and step.status == enums.GuideStepStatus.IN_PROGRESS
            and not step.breadcrumbs.exists()
        ):
            step.status = enums.GuideStepStatus.NOT_STARTED
            step.save(update_fields=["status", "updated_at"])
    state = recalculate_journey_state(journey)
    logger.info(
        "breadcrumb_deleted journey_id=%s breadcrumb_id=%s", journey.id, breadcrumb_id
    )
    return state


def complete_guide_step(guide_step):
    """Explicitly complete a suggestion and create one idempotent audit record."""
    with transaction.atomic():
        guide_step = GuideStep.objects.select_for_update().select_related(
            "guide__journey", "organization", "completion_breadcrumb"
        ).get(pk=guide_step.pk)
        if guide_step.completion_breadcrumb_id:
            return guide_step, guide_step.completion_breadcrumb, False

        journey = guide_step.guide.journey
        breadcrumb, created, _ = add_breadcrumb(
            journey,
            guide_step=guide_step,
            kind=enums.BreadcrumbKind.ACTION,
            channel=enums.Channel.OTHER,
            title=f"Completed guide step: {guide_step.title}",
            raw_text=f"I marked the guide step '{guide_step.title}' complete.",
            organization=guide_step.organization,
            organization_name=(guide_step.organization.name if guide_step.organization else ""),
            source_type=enums.SourceType.USER_REPORTED,
            structured_data={
                "reported_status": enums.ReportedStatus.UNKNOWN,
                "suggested_next_action": enums.NextActionCode.NONE,
                "guide_step_id": str(guide_step.id),
                "extractor": "none",
            },
            request_id=f"guide-step-{guide_step.id}-complete",
            check_duplicates=False,
        )
        guide_step.status = enums.GuideStepStatus.COMPLETED
        guide_step.completion_breadcrumb = breadcrumb
        guide_step.save(update_fields=["status", "completion_breadcrumb", "updated_at"])
        return guide_step, breadcrumb, created


def save_draft_as_note(journey, raw_text, request_id=None, guide_step=None):
    """
    The always-available escape hatch (§28).

    When interpretation fails -- model down, output invalid, wording too
    ambiguous to read -- the citizen can still capture what happened in their own
    words. Losing someone's record because a vendor had an outage is the one
    failure this product cannot afford.
    """
    from common.utils import truncate

    return add_breadcrumb(
        journey,
        kind=enums.BreadcrumbKind.NOTE,
        channel=enums.Channel.UNKNOWN,
        title=truncate(raw_text, 80) or "Note",
        raw_text=raw_text,
        source_type=enums.SourceType.USER_REPORTED,
        structured_data={"extractor": "none", "saved_as_note": True},
        request_id=request_id,
        guide_step=guide_step,
    )
