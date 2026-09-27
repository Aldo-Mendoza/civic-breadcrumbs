"""
Structured AI contracts (CLAUDE.md §13).

Model output is never trusted as-is. Everything crossing the AI boundary is
validated here: enum membership, date format, string length caps, confidence
range. Anything that fails validation is rejected rather than persisted, and the
citizen is offered "save as note" instead (§13, §28).

These schemas are also what the deterministic rule-based extractor produces, so
both implementations are held to exactly the same contract.
"""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.journeys import enums

MAX_TITLE = 300
MAX_INSTRUCTION = 500
MAX_ORGANIZATION = 200
MAX_REFERENCE = 64
MAX_GOAL = 1000
MAX_SUMMARY = 4000
MAX_PARAPHRASE = 220
MAX_GUIDE_STEP_DESCRIPTION = 700


def _choices(enum_cls):
    return {value for value, _ in enum_cls.choices}


def clarification_for(organization, status, instruction, channel):
    """
    One focused question, at most (§14 Rule 4).

    Shared by every extractor -- the rule-based engine calls this directly, and
    ``BreadcrumbDraft``'s own validator falls back to it for any extractor
    (Gemini included) that sets ``needs_clarification`` without supplying a
    question. We ask about the single most load-bearing missing fact rather
    than interviewing the citizen.
    """
    if not organization:
        return "Which organization was this with?"
    if not status and not instruction:
        return (
            "What did they tell you? For example, that it is still being "
            "processed, or that they need something from you."
        )
    if channel == enums.Channel.UNKNOWN:
        return "Was this a phone call, an email, or an in-person visit?"
    return "Was this something they told you directly, or something you read online?"


class BreadcrumbDraft(BaseModel):
    """A proposed interpretation of something the citizen described.

    A draft is never evidence. It becomes evidence only when the citizen
    confirms it through a separate request (§24).
    """

    model_config = ConfigDict(extra="ignore")

    kind: str = enums.BreadcrumbKind.NOTE
    channel: str = enums.Channel.UNKNOWN
    title: str = ""
    organization: str = ""
    occurred_on: date | None = None
    reported_status: str = enums.ReportedStatus.UNKNOWN
    instruction: str = ""
    suggested_next_action: str = enums.NextActionCode.NONE
    reference: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_question: str | None = None
    #: One plain-English sentence confirming what was understood, e.g. "Got it
    #: — you called IRCC and they said your application is still processing."
    #: Shown to the citizen immediately, before any correction form -- this is
    #: what lets a one-tap confirm feel safe instead of blind (§20 in spirit:
    #: never a substitute for the structured fields, just a human-readable
    #: mirror of them). Must never introduce a fact absent from the other
    #: fields (enforced by the prompt for Gemini; structurally true for the
    #: rule-based builder, which can only restate values it already computed).
    paraphrase: str = ""
    #: Which implementation produced this: "rules" or "gemini".
    extractor: str = "rules"

    # -- enum guards --------------------------------------------------------

    @field_validator("kind")
    @classmethod
    def _valid_kind(cls, value):
        return value if value in _choices(enums.BreadcrumbKind) else enums.BreadcrumbKind.NOTE

    @field_validator("channel")
    @classmethod
    def _valid_channel(cls, value):
        return value if value in _choices(enums.Channel) else enums.Channel.UNKNOWN

    @field_validator("reported_status")
    @classmethod
    def _valid_status(cls, value):
        if value in _choices(enums.ReportedStatus):
            return value
        return enums.ReportedStatus.UNKNOWN

    @field_validator("suggested_next_action")
    @classmethod
    def _valid_next_action(cls, value):
        if value in _choices(enums.NextActionCode):
            return value
        return enums.NextActionCode.NONE

    # -- length caps --------------------------------------------------------

    @field_validator("title")
    @classmethod
    def _cap_title(cls, value):
        return (value or "").strip()[:MAX_TITLE]

    @field_validator("organization")
    @classmethod
    def _cap_org(cls, value):
        return (value or "").strip()[:MAX_ORGANIZATION]

    @field_validator("instruction")
    @classmethod
    def _cap_instruction(cls, value):
        return (value or "").strip()[:MAX_INSTRUCTION]

    @field_validator("reference")
    @classmethod
    def _cap_reference(cls, value):
        return (value or "").strip()[:MAX_REFERENCE]

    @field_validator("clarification_question")
    @classmethod
    def _cap_question(cls, value):
        if not value:
            return None
        return value.strip()[:MAX_INSTRUCTION]

    @field_validator("paraphrase")
    @classmethod
    def _cap_paraphrase(cls, value):
        return (value or "").strip()[:MAX_PARAPHRASE]

    # -- cross-field invariants, enforced regardless of which extractor
    # produced this draft (§33 Case C) ---------------------------------------

    @model_validator(mode="after")
    def _enforce_unconfirmed_counterparty_needs_clarification(self):
        """
        "They said I need another thing" is not a record until we know who
        "they" were -- this must hold no matter which extractor produced the
        draft. Live evaluation (``manage.py eval_gemini``) found that Gemini's
        own ``needs_clarification`` judgment does not reliably reflect this:
        it can say False with an empty organization on an INTERACTION, which
        would let an unconfirmed counterparty through unquestioned. The
        rule-based engine already enforced this case by case; this makes it a
        property of the contract itself, so no extractor can bypass it.
        """
        if self.kind == enums.BreadcrumbKind.INTERACTION and not self.organization:
            self.needs_clarification = True
        return self

    @model_validator(mode="after")
    def _fill_missing_clarification_question(self):
        """
        A second gap the same evaluation found: Gemini can set
        ``needs_clarification=True`` while leaving ``clarification_question``
        empty -- a dead end for the citizen, who would be told something needs
        clarifying with nothing to answer. Falling back to the same
        deterministic question bank the rule-based engine uses keeps this
        honest without a second AI call.
        """
        if self.needs_clarification and not self.clarification_question:
            self.clarification_question = clarification_for(
                self.organization, self.reported_status, self.instruction, self.channel
            )
        return self


