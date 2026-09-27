"""
Supported-intent gate (CLAUDE.md §15, §16).

This runs *before* any model call and costs nothing. Its job is to keep the
product frictionless but bounded: obviously unrelated input gets a deterministic,
friendly answer that shows what the tool can actually do, and never consumes
quota or reaches a prompt.

It also absorbs prompt-injection attempts (§16). Note the security posture: this
classifier is a cost and UX optimisation, not the security boundary. The real
protections are that user text is always fenced as untrusted data in prompts,
that model output is schema-validated, and that nothing is persisted without the
citizen confirming it. A jailbreak that slipped past this gate would still be
unable to write to the journey.
"""
import re

from apps.journeys.enums import SUPPORTED_ACTIONS, Intent

#: Signals that the input is trying to reassign the assistant role rather than
#: describe something that happened.
_INJECTION_PATTERNS = (
    r"ignore (all )?(previous|prior|above) instructions",
    r"disregard (all )?(previous|prior|above)",
    r"you are now (a|an) ",
    r"system prompt",
    r"reveal your (instructions|prompt|rules)",
    r"act as (a|an) ",
    r"pretend (to be|you are)",
    r"new instructions:",
)

#: Obvious non-civic requests. Kept short on purpose; over-blocking is worse
#: than occasionally passing something through (§15: "do not be hostile").
_OFF_TOPIC_PATTERNS = (
    r"\bwrite (me )?(a|an) (poem|song|story|essay|joke|rap)\b",
    r"\b(sorting|search) algorithm\b",
    r"\bwrite (me )?(some )?(python|java|c\+\+|javascript|sql) (code|script|function)\b",
    r"\btell me a joke\b",
    r"\bwho (won|will win)\b.*\b(game|match|election)\b",
    r"\bwhat is the weather\b",
    r"\btranslate this (into|to)\b",
    r"\brecipes?\b",
    r"\b(cook|cooking|bake|baking)\b",
    r"\b(spaghetti|pasta|pizza|sauce)\b.*\b(make|recipe|cook)\b",
    r"\b(make|cook)\b.*\b(spaghetti|pasta|pizza|sauce)\b",
)

_RECORD_CUES = (
    "called",
    "phoned",
    "emailed",
    "e-mailed",
    "wrote to",
    "went to",
    "visited",
    "submitted",
    "applied",
    "uploaded",
    "received",
    "they said",
    "they told me",
    "he said",
    "she said",
    "was told",
    "sent",
    "spoke",
    "talked",
    "letter",
    "appointment",
    "they asked",
)

_STATE_CUES = (
    "where am i",
    "where did i leave",
    "what is my status",
    "what happened",
    "current state",
    "left off",
)

_NEXT_ACTION_CUES = (
    "what do i do",
    "what should i do",
    "what next",
    "next step",
    "do i need to do",
    "am i waiting",
)

_ORG_CUES = (
    "who do i talk to",
    "who do i contact",
    "who handles",
    "who is responsible",
    "which department",
    "which office",
)

_HANDOFF_CUES = (
    "hand me off",
    "handoff",
    "summary for",
    "explain my situation",
    "summarise",
    "summarize",
)

_CREATE_CUES = (
    "i need to",
    "i want to",
    "i am trying to",
    "trying to get",
    "how do i get",
    "i just moved",
    "help me",
    "i have to",
)

_OUT_OF_SCOPE_MESSAGE = (
    "I can help you keep track of your public-service journey. You can record "
    "what happened, see where you left off, identify the responsible "
    "organization, or prepare a handoff summary."
)


def _matches_any(text, patterns):
    return any(re.search(pattern, text) for pattern in patterns)


def _contains_any(text, cues):
    return any(cue in text for cue in cues)


def looks_like_injection(text):
    """Whether the input is attempting to redefine the application role."""
    return _matches_any((text or "").lower(), _INJECTION_PATTERNS)


def classify_intent(text):
    """
    Map free text onto the bounded action set. Deterministic, zero AI calls.

    Ordering matters: injection and off-topic checks run first so that a
    jailbreak wrapped in plausible civic language does not get a model call.
    """
    lowered = (text or "").strip().lower()
    if not lowered:
        return Intent.OUT_OF_SCOPE
    if looks_like_injection(lowered) or _matches_any(lowered, _OFF_TOPIC_PATTERNS):
        return Intent.OUT_OF_SCOPE

    if _contains_any(lowered, _HANDOFF_CUES):
        return Intent.GENERATE_HANDOFF
    if _contains_any(lowered, _ORG_CUES):
        return Intent.ASK_RESPONSIBLE_ORG
    if _contains_any(lowered, _STATE_CUES):
        return Intent.ASK_CURRENT_STATE
    if _contains_any(lowered, _NEXT_ACTION_CUES):
        return Intent.ASK_NEXT_ACTION
    # A past-tense report of an event beats a forward-looking goal phrase,
    # because "I need to upload the document they asked for" is a record of an
    # instruction, not a new journey.
    if _contains_any(lowered, _RECORD_CUES):
        return Intent.RECORD_EVENT
    if _contains_any(lowered, _CREATE_CUES):
        return Intent.CREATE_JOURNEY
    return Intent.RECORD_EVENT


def out_of_scope_response():
    """The deterministic reply for unsupported input (CLAUDE.md §15)."""
    return {
        "type": Intent.OUT_OF_SCOPE,
        "message": _OUT_OF_SCOPE_MESSAGE,
        "suggested_actions": list(SUPPORTED_ACTIONS),
    }


def is_supported_for_recording(intent):
    """Whether this intent should proceed to breadcrumb interpretation."""
    return intent in {
        Intent.RECORD_EVENT,
        Intent.CREATE_JOURNEY,
        Intent.CORRECT_INFORMATION,
    }
