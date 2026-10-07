"""
Current-state derivation (CLAUDE.md §18).

``derive_journey_state`` is a pure function: it touches no database, calls no
model, and reads no hidden conversation context. Given a journey and a list of
breadcrumbs it returns the same answer every time. That property is what makes
the "you left off here" feature trustworthy and trivially testable.

Two rules are enforced structurally rather than by convention:

* Only breadcrumbs where ``counts_as_evidence`` is true may inform state, so
  AI-generated content can never feed back into the journey (§14 Rule 2).
* Tense is constrained. We say "your last recorded interaction reported X",
  never "your application is X". The system has no authoritative live data and
  must not imply that it does (§18). This is a correctness requirement, not copy
  polish: the difference between reporting evidence and asserting fact is the
  difference between a trustworthy civic tool and one that misleads someone
  about their immigration status.
"""
import re
from dataclasses import dataclass, field, replace

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from common.utils import format_day

from . import enums

#: Phrases indicating the citizen was told to wait, used when an explicit
#: next-action code is absent. This is substring-matched against recorded
#: instruction text (possibly AI-generated, possibly French per Phase B), so
#: both languages' phrases are included unconditionally rather than gated by
#: the active locale -- a French phrase will not spuriously match English
#: text or vice versa, so being inclusive here is only ever safer.
_WAIT_PHRASES = (
    "wait",
    "waiting",
    "do not submit another",
    "not submit another",
    "no action",
    "nothing further",
    "no further action",
    "attendre",
    "attendez",
    "attente",
    "ne pas soumettre",
    "ne soumettez pas",
    "aucune action",
    "rien d'autre",
    "aucune autre action",
)

#: Module-level dict: values must be lazy, or they would be translated once
#: at import time (using whatever locale happens to be active at server
#: startup) and never re-evaluate per request.
_CHANNEL_PHRASES = {
    enums.Channel.PHONE: gettext_lazy("a phone call"),
    enums.Channel.EMAIL: gettext_lazy("an email"),
    enums.Channel.IN_PERSON: gettext_lazy("an in-person visit"),
    enums.Channel.WEB: gettext_lazy("a website"),
    enums.Channel.LETTER: gettext_lazy("a letter"),
    enums.Channel.UPLOAD: gettext_lazy("an upload"),
}

_STATUS_LABELS = {
    enums.ReportedStatus.SUBMITTED: gettext_lazy("submitted"),
    enums.ReportedStatus.RECEIVED: gettext_lazy("received"),
    enums.ReportedStatus.PROCESSING: gettext_lazy("still processing"),
    enums.ReportedStatus.UNDER_REVIEW: gettext_lazy("still under review"),
    enums.ReportedStatus.INCOMPLETE: gettext_lazy("incomplete"),
    enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED: gettext_lazy("needing more information"),
    enums.ReportedStatus.APPROVED: gettext_lazy("approved"),
    enums.ReportedStatus.REFUSED: gettext_lazy("refused"),
    enums.ReportedStatus.RESOLVED: gettext_lazy("resolved"),
    enums.ReportedStatus.UNKNOWN: gettext_lazy("unclear"),
}


@dataclass(frozen=True)
class JourneyState:
    """The derived answer to the question "where am I?"."""

    status: str
    current_state: str
    next_action: str
    next_action_code: str
    unresolved_issue: str
    latest_reported_status: str = enums.ReportedStatus.UNKNOWN
    latest_instruction: str = ""
    #: Provenance, so the UI can always cite which breadcrumb produced this.
    evidence_breadcrumb_id: object = None
    evidence_source_type: object = None
    evidence_occurred_at: object = None
    evidence_summary: str = ""
    evidence_organization: str = ""
    considered_count: int = 0
    references: tuple = field(default_factory=tuple)

    def as_dict(self):
        return {
            "status": self.status,
            "current_state": self.current_state,
            "next_action": self.next_action,
            "next_action_code": self.next_action_code,
            "unresolved_issue": self.unresolved_issue,
            "latest_reported_status": self.latest_reported_status,
            "latest_instruction": self.latest_instruction,
        }


