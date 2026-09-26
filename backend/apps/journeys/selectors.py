"""
Read paths for the Journey domain.

Two responsibilities worth calling out:

* **Ownership.** Every lookup goes through a selector that scopes on the
  requesting user and raises 404 -- not 403 -- when the object belongs to someone
  else. A 403 confirms that an id exists, which lets an attacker enumerate
  journeys; a 404 tells them nothing (§29, IDOR).
* **Context minimization.** ``build_minimal_context`` and ``build_ai_snapshot``
  are the only things ever sent to a model. They carry the journey goal, the
  current state and a handful of confirmed events -- never the full record, never
  UI state, never previously generated prose (§17). Less data leaves the
  citizen's device than the feature would otherwise need, which is the point.
"""
from django.http import Http404

from .models import Breadcrumb, Journey


def list_journeys(user):
    return (
        Journey.objects.filter(user=user)
        .select_related("primary_organization")
        .prefetch_related("breadcrumbs")
    )


def get_owned_journey(user, journey_id):
    """Fetch a journey the user owns, or raise 404."""
    try:
        return (
            Journey.objects.select_related("primary_organization")
            .prefetch_related("breadcrumbs__organization")
            .get(pk=journey_id, user=user)
        )
    except (Journey.DoesNotExist, ValueError, TypeError):
        raise Http404("Journey not found.")


def get_owned_breadcrumb(user, breadcrumb_id):
    """Fetch a breadcrumb on a journey the user owns, or raise 404."""
    try:
        return Breadcrumb.objects.select_related("journey", "organization").get(
            pk=breadcrumb_id, journey__user=user
        )
    except (Breadcrumb.DoesNotExist, ValueError, TypeError):
        raise Http404("Breadcrumb not found.")


def get_breadcrumbs(journey, confirmed_only=False):
    queryset = journey.breadcrumbs.select_related("organization").order_by(
        "occurred_at", "created_at"
    )
    if confirmed_only:
        queryset = queryset.filter(is_confirmed=True)
    return queryset


def evidence_breadcrumbs(journey):
    """
    Confirmed, non-AI breadcrumbs -- the only valid input to state derivation.

    The AI_INTERPRETATION exclusion lives here as well as on the model property
    so that the database query itself cannot return generated content as
    evidence (§14 Rule 2).
    """
    from . import enums

    return (
        journey.breadcrumbs.select_related("organization")
        .filter(is_confirmed=True)
        .exclude(source_type=enums.SourceType.AI_INTERPRETATION)
        .order_by("occurred_at", "created_at")
    )


def build_timeline(breadcrumbs):
    """Structured timeline rows. Presentation is left to the client (§43)."""
    return [
        {
            "id": str(breadcrumb.id),
            "kind": breadcrumb.kind,
            "channel": breadcrumb.channel,
            "title": breadcrumb.title,
            "organization_name": breadcrumb.organization_name,
            "organization_display": breadcrumb.organization_display,
            "occurred_at": breadcrumb.occurred_at,
            "source_type": breadcrumb.source_type,
            "reported_status": breadcrumb.reported_status,
            "instruction": breadcrumb.instruction,
            "is_confirmed": breadcrumb.is_confirmed,
            "counts_as_evidence": breadcrumb.counts_as_evidence,
        }
        for breadcrumb in breadcrumbs
    ]


def build_minimal_context(journey, state=None, today=None):
    """
    The smallest context that lets a model read one event correctly (§17).

    Deliberately excluded: the breadcrumb history, previously generated prose,
    anything about the interface. Included: the goal, the current derived state,
    and the curated organization allow-list so the extractor cannot name an
    institution we have not verified.
    """
    from apps.directory.selectors import known_organizations

    context = {
        "journey_title": journey.title,
        "journey_goal": journey.goal,
        "known_organizations": known_organizations(),
    }
    if state is not None:
        context["current_state"] = state.current_state
    if journey.primary_organization_id:
        context["journey_organization"] = journey.primary_organization.name
    if today is not None:
        context["today"] = today.isoformat()
    return context


def build_ai_snapshot(journey, state, breadcrumbs, summary, max_events=8):
    """
    A compact snapshot for the optional prose pass (§17).

    ``summary`` is already the complete factual answer; the snapshot exists so a
    model can improve its wording, not supply its content.
    """
    recent = list(breadcrumbs)[-max_events:]
    return {
        "goal": journey.goal,
        "current_state": state.current_state,
        "summary": summary,
        "confirmed_events": [
            {
                "date": b.occurred_at.date().isoformat(),
                "type": b.kind,
                "organization": b.organization_name,
                "summary": b.title,
                "reported_status": b.reported_status,
                "instruction": b.instruction,
            }
            for b in recent
        ],
    }
