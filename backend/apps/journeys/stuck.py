"""
"I am stuck" (CLAUDE.md §20).

This is an action with a bounded answer, not a chat session. It returns the same
seven things every time: what happened, where you left off, what is unresolved,
the latest recorded instruction, who is responsible, official sources, and the
actions available to you.

Everything here is assembled deterministically from confirmed evidence. A model
may be asked afterwards to make the wording clearer, and that is the only thing it
is allowed to touch -- it cannot change a date, an organization, a status or an
instruction, because those are already fixed before it is called.
"""
from django.utils.translation import gettext as _

from common.utils import format_day

from . import enums
from .state import _describe_event  # noqa: F401  (shared phrasing helper)


def _summarize_history(journey, breadcrumbs, state):
    """Two or three sentences describing the journey so far, in recorded tense."""
    evidence = [b for b in breadcrumbs if b.counts_as_evidence]
    if not evidence:
        return _(
            "You have not recorded anything for this journey yet, so there is "
            "nothing to summarise."
        )

    ordered = sorted(evidence, key=lambda b: (b.occurred_at, b.created_at))
    first = ordered[0]
    last = ordered[-1]

    parts = [
        _("You are working on: {goal}").format(
            goal=(journey.goal or journey.title).rstrip(".") + "."
        )
    ]

    if len(ordered) == 1:
        parts.append(_describe_event(first))
    else:
        parts.append(
            _(
                "You started recording this on {start} and your most recent "
                "entry was on {end}, {count} events in total."
            ).format(
                start=format_day(first.occurred_at),
                end=format_day(last.occurred_at),
                count=len(ordered),
            )
        )
        parts.append(_describe_event(last))

    if state.latest_instruction:
        parts.append(
            _("The last instruction you recorded was: {instruction}").format(
                instruction=state.latest_instruction.rstrip(".") + "."
            )
        )

    return " ".join(parts)


def _suggested_actions(state, organization, sources):
    """
    What the citizen can actually do next, as product actions (§5, §15).

    Ordered by usefulness given the derived state, so a waiting journey does not
    lead with "call someone".
    """
    actions = []
    if sources:
        actions.append("OPEN_OFFICIAL_SOURCE")
    if state.status == enums.JourneyStatus.ACTION_REQUIRED:
        actions.insert(0, "ADD_BREADCRUMB")
    else:
        actions.append("ADD_BREADCRUMB")
    if organization is not None:
        actions.append("GET_RESPONSIBLE_ORGANIZATION")
    actions.append("GENERATE_HANDOFF")

    seen = set()
    return [a for a in actions if not (a in seen or seen.add(a))]


def build_stuck_summary(journey, breadcrumbs, state, organization_result, sources):
    """
    Assemble the complete "I am stuck" answer from confirmed data.

    Returns a dict matching the §20 response contract. The ``summary`` field is
    the only one a model may later reword.
    """
    organization = organization_result.get("responsible_organization")

    summary = _summarize_history(journey, breadcrumbs, state)

    unresolved = state.unresolved_issue
    if not unresolved and state.status == enums.JourneyStatus.COMPLETED:
        unresolved = _("Nothing appears unresolved based on what you have recorded.")

    return {
        "summary": summary,
        "current_state": state.current_state,
        "unresolved_issue": unresolved,
        "latest_instruction": state.latest_instruction,
        "next_action": state.next_action,
        "status": state.status,
        "responsible_organization": (
            {
                "id": str(organization.id),
                "name": organization.name,
                "short_name": organization.short_name,
                "jurisdiction": organization.jurisdiction,
                "official_url": organization.localized_official_url,
                "source": "CURATED_DIRECTORY",
                "basis": organization_result.get("basis"),
            }
            if organization is not None
            else None
        ),
        "organization_message": organization_result.get("message", ""),
        "official_sources": [
            {
                "id": str(source.id),
                "title": source.localized_title,
                "url": source.localized_url,
                "description": source.localized_description,
                "organization": source.organization.short_name
                or source.organization.name,
                "verified_at": source.verified_at,
                "source_type": enums.SourceType.OFFICIAL,
            }
            for source in sources
        ],
        "evidence": {
            "breadcrumb_id": state.evidence_breadcrumb_id,
            "source_type": state.evidence_source_type,
            "occurred_at": state.evidence_occurred_at,
            "summary": state.evidence_summary,
        },
        "suggested_actions": _suggested_actions(state, organization, sources),
    }