def _sort_key(breadcrumb):
    """Newest-last ordering key. Falls back to occurred_at for unsaved rows."""
    return (breadcrumb.occurred_at, breadcrumb.created_at or breadcrumb.occurred_at)


def _organization_of(breadcrumb):
    """The name to show the citizen. See Breadcrumb.organization_display."""
    return breadcrumb.organization_display


def _implies_waiting(text):
    lowered = (text or "").lower()
    return any(re.search(r"\b" + re.escape(phrase) + r"\b", lowered) for phrase in _WAIT_PHRASES)


def _latest_where(ordered, predicate):
    """First match in a newest-first list."""
    for breadcrumb in ordered:
        if predicate(breadcrumb):
            return breadcrumb
    return None


def _has_status(breadcrumb):
    return breadcrumb.reported_status not in (
        "",
        None,
        enums.ReportedStatus.UNKNOWN,
    )


def _has_next_action(breadcrumb):
    return breadcrumb.suggested_next_action not in (
        "",
        None,
        enums.NextActionCode.NONE,
    )


def _describe_event(breadcrumb):
    """One human sentence for a single breadcrumb, in recorded-past tense."""
    org = _organization_of(breadcrumb)
    when = format_day(breadcrumb.occurred_at)
    channel_phrase = _CHANNEL_PHRASES.get(breadcrumb.channel)

    if breadcrumb.kind == enums.BreadcrumbKind.INTERACTION and org:
        if channel_phrase:
            return _("On {when} you recorded {how} with {org}.").format(
                when=when, how=channel_phrase, org=org
            )
        return _("On {when} you recorded contact with {org}.").format(when=when, org=org)
    return _("On {when} you recorded: {title}").format(when=when, title=breadcrumb.title)


def _next_action_sentence(code, instruction, organization):
    """
    Phrase the next step.

    Where the citizen was given an explicit instruction we repeat theirs rather
    than inventing our own. The product does not give advice (§4.2); it reports
    what was recorded.
    """
    if instruction:
        prefix = {
            enums.NextActionCode.WAIT: _("Wait, as you were told: "),
            enums.NextActionCode.UPLOAD: _("Provide what was asked for: "),
            enums.NextActionCode.SUBMIT: _("Submit what was asked for: "),
            enums.NextActionCode.PROVIDE_DOCUMENT: _("Provide the document requested: "),
            enums.NextActionCode.CALL: _("Follow up by phone: "),
            enums.NextActionCode.VISIT: _("Attend in person: "),
            enums.NextActionCode.CONTACT_ORGANIZATION: _("Follow up: "),
        }.get(code)
        if prefix:
            return prefix + instruction.rstrip(".") + "."

    if code == enums.NextActionCode.CONTACT_ORGANIZATION:
        if organization:
            return _("Contact {org} about the next step.").format(org=organization)
        return _("Contact the responsible organization about the next step.")

    plain = {
        enums.NextActionCode.WAIT: _(
            "Wait for an update unless your circumstances change."
        ),
        enums.NextActionCode.UPLOAD: _("Upload the document that was requested."),
        enums.NextActionCode.SUBMIT: _("Submit what was requested."),
        enums.NextActionCode.PROVIDE_DOCUMENT: _("Provide the document requested."),
        enums.NextActionCode.CALL: _("Call the organization for an update."),
        enums.NextActionCode.VISIT: _("Attend the office in person."),
    }.get(code)
    return plain or _("No next action has been recorded yet.")


def _empty_state():
    return JourneyState(
        status=enums.JourneyStatus.ACTIVE,
        current_state=_("Nothing has been recorded for this journey yet."),
        next_action=_(
            "Record what has happened so far, so you do not have to remember "
            "it yourself."
        ),
        next_action_code=enums.NextActionCode.NONE,
        unresolved_issue=_("No events have been recorded yet."),
        considered_count=0,
    )


# ---------------------------------------------------------------------------
# Staleness -- a proactive nudge, deliberately separate from state derivation.
#
# `derive_journey_state` answers "what is true"; this answers "how stale is
# our knowledge of it" -- a different question with a different reason to
# change, so it gets its own pure function rather than a clock parameter
# threaded through the state function above (which would touch every existing
# call site and test for no real benefit).
#
# The wording constraint here matters as much as the logic: this can only ever
# describe the citizen's own recording gap. It must never imply a government
# processing-time expectation (CLAUDE.md §4.2 -- do not invent eligibility,
# deadlines, or processing facts). "You haven't told us anything in 9 days" is
# fine; "IRCC normally takes 2 weeks" is not, and this function has no access
# to any such claim to begin with.
# ---------------------------------------------------------------------------