class GuideStepDraft(BaseModel):
    """One bounded suggestion in a plan; never proof the citizen did it."""

    model_config = ConfigDict(extra="ignore")

    title: str = ""
    description: str = ""
    #: A short (2-4 word) phrase naming what this step is about, e.g.
    #: "required documents" or "submission channel" -- used only to find a
    #: relevant curated official link for *this* step, never to assert a new
    #: fact. Optional; an empty topic just means no link gets attached.
    topic: str = ""

    @field_validator("title")
    @classmethod
    def _cap_title(cls, value):
        return (value or "").strip()[:200]

    @field_validator("description")
    @classmethod
    def _cap_description(cls, value):
        return (value or "").strip()[:MAX_GUIDE_STEP_DESCRIPTION]

    @field_validator("topic")
    @classmethod
    def _cap_topic(cls, value):
        return (value or "").strip()[:60]


class JourneyDraft(BaseModel):
    """A proposed journey, derived from how the citizen described their goal."""

    model_config = ConfigDict(extra="ignore")

    title: str = ""
    goal: str = ""
    organization: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extractor: str = "rules"
    guide_summary: str = ""
    guide_steps: list[GuideStepDraft] = Field(min_length=3, max_length=6)
    needs_clarification: bool = False
    clarification_question: str = ""

    @field_validator("title")
    @classmethod
    def _cap_title(cls, value):
        return (value or "").strip()[:200]

    @field_validator("goal")
    @classmethod
    def _cap_goal(cls, value):
        return (value or "").strip()[:MAX_GOAL]

    @field_validator("organization")
    @classmethod
    def _cap_org(cls, value):
        return (value or "").strip()[:MAX_ORGANIZATION]

    @field_validator("guide_summary")
    @classmethod
    def _cap_guide_summary(cls, value):
        return (value or "").strip()[:MAX_GOAL]

    @field_validator("clarification_question")
    @classmethod
    def _cap_clarification(cls, value):
        return (value or "").strip()[:300]

    @model_validator(mode="after")
    def _safe_guide_shape(self):
        self.guide_steps = [step for step in self.guide_steps if step.title][:6]
        return self


class ProseSummary(BaseModel):
    """
    Prose only.

    Used for the optional wording pass over "I am stuck" and handoff output. The
    model may rewrite the sentence; it can never supply a fact, a date, an
    organization or an instruction, because those fields are built
    deterministically before this is ever called (§20, §22).
    """

    model_config = ConfigDict(extra="ignore")

    summary: str = ""
    extractor: str = "rules"

    @field_validator("summary")
    @classmethod
    def _cap_summary(cls, value):
        return (value or "").strip()[:MAX_SUMMARY]


#: JSON schema handed to Gemini for constrained decoding. Kept in sync with
#: BreadcrumbDraft by the contract tests.
BREADCRUMB_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": sorted(_choices(enums.BreadcrumbKind))},
        "channel": {"type": "string", "enum": sorted(_choices(enums.Channel))},
        "title": {"type": "string"},
        "organization": {"type": "string"},
        "occurred_on": {"type": "string"},
        "reported_status": {
            "type": "string",
            "enum": sorted(_choices(enums.ReportedStatus)),
        },
        "instruction": {"type": "string"},
        "suggested_next_action": {
            "type": "string",
            "enum": sorted(_choices(enums.NextActionCode)),
        },
        "reference": {"type": "string"},
        "confidence": {"type": "number"},
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": "string"},
        "paraphrase": {"type": "string"},
    },
    # "paraphrase" is required so constrained decoding can't skip it -- the
    # citizen always sees a plain-English confirmation, not just when the
    # model happens to include one (§20 in spirit).
    "required": ["kind", "channel", "title", "confidence", "paraphrase"],
}

JOURNEY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "goal": {"type": "string"},
        "organization": {"type": "string"},
        "confidence": {"type": "number"},
        "guide_summary": {"type": "string"},
        "guide_steps": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "topic": {"type": "string"},
                },
                "required": ["title", "description", "topic"],
            },
        },
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": "string"},
    },
    "required": ["title", "goal", "guide_summary", "guide_steps"],
}

PROSE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}
