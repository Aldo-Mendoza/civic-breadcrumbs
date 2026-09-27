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

from django.utils.translation import get_language

from apps.journeys.enums import SUPPORTED_ACTIONS, Intent


def _is_french():
    return (get_language() or "en").startswith("fr")


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

#: French counterparts, added unconditionally per module (French localization,
#: mirroring the bilingual-table pattern already used in services/ai/rules.py).
_INJECTION_PATTERNS_FR = (
    r"ignore[z]? (toutes )?(les )?instructions (précédentes|precedentes|antérieures|anterieures|ci-dessus)",
    r"ne tenez pas compte (des|de ces) instructions",
    r"(tu es|vous êtes|vous etes) maintenant (un|une) ",
    r"invite système",
    r"invite systeme",
    r"révél(ez|e)[rz]? (tes|vos) (instructions|règles|regles)",
    r"revel(ez|e)[rz]? (tes|vos) (instructions|règles|regles)",
    r"agis(sez)? comme (un|une) ",
    r"fais(ez)? semblant d'être",
    r"fais(ez)? semblant d'etre",
    r"nouvelles instructions\s*:",
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

_OFF_TOPIC_PATTERNS_FR = (
    r"\bécri[sz](-moi)? (un|une) (poème|poeme|chanson|histoire|essai|blague|rap)\b",
    r"\balgorithme de tri\b",
    r"\bécri[sz](-moi)? (du )?(code|script|fonction) (python|java|c\+\+|javascript|sql)\b",
    r"\braconte(-moi)? une blague\b",
    r"\bqui (a gagné|a gagne|va gagner)\b.*\b(match|partie|élection|election)\b",
    r"\bquel temps (fait-il|va-t-il faire)\b",
    r"\btraduis(ez)? (ceci|ça|ca|cela) (en|vers)\b",
    r"\brecette (de|pour)\b",
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

_RECORD_CUES_FR = (
    "appelé",
    "appele",
    "téléphoné",
    "telephone",
    "envoyé un courriel",
    "envoye un courriel",
    "écrit à",
    "ecrit a",
    "suis allé",
    "suis alle",
    "visité",
    "visite",
    "soumis",
    "postulé",
    "postule",
    "téléversé",
    "televerse",
    "reçu",
    "recu",
    "ils ont dit",
    "on m'a dit",
    "il a dit",
    "elle a dit",
    "a dit",
    "envoyé",
    "envoye",
    "contacté",
    "contacte",
    "lettre",
    "rendez-vous",
    "ils m'ont demandé",
    "ils m'ont demande",
)

_STATE_CUES = (
    "where am i",
    "where did i leave",
    "what is my status",
    "what happened",
    "current state",
    "left off",
)

_STATE_CUES_FR = (
    "où en suis-je",
    "ou en suis-je",
    "où en étais-je",
    "ou en etais-je",
    "quel est mon statut",
    "qu'est-ce qui s'est passé",
    "qu'est-ce qui s'est passe",
    "état actuel",
    "etat actuel",
)

_NEXT_ACTION_CUES = (
    "what do i do",
    "what should i do",
    "what next",
    "next step",
    "do i need to do",
    "am i waiting",
)

_NEXT_ACTION_CUES_FR = (
    "qu'est-ce que je dois faire",
    "que dois-je faire",
    "quelle est la prochaine étape",
    "quelle est la prochaine etape",
    "prochaine étape",
    "prochaine etape",
    "suis-je en attente",
    "dois-je faire quelque chose",
)

_ORG_CUES = (
    "who do i talk to",
    "who do i contact",
    "who handles",
    "who is responsible",
    "which department",
    "which office",
)

_ORG_CUES_FR = (
    "à qui dois-je parler",
    "a qui dois-je parler",
    "qui dois-je contacter",
    "qui s'occupe de",
    "qui est responsable",
    "quel département",
    "quel departement",
    "quel bureau",
)

_HANDOFF_CUES = (
    "hand me off",
    "handoff",
    "summary for",
    "explain my situation",
    "summarise",
    "summarize",
)

_HANDOFF_CUES_FR = (
    "transférer mon dossier",
    "transferer mon dossier",
    "résumé pour",
    "resume pour",
    "expliquer ma situation",
    "résumer",
    "resumer",
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

_CREATE_CUES_FR = (
    "j'ai besoin de",
    "je veux",
    "j'essaie de",
    "j'essaye de",
    "j'ai besoin d'obtenir",
    "je viens de déménager",
    "je viens de demenager",
    "aide-moi",
    "aidez-moi",
    "je dois",
)


def _injection_patterns():
    return _INJECTION_PATTERNS_FR if _is_french() else _INJECTION_PATTERNS


def _off_topic_patterns():
    return _OFF_TOPIC_PATTERNS_FR if _is_french() else _OFF_TOPIC_PATTERNS


def _record_cues():
    return _RECORD_CUES_FR if _is_french() else _RECORD_CUES


def _state_cues():
    return _STATE_CUES_FR if _is_french() else _STATE_CUES


def _next_action_cues():
    return _NEXT_ACTION_CUES_FR if _is_french() else _NEXT_ACTION_CUES


def _org_cues():
    return _ORG_CUES_FR if _is_french() else _ORG_CUES


def _handoff_cues():
    return _HANDOFF_CUES_FR if _is_french() else _HANDOFF_CUES


def _create_cues():
    return _CREATE_CUES_FR if _is_french() else _CREATE_CUES


_OUT_OF_SCOPE_MESSAGE_EN = (
    "I can help you keep track of your public-service journey. You can record "
    "what happened, see where you left off, identify the responsible "
    "organization, or prepare a handoff summary."
)
_OUT_OF_SCOPE_MESSAGE_FR = (
    "Je peux vous aider à suivre votre démarche auprès des services publics. "
    "Vous pouvez enregistrer ce qui s'est passé, voir où vous en êtes, "
    "identifier l'organisation responsable, ou préparer un résumé à transférer."
)


def _out_of_scope_message():
    return _OUT_OF_SCOPE_MESSAGE_FR if _is_french() else _OUT_OF_SCOPE_MESSAGE_EN


def _matches_any(text, patterns):
    return any(re.search(pattern, text) for pattern in patterns)


def _contains_any(text, cues):
    return any(cue in text for cue in cues)


def looks_like_injection(text):
    """Whether the input is attempting to redefine the application role."""
    return _matches_any((text or "").lower(), _injection_patterns())


def classify_intent(text):
    """
    Map free text onto the bounded action set. Deterministic, zero AI calls.

    Ordering matters: injection and off-topic checks run first so that a
    jailbreak wrapped in plausible civic language does not get a model call.
    """
    lowered = (text or "").strip().lower()
    if not lowered:
        return Intent.OUT_OF_SCOPE
    if looks_like_injection(lowered) or _matches_any(lowered, _off_topic_patterns()):
        return Intent.OUT_OF_SCOPE

    if _contains_any(lowered, _handoff_cues()):
        return Intent.GENERATE_HANDOFF
    if _contains_any(lowered, _org_cues()):
        return Intent.ASK_RESPONSIBLE_ORG
    if _contains_any(lowered, _state_cues()):
        return Intent.ASK_CURRENT_STATE
    if _contains_any(lowered, _next_action_cues()):
        return Intent.ASK_NEXT_ACTION
    # A past-tense report of an event beats a forward-looking goal phrase,
    # because "I need to upload the document they asked for" is a record of an
    # instruction, not a new journey.
    if _contains_any(lowered, _record_cues()):
        return Intent.RECORD_EVENT
    if _contains_any(lowered, _create_cues()):
        return Intent.CREATE_JOURNEY
    return Intent.RECORD_EVENT


def out_of_scope_response():
    """The deterministic reply for unsupported input (CLAUDE.md §15)."""
    return {
        "type": Intent.OUT_OF_SCOPE,
        "message": _out_of_scope_message(),
        "suggested_actions": list(SUPPORTED_ACTIONS),
    }


def is_supported_for_recording(intent):
    """Whether this intent should proceed to breadcrumb interpretation."""
    return intent in {
        Intent.RECORD_EVENT,
        Intent.CREATE_JOURNEY,
        Intent.CORRECT_INFORMATION,
    }
