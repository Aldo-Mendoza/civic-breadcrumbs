"""
Handoff summary (CLAUDE.md §22).

The point of the whole product, compressed into one screen: the citizen hands
someone a short, accurate account of their case instead of reconstructing it from
memory for the fourth time.

Two design rules:

* Built from confirmed evidence only. A handoff that included a guess would be
  worse than no handoff, because the person receiving it would act on it.
* Never persisted. A generated summary describes evidence; it is not evidence
  (§14 Rule 2). Storing it would create a record that could later be mistaken
  for something the citizen was actually told, so the endpoint returns it and
  keeps nothing (§33 Case G).
"""
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from common.utils import format_day

from . import enums

#: Module-level dict: values must be lazy so they translate per request
#: rather than being frozen at import time (see apps/journeys/state.py).
_STATUS_SENTENCES = {
    enums.ReportedStatus.PROCESSING: gettext_lazy("It was reported as still processing."),
    enums.ReportedStatus.UNDER_REVIEW: gettext_lazy("It was reported as still under review."),
    enums.ReportedStatus.SUBMITTED: gettext_lazy("It was reported as submitted."),
    enums.ReportedStatus.RECEIVED: gettext_lazy("It was reported as received."),
    enums.ReportedStatus.INCOMPLETE: gettext_lazy("It was reported as incomplete."),
    enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED: gettext_lazy(
        "It was reported that more information is needed."
    ),
    enums.ReportedStatus.APPROVED: gettext_lazy("It was reported as approved."),
    enums.ReportedStatus.REFUSED: gettext_lazy("It was reported as refused."),
    enums.ReportedStatus.RESOLVED: gettext_lazy("It was reported as resolved."),
}


def _timeline_lines(breadcrumbs):
    """One line per confirmed event, oldest first, with the channel made plain."""
    lines = []
    for breadcrumb in sorted(
        (b for b in breadcrumbs if b.counts_as_evidence),
        key=lambda b: (b.occurred_at, b.created_at),
    ):
        org = breadcrumb.organization_display
        channel = {
            enums.Channel.PHONE: _("by phone"),
            enums.Channel.EMAIL: _("by email"),
            enums.Channel.IN_PERSON: _("in person"),
            enums.Channel.WEB: _("online"),
            enums.Channel.LETTER: _("by letter"),
            enums.Channel.UPLOAD: _("by upload"),
        }.get(breadcrumb.channel, "")

        descriptor = breadcrumb.title
        if org and org.lower() not in descriptor.lower():
            descriptor = _("{desc} ({org})").format(desc=descriptor, org=org)
        if channel:
            descriptor = _("{desc}, {channel}").format(desc=descriptor, channel=channel)

        line = _("{when} - {what}").format(
            when=format_day(breadcrumb.occurred_at), what=descriptor
        )
        if breadcrumb.instruction:
            line += _(". I was told: {instruction}").format(
                instruction=breadcrumb.instruction.rstrip(".")
            )
        lines.append(line)
    return lines


def _current_question(state):
    """
    The question the citizen is actually asking, phrased for the recipient.

    Derived from state rather than free text, so the handoff always ends with
    something answerable.
    """
    if state.status == enums.JourneyStatus.WAITING:
        return _("Is any additional action required from me, or should I keep waiting?")
    if state.status == enums.JourneyStatus.ACTION_REQUIRED:
        return _("Can you confirm exactly what I need to provide, and how to send it?")
    if state.status == enums.JourneyStatus.COMPLETED:
        return _("Is there anything further I need to do to close this?")
    return _("What is the next step I should take?")


def build_handoff(journey, breadcrumbs, state, organization=None):
    """
    Assemble the handoff, both as structured data and as copyable text.

    The structured form lets the frontend render or partially share it later; the
    rendered text is what the MVP puts behind COPY SUMMARY (§22).
    """
    timeline = _timeline_lines(breadcrumbs)
    status_sentence = _STATUS_SENTENCES.get(state.latest_reported_status, "")

    structured = {
        "goal": journey.goal or journey.title,
        "title": journey.title,
        "timeline": timeline,
        "latest_known_status": status_sentence
        or _("No status has been recorded for this journey."),
        "latest_instruction": state.latest_instruction,
        "current_state": state.current_state,
        "current_question": _current_question(state),
        "references": list(state.references),
        "organization": (
            {
                "name": organization.name,
                "short_name": organization.short_name,
                "official_url": organization.localized_official_url,
            }
            if organization is not None
            else None
        ),
        "generated_note": _(
            "Prepared from records kept by the person named above. This is a "
            "personal record, not an official government document."
        ),
    }
    structured["summary"] = render_handoff_text(structured)
    return structured


def render_handoff_text(structured):
    """
    Render the copyable case summary.

    Plain text on purpose: it has to paste cleanly into an email, a web form, a
    chat window, or be read aloud over the phone. The closing disclaimer is not
    boilerplate -- it stops a caseworker mistaking a citizen's own notes for an
    official case record (§4.2).
    """
    lines = [_("CASE SUMMARY"), ""]
    lines.append(_("What I am trying to do:"))
    lines.append(structured["goal"].rstrip(".") + ".")
    lines.append("")

    if structured["timeline"]:
        lines.append(_("What has happened so far:"))
        for entry in structured["timeline"]:
            lines.append("- " + entry)
        lines.append("")

    lines.append(_("Last information I received:"))
    lines.append(structured["latest_known_status"])
    if structured["latest_instruction"]:
        lines.append(
            _("I was told: ") + structured["latest_instruction"].rstrip(".") + "."
        )
    lines.append("")

    if structured["references"]:
        lines.append(_("Reference number(s): ") + ", ".join(structured["references"]))
        lines.append("")

    lines.append(_("My question:"))
    lines.append(structured["current_question"])

    if structured.get("organization"):
        lines.append("")
        lines.append(
            _("Organization involved: ") + structured["organization"]["name"]
        )

    lines.append("")
    lines.append("---")
    lines.append(structured["generated_note"])

    # str() every line: a couple of fields (e.g. latest_known_status) may still
    # be an unevaluated gettext_lazy proxy from a module-level lookup table
    # (_STATUS_SENTENCES) -- str.join() requires real str instances.
    return "\n".join(str(line) for line in lines)
