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
from common.utils import format_day

from . import enums

_STATUS_SENTENCES = {
    enums.ReportedStatus.PROCESSING: "It was reported as still processing.",
    enums.ReportedStatus.UNDER_REVIEW: "It was reported as still under review.",
    enums.ReportedStatus.SUBMITTED: "It was reported as submitted.",
    enums.ReportedStatus.RECEIVED: "It was reported as received.",
    enums.ReportedStatus.INCOMPLETE: "It was reported as incomplete.",
    enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED: (
        "It was reported that more information is needed."
    ),
    enums.ReportedStatus.APPROVED: "It was reported as approved.",
    enums.ReportedStatus.REFUSED: "It was reported as refused.",
    enums.ReportedStatus.RESOLVED: "It was reported as resolved.",
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
            enums.Channel.PHONE: "by phone",
            enums.Channel.EMAIL: "by email",
            enums.Channel.IN_PERSON: "in person",
            enums.Channel.WEB: "online",
            enums.Channel.LETTER: "by letter",
            enums.Channel.UPLOAD: "by upload",
        }.get(breadcrumb.channel, "")

        descriptor = breadcrumb.title
        if org and org.lower() not in descriptor.lower():
            descriptor = "{desc} ({org})".format(desc=descriptor, org=org)
        if channel:
            descriptor = "{desc}, {channel}".format(desc=descriptor, channel=channel)

        line = "{when} - {what}".format(
            when=format_day(breadcrumb.occurred_at), what=descriptor
        )
        if breadcrumb.instruction:
            line += ". I was told: {instruction}".format(
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
        return "Is any additional action required from me, or should I keep waiting?"
    if state.status == enums.JourneyStatus.ACTION_REQUIRED:
        return "Can you confirm exactly what I need to provide, and how to send it?"
    if state.status == enums.JourneyStatus.COMPLETED:
        return "Is there anything further I need to do to close this?"
    return "What is the next step I should take?"


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
        or "No status has been recorded for this journey.",
        "latest_instruction": state.latest_instruction,
        "current_state": state.current_state,
        "current_question": _current_question(state),
        "references": list(state.references),
        "organization": (
            {
                "name": organization.name,
                "short_name": organization.short_name,
                "official_url": organization.official_url,
            }
            if organization is not None
            else None
        ),
        "generated_note": (
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
    lines = ["CASE SUMMARY", ""]
    lines.append("What I am trying to do:")
    lines.append(structured["goal"].rstrip(".") + ".")
    lines.append("")

    if structured["timeline"]:
        lines.append("What has happened so far:")
        for entry in structured["timeline"]:
            lines.append("- " + entry)
        lines.append("")

    lines.append("Last information I received:")
    lines.append(structured["latest_known_status"])
    if structured["latest_instruction"]:
        lines.append(
            "I was told: " + structured["latest_instruction"].rstrip(".") + "."
        )
    lines.append("")

    if structured["references"]:
        lines.append("Reference number(s): " + ", ".join(structured["references"]))
        lines.append("")

    lines.append("My question:")
    lines.append(structured["current_question"])

    if structured.get("organization"):
        lines.append("")
        lines.append(
            "Organization involved: " + structured["organization"]["name"]
        )

    lines.append("")
    lines.append("---")
    lines.append(structured["generated_note"])

    return "\n".join(lines)