#: Days of silence before a nudge appears, tuned per status: shorter for
#: ACTION_REQUIRED (something is outstanding on the citizen's side, so a lull
#: is worth surfacing quickly), longest for WAITING (the citizen is expecting
#: someone else to act, and a frequent nudge there would just feel like
#: nagging). COMPLETED/ARCHIVED are absent on purpose -- a closed journey is
#: never stale.
STALE_AFTER_DAYS = {
    enums.JourneyStatus.ACTION_REQUIRED: 3,
    enums.JourneyStatus.WAITING: 10,
    enums.JourneyStatus.ACTIVE: 7,
}


@dataclass(frozen=True)
class Staleness:
    """Whether, and how, to nudge the citizen about a recording gap."""

    is_stale: bool
    days_since_last_recorded: int | None
    last_recorded_at: object | None
    message: str


def compute_staleness(status, breadcrumbs, now):
    """
    Zero-AI. Reports only the citizen's own recording gap.

    Uses ``created_at`` (when the citizen actually told the system something),
    not ``occurred_at`` (the date they say the event happened) -- backdating
    old history today correctly reads as "just recorded something," not as
    stale, and recording something about a long-past or future event is
    neither penalized nor rewarded either way.
    """
    threshold = STALE_AFTER_DAYS.get(status)
    evidence = [b for b in (breadcrumbs or []) if b.counts_as_evidence]
    if threshold is None or not evidence:
        return Staleness(False, None, None, "")

    last_recorded_at = max(b.created_at for b in evidence)
    days = (now - last_recorded_at).days
    if days < threshold:
        return Staleness(False, days, last_recorded_at, "")

    if status == enums.JourneyStatus.ACTION_REQUIRED:
        message = _(
            "You haven't recorded anything new in {days} days, and "
            "something was still outstanding at your last update. If "
            "anything has happened since, record it so this stays "
            "accurate."
        ).format(days=days)
    else:
        message = _(
            "You haven't recorded anything new in {days} days. If "
            "anything has happened since, record it so this stays "
            "accurate."
        ).format(days=days)
    return Staleness(True, days, last_recorded_at, message)


def derive_journey_state(journey, breadcrumbs):
    """Keep explicit archival status while deriving facts from evidence."""
    state = _derive_evidence_state(journey, breadcrumbs)
    if journey.status == enums.JourneyStatus.ARCHIVED:
        return replace(state, status=enums.JourneyStatus.ARCHIVED)
    return state


