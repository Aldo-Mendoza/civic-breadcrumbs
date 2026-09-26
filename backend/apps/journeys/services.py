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

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.directory.selectors import match_organization_by_name

from . import duplicates, enums
from .models import Breadcrumb, Journey
from .selectors import evidence_breadcrumbs
from .state import derive_journey_state

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


def create_journey(user, title, goal, organization=None, organization_name=""):
    """Create a journey and derive its (empty) starting state."""
    if organization is None and organization_name:
        organization = match_organization_by_name(organization_name)

    with transaction.atomic():
        journey = Journey.objects.create(
            user=user,
            title=(title or "").strip()[:200] or "My journey",
            goal=(goal or "").strip(),
            primary_organization=organization,
        )
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
    breadcrumb.delete()
    state = recalculate_journey_state(journey)
    logger.info(
        "breadcrumb_deleted journey_id=%s breadcrumb_id=%s", journey.id, breadcrumb_id
    )
    return state


def save_draft_as_note(journey, raw_text, request_id=None):
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
    )
