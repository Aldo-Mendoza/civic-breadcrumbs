"""
Closing the loop after a write.

Deterministic, zero AI calls. Compares two ``JourneyState`` snapshots taken
immediately either side of one mutation and produces one short sentence -- or a
calm unchanged acknowledgement when the correction didn't move the derived
answer. Because ``current_state``/``next_action`` are already a denormalized
cache recalculated from confirmed evidence (§9.1), "what changed" is just
describing that cache's diff; there is nothing new to compute.
"""
from dataclasses import dataclass

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from . import enums

#: Module-level dict: values must be lazy, or they would be translated once
#: at import time and never re-evaluate per request (see apps/journeys/state.py
#: for the same pattern and reasoning).
_STATUS_LABELS = {
    enums.JourneyStatus.ACTIVE: gettext_lazy("Active"),
    enums.JourneyStatus.WAITING: gettext_lazy("Waiting"),
    enums.JourneyStatus.ACTION_REQUIRED: gettext_lazy("Action needed"),
    enums.JourneyStatus.COMPLETED: gettext_lazy("Completed"),
    enums.JourneyStatus.ARCHIVED: gettext_lazy("Archived"),
}


@dataclass(frozen=True)
class StateChange:
    changed: bool
    status_changed: bool
    next_action_changed: bool
    message: str


def describe_change(before, after, verb, ack=gettext_lazy("Saved")):
    """
    Describe what a mutation actually did to the journey.

    ``before``/``after`` are ``JourneyState`` instances taken immediately
    either side of one create/correct/delete. ``verb`` names what the citizen
    just did, in past tense, for the "because you ___" clause (e.g. "recorded
    this", "corrected this", "deleted that", "saved that note"). ``ack`` is the
    short word used when nothing moved (e.g. "Saved", "Removed") -- an
    idempotent replay of the same request naturally lands here too, since
    before/after are identical when no real mutation occurred.
    """
    status_changed = before.status != after.status
    next_action_changed = before.next_action != after.next_action
    changed = status_changed or next_action_changed
    after_label = _STATUS_LABELS.get(after.status, after.status)

    if not changed:
        message = _("{ack}. Your status is still {label}.").format(
            ack=ack, label=after_label
        )
        return StateChange(False, False, False, message)

    if status_changed:
        before_label = _STATUS_LABELS.get(before.status, before.status)
        message = _(
            "Because you {verb}, your status moved from {before} to {after}."
        ).format(verb=verb, before=before_label, after=after_label)
    else:
        message = _(
            "Because you {verb}, the next recorded action changed to: {action}"
        ).format(verb=verb, action=after.next_action)
    return StateChange(True, status_changed, next_action_changed, message)
