"""
Controlled vocabularies for the Journey domain (CLAUDE.md §9).

These enums are the API contract. Note two deliberate decisions that differ from
the earlier draft spec in README.txt:

1. ``kind`` and ``channel`` are separate axes. "I emailed IRCC" is
   ``kind=INTERACTION, channel=EMAIL`` -- EMAIL is never a kind (§9.2).
2. There is no PERSON or OFFICIAL_SOURCE kind; a named person lives in
   structured_data, and an official source is kind=SOURCE with
   source_type=OFFICIAL.
"""
from django.db import models


class JourneyStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    WAITING = "WAITING", "Waiting"
    ACTION_REQUIRED = "ACTION_REQUIRED", "Action required"
    COMPLETED = "COMPLETED", "Completed"
    ARCHIVED = "ARCHIVED", "Archived"


class BreadcrumbKind(models.TextChoices):
    INTERACTION = "INTERACTION", "Interaction"
    ACTION = "ACTION", "Action"
    STATUS_UPDATE = "STATUS_UPDATE", "Status update"
    DOCUMENT = "DOCUMENT", "Document"
    NOTE = "NOTE", "Note"
    SOURCE = "SOURCE", "Source"


class Channel(models.TextChoices):
    PHONE = "PHONE", "Phone"
    EMAIL = "EMAIL", "Email"
    IN_PERSON = "IN_PERSON", "In person"
    WEB = "WEB", "Web"
    LETTER = "LETTER", "Letter"
    UPLOAD = "UPLOAD", "Upload"
    OTHER = "OTHER", "Other"
    UNKNOWN = "UNKNOWN", "Unknown"


class SourceType(models.TextChoices):
    """
    Provenance. The UI must distinguish these visibly, and never with colour
    alone (CLAUDE.md §4.1, README §16).

    AI_INTERPRETATION is deliberately excluded from state derivation: generated
    content describes evidence, it never becomes evidence (§14 Rule 2).
    """

    OFFICIAL = "OFFICIAL", "Official"
    USER_REPORTED = "USER_REPORTED", "User reported"
    COMMUNITY = "COMMUNITY", "Community"
    AI_INTERPRETATION = "AI_INTERPRETATION", "AI interpretation"


class GuideStepStatus(models.TextChoices):
    """Progress through suggested guidance, kept separate from case status."""

    NOT_STARTED = "NOT_STARTED", "Not started"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"


class ReportedStatus(models.TextChoices):
    """A status the citizen was *told*, not a status we independently verified."""

    SUBMITTED = "SUBMITTED", "Submitted"
    RECEIVED = "RECEIVED", "Received"
    PROCESSING = "PROCESSING", "Processing"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    INCOMPLETE = "INCOMPLETE", "Incomplete"
    ADDITIONAL_INFO_REQUIRED = "ADDITIONAL_INFO_REQUIRED", "Additional info required"
    APPROVED = "APPROVED", "Approved"
    REFUSED = "REFUSED", "Refused"
    RESOLVED = "RESOLVED", "Resolved"
    UNKNOWN = "UNKNOWN", "Unknown"


class NextActionCode(models.TextChoices):
    """What the citizen should do next, per the latest recorded evidence."""

    WAIT = "WAIT", "Wait"
    SUBMIT = "SUBMIT", "Submit something"
    UPLOAD = "UPLOAD", "Upload a document"
    CALL = "CALL", "Call the organization"
    VISIT = "VISIT", "Visit in person"
    PROVIDE_DOCUMENT = "PROVIDE_DOCUMENT", "Provide a document"
    CONTACT_ORGANIZATION = "CONTACT_ORGANIZATION", "Contact the organization"
    NONE = "NONE", "Nothing recorded"


#: Next actions that put the ball in the citizen's court (CLAUDE.md §18).
ACTION_REQUIRED_CODES = frozenset(
    {
        NextActionCode.SUBMIT,
        NextActionCode.UPLOAD,
        NextActionCode.CALL,
        NextActionCode.VISIT,
        NextActionCode.PROVIDE_DOCUMENT,
        NextActionCode.CONTACT_ORGANIZATION,
    }
)

#: Reported statuses that mean "nothing to do but wait".
WAITING_STATUSES = frozenset(
    {
        ReportedStatus.PROCESSING,
        ReportedStatus.UNDER_REVIEW,
        ReportedStatus.SUBMITTED,
        ReportedStatus.RECEIVED,
    }
)

#: Reported statuses that close a journey.
TERMINAL_STATUSES = frozenset(
    {
        ReportedStatus.APPROVED,
        ReportedStatus.REFUSED,
        ReportedStatus.RESOLVED,
    }
)


class Intent(models.TextChoices):
    """Supported intents for the out-of-scope gate (CLAUDE.md §15)."""

    CREATE_JOURNEY = "CREATE_JOURNEY", "Create journey"
    RECORD_EVENT = "RECORD_EVENT", "Record event"
    ASK_CURRENT_STATE = "ASK_CURRENT_STATE", "Ask current state"
    ASK_NEXT_ACTION = "ASK_NEXT_ACTION", "Ask next action"
    ASK_RESPONSIBLE_ORG = "ASK_RESPONSIBLE_ORG", "Ask responsible organization"
    GENERATE_HANDOFF = "GENERATE_HANDOFF", "Generate handoff"
    CORRECT_INFORMATION = "CORRECT_INFORMATION", "Correct information"
    OUT_OF_SCOPE = "OUT_OF_SCOPE", "Out of scope"


#: The bounded action set the product supports (CLAUDE.md §5).
SUPPORTED_ACTIONS = (
    "ADD_BREADCRUMB",
    "GET_CURRENT_STATE",
    "GET_RESPONSIBLE_ORGANIZATION",
    "GENERATE_HANDOFF",
)