def _derive_evidence_state(journey, breadcrumbs):
    """
    Derive the current known state of a journey from confirmed evidence.

    ``breadcrumbs`` may arrive in any order and may include drafts or
    AI-generated entries; both are filtered out here rather than at the call
    site, so no caller can accidentally bypass the rule.
    """
    evidence = [b for b in breadcrumbs if b.counts_as_evidence]
    if not evidence:
        return _empty_state()

    ordered = sorted(evidence, key=_sort_key, reverse=True)
    latest = ordered[0]

    status_evidence = _latest_where(ordered, _has_status)
    instruction_evidence = _latest_where(ordered, lambda b: bool(b.instruction))
    action_evidence = _latest_where(ordered, _has_next_action)

    reported_status = (
        status_evidence.reported_status
        if status_evidence
        else enums.ReportedStatus.UNKNOWN
    )
    instruction = instruction_evidence.instruction if instruction_evidence else ""
    # Historical instructions remain available for handoffs, but must not be
    # presented as current after a newer status or explicit action replaces them.
    current_instruction = instruction
    if instruction_evidence is not None and any(
        anchor is not None and _sort_key(anchor) > _sort_key(instruction_evidence)
        for anchor in (status_evidence, action_evidence)
    ):
        current_instruction = ""
    organization = _organization_of(status_evidence or latest)
    references = tuple(sorted({b.reference for b in ordered if b.reference}))

    common = {
        "latest_reported_status": reported_status,
        "latest_instruction": instruction,
        "evidence_organization": organization,
        "considered_count": len(evidence),
        "references": references,
    }

    def with_evidence(anchor, **kwargs):
        return JourneyState(
            evidence_breadcrumb_id=str(anchor.id),
            evidence_source_type=anchor.source_type,
            evidence_occurred_at=anchor.occurred_at,
            evidence_summary=_describe_event(anchor),
            **common,
            **kwargs,
        )

    # --- Rule 1: a closed outcome ends the journey --------------------------
    # Note we do not advise on a refusal: an appeal is a legal question and
    # outside what this product may answer (§4.2).
    if reported_status in enums.TERMINAL_STATUSES:
        return with_evidence(
            status_evidence,
            status=enums.JourneyStatus.COMPLETED,
            current_state=_(
                "Your last recorded update, on {when}, reported the outcome as "
                "{outcome}."
            ).format(
                when=format_day(status_evidence.occurred_at),
                outcome=_STATUS_LABELS.get(reported_status, _("recorded")),
            ),
            next_action=_("No further action has been recorded."),
            next_action_code=enums.NextActionCode.NONE,
            unresolved_issue="",
        )

    # --- Rule 2: an outstanding action the citizen must take ----------------
    # Live only if nothing newer reports a status, i.e. it has not been
    # superseded by a later interaction.
    action_is_current = action_evidence is not None and (
        action_evidence.suggested_next_action in enums.ACTION_REQUIRED_CODES
    )
    if action_is_current and status_evidence is not None:
        action_is_current = _sort_key(action_evidence) >= _sort_key(status_evidence)

    if action_is_current:
        return with_evidence(
            action_evidence,
            status=enums.JourneyStatus.ACTION_REQUIRED,
            current_state=_(
                "Your last recorded update, on {when}, indicated that something "
                "is needed from you."
            ).format(when=format_day(action_evidence.occurred_at)),
            next_action=_next_action_sentence(
                action_evidence.suggested_next_action,
                action_evidence.instruction,
                organization,
            ),
            next_action_code=action_evidence.suggested_next_action,
            unresolved_issue=_("A recorded instruction is still outstanding."),
        )

    # --- Rule 3: waiting ----------------------------------------------------
    waiting_by_status = reported_status in enums.WAITING_STATUSES
    waiting_by_instruction = _implies_waiting(current_instruction)
    waiting_by_code = (
        action_evidence is not None
        and action_evidence.suggested_next_action == enums.NextActionCode.WAIT
        and (status_evidence is None or _sort_key(action_evidence) >= _sort_key(status_evidence))
    )

    if waiting_by_status or waiting_by_instruction or waiting_by_code:
        anchor = status_evidence or instruction_evidence or latest
        label = (
            _STATUS_LABELS.get(reported_status, _("still in progress"))
            if waiting_by_status
            else _("still in progress")
        )
        with_org = _(" with {org}").format(org=organization) if organization else ""
        return with_evidence(
            anchor,
            status=enums.JourneyStatus.WAITING,
            current_state=_(
                "Your last recorded interaction{with_org}, on {when}, reported "
                "the matter as {label}."
            ).format(
                with_org=with_org,
                when=format_day(anchor.occurred_at),
                label=label,
            ),
            next_action=_next_action_sentence(
                enums.NextActionCode.WAIT, current_instruction, organization
            ),
            next_action_code=enums.NextActionCode.WAIT,
            unresolved_issue=_(
                "No newer status has been recorded since {when}."
            ).format(when=format_day(anchor.occurred_at)),
        )

    # --- Rule 4: recorded activity that implies no particular state ---------
    return with_evidence(
        latest,
        status=enums.JourneyStatus.ACTIVE,
        current_state=_(
            "Your most recent recorded event was on {when}: {title}"
        ).format(when=format_day(latest.occurred_at), title=latest.title),
        next_action=_(
            "No next action has been recorded. If an organization has told you "
            "something, record it so this stays up to date."
        ),
        next_action_code=enums.NextActionCode.NONE,
        unresolved_issue=_("No status has been recorded for this journey yet."),
    )
