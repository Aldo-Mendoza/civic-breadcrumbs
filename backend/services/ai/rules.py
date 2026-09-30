"""
Deterministic extraction (the default engine).

This is not a stub that fills in for a missing model. It is the primary
implementation: it satisfies the same contract as the Gemini adapter, it is what
runs when no key is configured, and it is what the product falls back to the
instant a model call fails. Every user-facing feature works with this alone.

Why build it this way round? Three reasons, in order of importance:

1. A civic tool that stops working when a vendor has an outage, a quota runs
   out, or the venue wifi drops is not dependable enough for the people who need
   it most (§28, §35).
2. It makes the AI genuinely replaceable, which is the architectural claim the
   spec makes (§11: "bounded, efficient, structured, and replaceable").
3. It keeps the core free of proprietary dependencies.

The tradeoff is honest: this reads cue words, so it is more literal than a model
and will miss unusual phrasings. That is exactly why every draft goes to the
citizen for review before it is saved (§24) -- the review step is not a
formality bolted onto an AI feature, it is the mechanism that makes a modest
extractor safe to rely on.
"""
import re
from datetime import date, timedelta

from django.utils.translation import get_language

from apps.directory.selectors import match_organization_by_topic
from apps.journeys import enums

from .schemas import BreadcrumbDraft, GuideStepDraft, JourneyDraft, ProseSummary
from .schemas import clarification_for as _clarification_for


def _is_french():
    return (get_language() or "en").startswith("fr")


def _phrase_present(phrase, lowered):
    """
    Whether ``phrase`` appears in ``lowered`` as a whole word/phrase, not as a
    substring of an unrelated word.

    A plain ``phrase in lowered`` check is exactly the bug this guards
    against: a short keyword like "sin" is a substring of ordinary words
    ("since", "using", "basin"), so an unqualified containment check silently
    mislabels a citizen's goal (§21's "never invent" concern applies just as
    much to a wrong topic as to a wrong organization). Word boundaries are
    checked only at the two ends of the whole phrase -- an internal space
    already separates words, so this works for multi-word cues too.
    """
    return re.search(r"\b" + re.escape(phrase) + r"\b", lowered) is not None


# ---------------------------------------------------------------------------
# Cue tables. Ordered most-specific first where order matters.
#
# French localization, Phase E: this is the guaranteed-availability engine
# (runs whenever Gemini is down, rate-limited, or AI_ENABLED=false), so it
# must understand French input and produce French output just as reliably as
# English -- a citizen should never see a worse, English-biased experience
# here just because Gemini happened to be unavailable at that moment.
# ---------------------------------------------------------------------------

_CHANNEL_CUES_FR = (
    (enums.Channel.PHONE, (
        "appelé", "téléphoné", "au téléphone", "par téléphone",
        "appel téléphonique", "raccroché", "en attente", "centre d'appel",
    )),
    (enums.Channel.EMAIL, (
        "envoyé un courriel", "par courriel", "courriel de", "courriel disait",
        "répondu par courriel", "courriel indique",
    )),
    (enums.Channel.IN_PERSON, (
        "suis allé", "visité", "en personne", "au bureau", "centre de service",
        "comptoir", "rendez-vous à", "déposé en personne",
    )),
    (enums.Channel.LETTER, (
        "lettre", "par la poste", "dans le courrier", "enveloppe", "posté",
    )),
    (enums.Channel.UPLOAD, (
        "téléversé", "joint", "soumis en ligne", "téléversement",
    )),
    (enums.Channel.WEB, (
        "site web", "portail", "compte en ligne", "en ligne", "le site",
        "page web", "mon compte",
    )),
)

_STATUS_CUES_FR = (
    (enums.ReportedStatus.PROCESSING, (
        "toujours en traitement", "en cours de traitement", "en traitement",
        "en cours",
    )),
    (enums.ReportedStatus.UNDER_REVIEW, (
        "en révision", "en cours de révision", "en évaluation",
    )),
    (enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED, (
        "besoin de plus de renseignements", "renseignements supplémentaires",
        "document supplémentaire", "informations supplémentaires",
        "autre document", "demandé plus",
    )),
    (enums.ReportedStatus.INCOMPLETE, (
        "incomplète", "incomplet", "manquant", "n'était pas complète",
    )),
    (enums.ReportedStatus.APPROVED, (
        "approuvée", "approuvé", "accordée", "acceptée", "délivré",
    )),
    (enums.ReportedStatus.REFUSED, (
        "refusée", "refusé", "rejetée", "refoulé",
    )),
    (enums.ReportedStatus.RESOLVED, (
        "résolue", "résolu", "fermé", "réglé", "terminé",
    )),
    (enums.ReportedStatus.RECEIVED, (
        "reçu ma demande", "ils ont reçu", "confirmation", "accusé de réception",
        "reçu mon dossier",
    )),
    (enums.ReportedStatus.SUBMITTED, (
        "soumise", "soumis", "envoyé", "déposé", "demandé",
    )),
)

_ACTION_CUES_FR = (
    (enums.NextActionCode.WAIT, (
        "ne pas soumettre une autre", "ne soumettez pas une autre",
        "ne pas réappliquer", "juste attendre", "d'attendre", "attendre",
        "aucune action", "rien à faire", "rien de plus", "aucune autre action",
        "soyez patient",
    )),
    (enums.NextActionCode.UPLOAD, (
        "téléverser", "joindre", "envoyez-nous une copie", "envoyer une copie",
        "numériser et envoyer",
    )),
    (enums.NextActionCode.PROVIDE_DOCUMENT, (
        "fournir", "apporter", "besoin d'un autre document",
        "besoin d'un document", "preuve de", "envoyer le document",
        "avec une pièce d'identité",
    )),
    (enums.NextActionCode.VISIT, (
        "venir", "visiter", "en personne", "prendre rendez-vous",
        "aller au bureau",
    )),
    (enums.NextActionCode.CALL, (
        "rappeler", "les rappeler", "nous appeler",
    )),
    (enums.NextActionCode.SUBMIT, (
        "soumettre", "réappliquer", "redemander", "remplir le formulaire",
        "compléter le formulaire",
    )),
)

#: Clause markers introducing something the citizen was told to do, French.
_INSTRUCTION_MARKERS_FR = (
    "m'a dit de",
    "m'a dit de ne pas",
    "m'a dit",
    "a dit de",
    "a dit que je devrais",
    "a dit que je dois",
    "m'a demandé de",
    "m'a conseillé de",
    "conseillé",
    "m'a instruit de",
    "instruit",
    "je dois",
    "je devrais",
    "il faut que je",
    "ils veulent",
    "ils ont besoin",
)

_KIND_ACTION_CUES_FR = ("soumis", "demandé", "déposé", "payé", "envoyé", "renouvelé")
_KIND_DOCUMENT_CUES_FR = ("téléversé", "joint", "document", "lettre", "formulaire", "reçu")
_KIND_SOURCE_CUES_FR = ("le site dit", "selon", "la page dit", "j'ai lu sur",
                        "trouvé sur le site")
_KIND_INTERACTION_CUES_FR = ("appelé", "téléphoné", "envoyé un courriel", "parlé",
                             "visité", "suis allé", "ils ont dit", "on m'a dit",
                             "a dit", "contacté", "rencontré")


def _channel_cues():
    return _CHANNEL_CUES_FR if _is_french() else _CHANNEL_CUES


def _status_cues():
    return _STATUS_CUES_FR if _is_french() else _STATUS_CUES


def _action_cues():
    return _ACTION_CUES_FR if _is_french() else _ACTION_CUES


def _instruction_markers():
    return _INSTRUCTION_MARKERS_FR if _is_french() else _INSTRUCTION_MARKERS


def _kind_action_cues():
    return _KIND_ACTION_CUES_FR if _is_french() else _KIND_ACTION_CUES


def _kind_document_cues():
    return _KIND_DOCUMENT_CUES_FR if _is_french() else _KIND_DOCUMENT_CUES


def _kind_source_cues():
    return _KIND_SOURCE_CUES_FR if _is_french() else _KIND_SOURCE_CUES


def _kind_interaction_cues():
    return _KIND_INTERACTION_CUES_FR if _is_french() else _KIND_INTERACTION_CUES


_CHANNEL_CUES = (
    (enums.Channel.PHONE, (
        "called", "phoned", "rang", "on the phone", "over the phone",
        "phone call", "hung up", "on hold", "call centre", "call center",
    )),
    (enums.Channel.EMAIL, (
        "emailed", "e-mailed", "sent an email", "sent an e-mail", "by email",
        "email from", "email said", "replied by email", "inbox",
    )),
    (enums.Channel.IN_PERSON, (
        "went to", "visited", "in person", "at the office", "service centre",
        "service center", "counter", "walked in", "appointment at",
        "dropped off",
    )),
    (enums.Channel.LETTER, (
        "letter", "by mail", "in the mail", "envelope", "post", "mailed me",
    )),
    (enums.Channel.UPLOAD, (
        "uploaded", "attached", "submitted online", "upload",
    )),
    (enums.Channel.WEB, (
        "website", "web site", "portal", "online account", "online", "the site",
        "web page", "webpage", "my account",
    )),
)

_STATUS_CUES = (
    (enums.ReportedStatus.PROCESSING, (
        "still processing", "in processing", "being processed", "still in process",
        "processing", "in progress",
    )),
    (enums.ReportedStatus.UNDER_REVIEW, (
        "under review", "being reviewed", "in review", "under assessment",
    )),
    (enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED, (
        "need more information", "needs more information", "additional document",
        "additional information", "more documents", "another document",
        "need another", "requested more",
    )),
    (enums.ReportedStatus.INCOMPLETE, (
        "incomplete", "missing", "was not complete", "not complete",
    )),
    (enums.ReportedStatus.APPROVED, (
        "approved", "granted", "accepted", "issued",
    )),
    (enums.ReportedStatus.REFUSED, (
        "refused", "rejected", "denied", "turned down",
    )),
    (enums.ReportedStatus.RESOLVED, (
        "resolved", "closed", "sorted out", "all set", "finished",
    )),
    (enums.ReportedStatus.RECEIVED, (
        "received my application", "they received", "confirmation", "acknowledged",
        "got my application",
    )),
    (enums.ReportedStatus.SUBMITTED, (
        "submitted", "sent in", "filed", "applied",
    )),
)

_ACTION_CUES = (
    (enums.NextActionCode.WAIT, (
        "not to submit another", "do not submit another", "dont submit another",
        "not to apply again", "just wait", "to wait", "wait for",
        "no action", "nothing to do", "nothing further", "no further action",
        "be patient",
    )),
    (enums.NextActionCode.UPLOAD, (
        "upload", "attach", "send us a copy", "send a copy", "scan and send",
    )),
    (enums.NextActionCode.PROVIDE_DOCUMENT, (
        "provide", "bring", "need another document", "need a document",
        "proof of", "send the document", "with identification", "bring id",
    )),
    (enums.NextActionCode.VISIT, (
        "come in", "visit", "in person", "book an appointment", "make an appointment",
        "go to the office",
    )),
    (enums.NextActionCode.CALL, (
        "call back", "call them", "phone back", "call us",
    )),
    (enums.NextActionCode.SUBMIT, (
        "submit", "apply again", "reapply", "fill out", "complete the form",
    )),
)

#: Clause markers introducing something the citizen was told to do.
_INSTRUCTION_MARKERS = (
    "told me to",
    "told me not to",
    "told me",
    "said to",
    "said not to",
    "said i should",
    "said i need to",
    "said i needed to",
    "asked me to",
    "advised me to",
    "advised",
    "instructed me to",
    "instructed",
    "i need to",
    "i have to",
    "i should",
    "i must",
    "they want",
    "they need",
)

#: Checked before any kind/organization/status detection runs. Without this,
#: a hypothetical or explicitly-negated sentence ("if they ask...", "I have
#: not submitted...") gets read the same as a plain factual report, because
#: the cue tables below match on bare substrings like "submitted" or "ask"
#: with no awareness of negation -- turning a citizen's caveat into a
#: fabricated event. Deliberately narrow and literal (a false miss just
#: means normal extraction proceeds; a false hit only costs one review step).
_HYPOTHETICAL_MARKERS = (
    "if they ask", "if he asks", "if she asks", "if asked",
    "in case they ask", "in case i'm asked", "in case i am asked",
    "nobody asked", "no one asked", "no one has asked",
    "have not submitted", "haven't submitted", "has not submitted", "hasn't submitted",
    "did not submit", "didn't submit",
    "have not called", "haven't called", "have not applied", "haven't applied",
    "have not sent", "haven't sent", "have not contacted", "haven't contacted",
    "i have not", "i haven't", "i've not",
)
_HYPOTHETICAL_MARKERS_FR = (
    "s'ils demandent", "s'il demande", "si on me demande", "au cas où on demande",
    "personne n'a demandé", "personne ne m'a demandé",
    "je n'ai pas soumis", "je n'ai pas encore soumis", "je n'ai pas déposé",
    "je n'ai pas appelé", "je n'ai pas encore appelé",
    "je n'ai pas envoyé", "je n'ai rien envoyé", "je n'ai rien soumis",
    "je n'ai pas contacté", "je n'ai pas encore contacté",
)


def _is_hypothetical_or_negated(lowered):
    markers = _HYPOTHETICAL_MARKERS_FR if _is_french() else _HYPOTHETICAL_MARKERS
    return any(marker in lowered for marker in markers)


_KIND_ACTION_CUES = ("submitted", "applied", "filed", "paid", "sent in", "renewed")
_KIND_DOCUMENT_CUES = ("uploaded", "attached", "document", "letter", "form", "receipt")
_KIND_SOURCE_CUES = ("website says", "site says", "according to", "the page says",
                     "i read on", "found on the website")
_KIND_INTERACTION_CUES = ("called", "phoned", "emailed", "e-mailed", "spoke",
                          "talked", "visited", "went to", "they said",
                          "they told me", "was told", "he said", "she said",
                          "contacted", "reached out", "met with")

#: A reference is only captured when the citizen labelled it as one. Scraping
#: every long number would collect phone numbers and partial identifiers nobody
#: asked us to store (§30, data minimization).
#: Bilingual keyword alternation: matching either language's word is only
#: ever safer, same reasoning as state.py's _WAIT_PHRASES (a French keyword
#: cannot spuriously match English text or vice versa).
_REFERENCE_RE = re.compile(
    r"(?:reference|ref|application|file|confirmation|tracking|case"
    r"|référence|réf|demande|dossier|confirmation|suivi|cas)\s*"
    r"(?:number|no\.?|#|id|numéro|n[o°]\.?)?\s*"
    r"(?:is|was|:|#|=|est|était)?\s*"
    r"([A-Za-z0-9][A-Za-z0-9-]{4,24})",
    re.IGNORECASE,
)

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    # French month names, added unconditionally (see comment above _REFERENCE_RE).
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTH_DAY_RE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE
)
_DAY_MONTH_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(_MONTHS) + r")\b", re.IGNORECASE
)


def _first_cue(text, table):
    """Return the first (value, matched_cue) whose cue appears in text."""
    for value, cues in table:
        for cue in cues:
            if cue in text:
                return value, cue
    return None, None


def _detect_date(text, today):
    """
    Resolve a date from relative or explicit references.

    Returns None when nothing is stated; the caller then defaults to "today"
    rather than guessing a date the citizen never gave us.
    """
    lowered = text.lower()

    # Bilingual phrase checks, added unconditionally (see the comment above
    # _REFERENCE_RE -- matching either language's phrase is only ever safer).
    if "yesterday" in lowered or "hier" in lowered:
        return today - timedelta(days=1)
    if (
        "today" in lowered or "this morning" in lowered or "this afternoon" in lowered
        or "aujourd'hui" in lowered or "aujourdhui" in lowered
        or "ce matin" in lowered or "cet après-midi" in lowered
    ):
        return today
    if "last week" in lowered or "la semaine dernière" in lowered or "la semaine derniere" in lowered:
        return today - timedelta(days=7)
    if "two weeks ago" in lowered or "2 weeks ago" in lowered or "il y a deux semaines" in lowered or "il y a 2 semaines" in lowered:
        return today - timedelta(days=14)
    if "last month" in lowered or "le mois dernier" in lowered:
        return today - timedelta(days=30)

    # French puts the quantifier before the number ("il y a {n} jours") where
    # English puts it after ("{n} days ago") -- two patterns, not one shared
    # numeric capture, so an unrelated number ("3 jours de congé") can't
    # falsely match just because "il y a" appears elsewhere in the sentence.
    days_ago = re.search(r"(\d{1,3})\s+days?\s+ago", lowered) or re.search(
        r"il y a\s+(\d{1,3})\s+jours?", lowered
    )
    if days_ago:
        return today - timedelta(days=int(days_ago.group(1)))

    weeks_ago = re.search(r"(\d{1,2})\s+weeks?\s+ago", lowered) or re.search(
        r"il y a\s+(\d{1,2})\s+semaines?", lowered
    )
    if weeks_ago:
        return today - timedelta(weeks=int(weeks_ago.group(1)))

    iso = _ISO_DATE_RE.search(text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    month_day = _MONTH_DAY_RE.search(text)
    if month_day:
        return _safe_date(today.year, _MONTHS[month_day.group(1).lower()],
                          int(month_day.group(2)), today)

    day_month = _DAY_MONTH_RE.search(text)
    if day_month:
        return _safe_date(today.year, _MONTHS[day_month.group(2).lower()],
                          int(day_month.group(1)), today)

    return None


def _detect_reference(text):
    """
    Capture a reference number, but only a labelled one.

    A candidate must contain a digit and be long enough to be an identifier,
    which keeps ordinary words after "application" ("application status") from
    being stored as a reference.
    """
    match = _REFERENCE_RE.search(text)
    if not match:
        return ""
    candidate = match.group(1).strip("-")
    if len(candidate) < 5 or not any(ch.isdigit() for ch in candidate):
        return ""
    return candidate


def _safe_date(year, month, day, today):
    """
    Build a date, assuming the recent past when no year is given.

    A bare "September 24" heard in January means last September, not a date nine
    months in the future.
    """
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    if candidate > today:
        try:
            return date(year - 1, month, day)
        except ValueError:
            return None
    return candidate


def _detect_organization(text, known_organizations):
    """
    Match against the curated directory only.

    Organizations are never invented from free text (§21): an unrecognised name
    is left blank so the citizen can supply it during review, rather than the
    system asserting a public body that may not exist.

    Returns ``(canonical_name, display_name)``. The canonical name resolves the
    directory foreign key; the display name is what a person would actually say,
    so a timeline reads "Called IRCC" rather than "Called Immigration, Refugees
    and Citizenship Canada".
    """
    lowered = text.lower()
    best = None
    best_length = 0
    for entry in known_organizations or ():
        name = entry.get("name", "")
        candidates = [name, entry.get("short_name", "")] + list(
            entry.get("aliases") or []
        )
        for alias in candidates:
            alias = (alias or "").strip().lower()
            if not alias or len(alias) < 3:
                continue
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, lowered) and len(alias) > best_length:
                best = entry
                best_length = len(alias)

    if best is None:
        return "", ""
    canonical = best.get("name", "")
    return canonical, (best.get("short_name") or canonical)


def _detect_instruction(text):
    """Pull out the clause describing what the citizen was told to do."""
    lowered = text.lower()
    french = _is_french()
    for marker in _instruction_markers():
        index = lowered.find(marker)
        if index == -1:
            continue
        start = index + len(marker)
        tail = text[start:].strip(" ,:;-")
        # Stop at a sentence boundary so we keep one instruction, not a
        # paragraph. Bilingual boundary words, added unconditionally -- see
        # the comment above _REFERENCE_RE.
        clause = re.split(
            r"[.!?]|\band\s+(?:then\s+)?(?:i|they)\b|\bet\s+(?:puis\s+)?(?:je|ils)\b",
            tail,
        )[0]
        clause = clause.strip(" ,:;-")
        if len(clause) < 3:
            continue
        if french:
            negated = "ne pas" in marker
            clause = ("Ne pas " if negated else "") + clause
        else:
            negated = "not to" in marker or marker.endswith("not to")
            clause = ("Do not " if negated else "") + clause
        return clause[:500]
    return ""


def _detect_kind(text, channel, has_status, has_instruction):
    if any(cue in text for cue in _kind_source_cues()):
        return enums.BreadcrumbKind.SOURCE
    if any(cue in text for cue in _kind_interaction_cues()):
        return enums.BreadcrumbKind.INTERACTION
    if any(cue in text for cue in _kind_action_cues()):
        return enums.BreadcrumbKind.ACTION
    if any(cue in text for cue in _kind_document_cues()):
        return enums.BreadcrumbKind.DOCUMENT
    if has_status:
        return enums.BreadcrumbKind.STATUS_UPDATE
    if channel != enums.Channel.UNKNOWN or has_instruction:
        return enums.BreadcrumbKind.INTERACTION
    return enums.BreadcrumbKind.NOTE


_TITLE_VERBS_FR = {
    enums.Channel.PHONE: "Appel à",
    enums.Channel.EMAIL: "Courriel à",
    enums.Channel.IN_PERSON: "Visite à",
    enums.Channel.LETTER: "Lettre de",
    enums.Channel.UPLOAD: "Téléversé à",
    enums.Channel.WEB: "Vérifié en ligne avec",
}


def _build_title(text, kind, channel, organization):
    """A short, scannable timeline label."""
    french = _is_french()
    verb = (_TITLE_VERBS_FR if french else {
        enums.Channel.PHONE: "Called",
        enums.Channel.EMAIL: "Emailed",
        enums.Channel.IN_PERSON: "Visited",
        enums.Channel.LETTER: "Letter from",
        enums.Channel.UPLOAD: "Uploaded to",
        enums.Channel.WEB: "Checked online with",
    }).get(channel)

    if organization and verb:
        return "{verb} {org}".format(verb=verb, org=organization)
    if kind == enums.BreadcrumbKind.ACTION:
        return "Demande ou action enregistrée" if french else "Application or action recorded"
    if kind == enums.BreadcrumbKind.DOCUMENT:
        return "Document enregistré" if french else "Document recorded"
    if kind == enums.BreadcrumbKind.STATUS_UPDATE:
        return "Mise à jour de statut enregistrée" if french else "Status update recorded"
    if organization:
        template = "Contact avec {org}" if french else "Contact with {org}"
        return template.format(org=organization)

    first_sentence = re.split(r"[.!?]", text.strip())[0].strip()
    if len(first_sentence) > 80:
        first_sentence = first_sentence[:77].rsplit(" ", 1)[0] + "..."
    return first_sentence or ("Note" if french else "Note")


_PARAPHRASE_VERBS = {
    enums.Channel.PHONE: "called",
    enums.Channel.EMAIL: "emailed",
    enums.Channel.IN_PERSON: "visited",
    enums.Channel.WEB: "checked online with",
    enums.Channel.LETTER: "got a letter from",
    enums.Channel.UPLOAD: "uploaded something to",
}

_PARAPHRASE_VERBS_FR = {
    enums.Channel.PHONE: "avez appelé",
    enums.Channel.EMAIL: "avez envoyé un courriel à",
    enums.Channel.IN_PERSON: "avez visité",
    enums.Channel.WEB: "avez vérifié en ligne avec",
    enums.Channel.LETTER: "avez reçu une lettre de",
    enums.Channel.UPLOAD: "avez téléversé quelque chose à",
}

_PARAPHRASE_STATUS_LABELS = {
    enums.ReportedStatus.SUBMITTED: "your application was submitted",
    enums.ReportedStatus.RECEIVED: "your application was received",
    enums.ReportedStatus.PROCESSING: "your application is still processing",
    enums.ReportedStatus.UNDER_REVIEW: "your application is still under review",
    enums.ReportedStatus.INCOMPLETE: "your application was incomplete",
    enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED: (
        "they need more information from you"
    ),
    enums.ReportedStatus.APPROVED: "your application was approved",
    enums.ReportedStatus.REFUSED: "your application was refused",
    enums.ReportedStatus.RESOLVED: "the matter was resolved",
}

_PARAPHRASE_STATUS_LABELS_FR = {
    enums.ReportedStatus.SUBMITTED: "votre demande a été soumise",
    enums.ReportedStatus.RECEIVED: "votre demande a été reçue",
    enums.ReportedStatus.PROCESSING: "votre demande est toujours en traitement",
    enums.ReportedStatus.UNDER_REVIEW: "votre demande est toujours en révision",
    enums.ReportedStatus.INCOMPLETE: "votre demande était incomplète",
    enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED: (
        "ils ont besoin de plus de renseignements de votre part"
    ),
    enums.ReportedStatus.APPROVED: "votre demande a été approuvée",
    enums.ReportedStatus.REFUSED: "votre demande a été refusée",
    enums.ReportedStatus.RESOLVED: "le dossier a été résolu",
}


def _build_paraphrase(organization_stated, organization_display, channel, status, instruction):
    """
    One honest sentence confirming what was understood.

    This can only ever restate values already computed above -- there is no
    path here to inventing a fact, which is what makes it safe to show before
    any correction step (§4.2 in spirit: nothing here is a claim about
    eligibility, timelines, or an official outcome that was not literally
    extracted from the citizen's own words).
    """
    french = _is_french()
    verb = (_PARAPHRASE_VERBS_FR if french else _PARAPHRASE_VERBS).get(channel)
    # An inferred (not stated) organization is a guess -- do not put words in
    # the citizen's mouth about who they contacted until they confirm it.
    org = organization_display if organization_stated else ""

    if french:
        if verb and org:
            subject = "vous {verb} {org}".format(verb=verb, org=org)
        elif org:
            subject = "vous étiez en contact avec {org}".format(org=org)
        elif verb:
            subject = "vous les {verb}".format(verb=verb)
        else:
            subject = "vous avez enregistré ceci"
    else:
        if verb and org:
            subject = "you {verb} {org}".format(verb=verb, org=org)
        elif org:
            subject = "you were in touch with {org}".format(org=org)
        elif verb:
            subject = "you {verb} them".format(verb=verb)
        else:
            subject = "you recorded this"

    clauses = []
    status_phrase = (_PARAPHRASE_STATUS_LABELS_FR if french else _PARAPHRASE_STATUS_LABELS).get(status)
    if status_phrase:
        clauses.append(("on vous a dit que " if french else "they said ") + status_phrase)
    if instruction:
        clauses.append(("on vous a dit : " if french else "they told you: ") + instruction.rstrip("."))

    if french:
        if not clauses:
            return "Entendu — {subject}.".format(subject=subject)
        return "Entendu — {subject}, et {rest}.".format(
            subject=subject, rest="; ".join(clauses)
        )
    if not clauses:
        return "Got it — {subject}.".format(subject=subject)
    return "Got it — {subject}, and {rest}.".format(
        subject=subject, rest="; ".join(clauses)
    )


def _guide_for(text):
    """Return one honest generic plan when Gemini is unavailable.

    The fallback deliberately has no domain or case templates. It cannot infer
    a person's remaining process safely, so it helps them establish their
    current point and verify the next applicable action instead of pretending
    to offer a personalized guide.
    """
    french = _is_french()
    steps_fr = [
        ("Confirmer où vous en êtes dans le processus", "Faites la liste de ce que vous avez déjà complété, de la confirmation que vous avez reçue, et de ce qui reste non résolu.", ""),
        ("Vérifier la prochaine action officielle applicable", "Utilisez le service officiel responsable pour confirmer la prochaine action pour votre situation actuelle.", ""),
        ("Préparer seulement ce qui reste", "Faites une liste à partir des instructions officielles actuelles et excluez ce que vous avez déjà complété.", ""),
        ("Compléter la prochaine action applicable", "Suivez l'instruction vérifiée pour votre étape actuelle et révisez-la avant de soumettre, d'envoyer, ou de vous présenter.", ""),
        ("Enregistrer la confirmation et le suivi", "Enregistrez les confirmations non sensibles, les interactions, les nouvelles instructions et les résultats pour que la démarche montre où vous en êtes.", ""),
    ]
    steps_en = [
        ("Confirm where you are in the process", "List what you have already completed, what confirmation you received, and what remains unresolved.", ""),
        ("Verify the next applicable official action", "Use the responsible official service to confirm the next action for your current point in the process.", ""),
        ("Prepare only what remains", "Build a checklist from the current official instructions and exclude anything you have already completed.", ""),
        ("Complete the next applicable action", "Follow the verified instruction for your current stage and review it before submitting, sending, or attending.", ""),
        ("Record confirmation and follow-up", "Record non-sensitive confirmations, interactions, new instructions, and outcomes so the Journey shows where you left off.", ""),
    ]
    steps = steps_fr if french else steps_en
    clarification = (
        "Qu'avez-vous déjà complété, et quelle réponse, instruction ou "
        "résultat attendez-vous maintenant?"
        if french
        else (
            "What have you already completed, and what response, instruction, "
            "or result are you waiting for now?"
        )
    )

    return (
        [
            GuideStepDraft(title=title, description=description, topic=topic)
            for title, description, topic in steps
        ],
        clarification,
    )


class RuleBasedAIService:
    """Deterministic implementation of the AI service contract."""

    name = "rules"

    def __init__(self, today=None):
        # Injectable for tests; never reads the clock mid-derivation.
        self._today = today

    def _now(self):
        return self._today or date.today()

    # -- journeys ----------------------------------------------------------

    def extract_journey(self, user_text, source_context=None):
        text = (user_text or "").strip()
        lowered = text.lower()
        french = _is_french()

        topic_titles_en = (
            ("study permit", "Study Permit Extension"),
            ("work permit", "Work Permit"),
            ("permanent residence", "Permanent Residence Application"),
            ("citizenship", "Citizenship Application"),
            ("visa", "Visa Application"),
            ("sin", "Social Insurance Number"),
            ("social insurance", "Social Insurance Number"),
            ("health card", "Health Card"),
            ("ohip", "Health Coverage"),
            ("driver", "Driver Licence"),
            ("drivers", "Driver Licence"),
            ("driver's", "Driver Licence"),
            ("renew my passport", "Passport Renewal"),
            ("renew a passport", "Passport Renewal"),
            ("passport renewal", "Passport Renewal"),
            ("passport", "Passport Application"),
            ("employment insurance", "Employment Insurance"),
            ("tax", "Taxes and Benefits"),
            ("housing", "Housing"),
            ("moved to ottawa", "Settling in Ottawa"),
            ("settle", "Settling in Ottawa"),
        )
        topic_titles_fr = (
            ("permis d'études", "Prolongation du permis d'études"),
            ("permis d'etudes", "Prolongation du permis d'études"),
            ("permis de travail", "Permis de travail"),
            ("résidence permanente", "Demande de résidence permanente"),
            ("residence permanente", "Demande de résidence permanente"),
            ("citoyenneté", "Demande de citoyenneté"),
            ("citoyennete", "Demande de citoyenneté"),
            ("visa", "Demande de visa"),
            ("nas", "Numéro d'assurance sociale"),
            ("assurance sociale", "Numéro d'assurance sociale"),
            ("carte santé", "Carte santé"),
            ("carte sante", "Carte santé"),
            ("ohip", "Couverture santé"),
            ("permis de conduire", "Permis de conduire"),
            ("renouveler mon passeport", "Renouvellement de passeport"),
            ("renouvellement de passeport", "Renouvellement de passeport"),
            ("passeport", "Demande de passeport"),
            ("assurance-emploi", "Assurance-emploi"),
            ("impôt", "Impôts et prestations"),
            ("impot", "Impôts et prestations"),
            ("logement", "Logement"),
            ("déménagé à ottawa", "S'installer à Ottawa"),
            ("demenage a ottawa", "S'installer à Ottawa"),
            ("m'installer", "S'installer à Ottawa"),
        )
        title = ""
        for cue, candidate in (topic_titles_fr if french else topic_titles_en):
            if _phrase_present(cue, lowered):
                title = candidate
                break

        if not title:
            # Fall back to the citizen's own first clause, trimmed.
            clause = re.split(r"[.!?]", text)[0].strip()
            prefix_pattern = (
                r"^(je suis|j'ai|j'|je dois|je veux|je|j ai|j)\s+"
                if french
                else r"^(i|i am|i have|i need to|i want to|i just|im|i m)\s+"
            )
            clause = re.sub(prefix_pattern, "", clause, flags=re.IGNORECASE).strip()
            title = (clause[:60].rsplit(" ", 1)[0] if len(clause) > 60 else clause)
            default_title = "Ma démarche" if french else "My journey"
            title = title.capitalize() or default_title

        guide_steps, clarification = _guide_for(text)
        default_title = "Ma démarche" if french else "My journey"
        guide_summary = (
            (
                "Gemini n'a pas été utilisé, donc ceci est un guide de continuité "
                "générique plutôt qu'un plan propre à votre cas. Confirmez votre "
                "situation actuelle auprès du service officiel responsable, puis "
                "enregistrez ce que vous faites réellement."
            )
            if french
            else (
                "Gemini was not used, so this is a generic continuity guide rather "
                "than a case-specific plan. Confirm your current point with the "
                "responsible official service, then record what you actually do."
            )
        )
        return JourneyDraft(
            title=title,
            goal=text or title,
            organization="",
            confidence=0.8 if title != default_title else 0.4,
            extractor=self.name,
            guide_summary=guide_summary,
            guide_steps=guide_steps,
            needs_clarification=bool(clarification),
            clarification_question=clarification,
        )

    def classify_organization(self, user_text, known_organizations=None):
        """
        Interface parity with the AI contract only -- the deterministic
        engine stays keyword-based by design (it must keep working with no
        model available), so this simply re-runs the same curated-directory
        matching used everywhere else rather than adding a second mechanism.
        """
        organization = match_organization_by_topic(user_text)
        return organization.name if organization else ""

    def summarize_goal(self, user_text):
        """Keep confirmation usable when Gemini is unavailable."""
        fields = {}
        for line in (user_text or "").splitlines():
            label, separator, value = line.partition(":")
            if separator:
                fields[label.strip().lower()] = value.strip()
        goal = fields.get("goal", "")
        situation = fields.get("situation", "")
        core = goal.rstrip(". ") or situation.rstrip(". ")
        if _is_french():
            core = re.sub(r"^(je veux|je dois|j’ai besoin de|j'ai besoin de)\s+", "", core, flags=re.IGNORECASE)
            core = re.sub(r"\b(mon|ma|mes)\b", "votre", core, flags=re.IGNORECASE)
            if len(core) > 1 and not core[:2].isupper():
                core = core[0].lower() + core[1:]
            summary = "Est-ce que vous demandez de l’aide pour atteindre votre objectif de {core}?".format(
                core=core[:180]
            )
        else:
            core = re.sub(r"^(i want to|i need to|to)\s+", "", core, flags=re.IGNORECASE)
            core = re.sub(r"\bmy\b", "your", core, flags=re.IGNORECASE)
            if len(core) > 1 and not core[:2].isupper():
                core = core[0].lower() + core[1:]
            summary = "Are you asking for help with your goal to {core}?".format(
                core=core[:180]
            )
        return ProseSummary(summary=summary or (user_text or "").strip(), extractor=self.name)

    # -- breadcrumbs -------------------------------------------------------

    def extract_breadcrumb(self, user_text, minimal_context):
        text = (user_text or "").strip()
        lowered = text.lower()
        context = minimal_context or {}
        today = self._now()

        if _is_hypothetical_or_negated(lowered):
            # Preserve the citizen's words as a note rather than let cue
            # matching turn a hypothetical or an explicit "I have not done
            # this yet" into a claim that an interaction or action happened.
            french = _is_french()
            return BreadcrumbDraft(
                kind=enums.BreadcrumbKind.NOTE,
                channel=enums.Channel.UNKNOWN,
                title=_build_title(text, enums.BreadcrumbKind.NOTE, enums.Channel.UNKNOWN, ""),
                organization="",
                occurred_on=today,
                reported_status=enums.ReportedStatus.UNKNOWN,
                instruction="",
                suggested_next_action=enums.NextActionCode.NONE,
                reference="",
                confidence=0.3,
                needs_clarification=True,
                clarification_question=(
                    "S'agit-il de quelque chose qui s'est déjà produit, ou d'une "
                    "possibilité que vous décrivez?"
                    if french
                    else "Is this something that already happened, or a possibility you're describing?"
                ),
                paraphrase=(
                    "Entendu — enregistré comme note pour l'instant."
                    if french
                    else "Got it — saved as a note for now."
                ),
                extractor=self.name,
            )

        channel, _ = _first_cue(lowered, _channel_cues())
        channel = channel or enums.Channel.UNKNOWN

        status, _ = _first_cue(lowered, _status_cues())
        status = status or enums.ReportedStatus.UNKNOWN

        instruction = _detect_instruction(text)
        organization, organization_display = _detect_organization(
            text, context.get("known_organizations")
        )
        organization_stated = bool(organization)
        if not organization:
            # Fall back to the journey's own organization: "I called them again"
            # on a study permit journey probably means IRCC. Tracked as inferred,
            # not stated, because an assumed counterparty must still be confirmed.
            organization = context.get("journey_organization", "")
            organization_display = organization

        occurred_on = _detect_date(text, today)
        reference = _detect_reference(text)

        next_action, _ = _first_cue(lowered, _action_cues())
        if not next_action:
            if status in enums.WAITING_STATUSES:
                next_action = enums.NextActionCode.WAIT
            elif status == enums.ReportedStatus.ADDITIONAL_INFO_REQUIRED:
                next_action = enums.NextActionCode.PROVIDE_DOCUMENT
            else:
                next_action = enums.NextActionCode.NONE

        kind = _detect_kind(
            lowered,
            channel,
            status != enums.ReportedStatus.UNKNOWN,
            bool(instruction),
        )

        # Confidence reflects how much we actually recognised, so the review
        # step can be emphasised when the reading is thin.
        confidence = 0.25
        if channel != enums.Channel.UNKNOWN:
            confidence += 0.2
        if organization_stated:
            confidence += 0.2
        elif organization:
            # Inferred from the journey, not stated by the citizen. Worth less.
            confidence += 0.1
        if status != enums.ReportedStatus.UNKNOWN:
            confidence += 0.15
        if instruction:
            confidence += 0.15
        if occurred_on is not None:
            confidence += 0.05
        confidence = round(min(confidence, 1.0), 2)

        # An interaction whose organization we cannot identify always needs one
        # question, however confident the rest of the reading is. "They said I
        # need another thing" is unusable evidence until we know who "they" were
        # -- that is the difference between a record and a rumour (§33 Case C).
        unconfirmed_counterparty = (
            kind == enums.BreadcrumbKind.INTERACTION and not organization_stated
        )
        needs_clarification = confidence < 0.5 or unconfirmed_counterparty
        clarification = (
            _clarification_for(
                organization if organization_stated else "",
                status,
                instruction,
                channel,
            )
            if needs_clarification
            else None
        )

        paraphrase = _build_paraphrase(
            organization_stated, organization_display, channel, status, instruction
        )

        return BreadcrumbDraft(
            kind=kind,
            channel=channel,
            title=_build_title(text, kind, channel, organization_display),
            organization=organization,
            occurred_on=occurred_on or today,
            reported_status=status,
            instruction=instruction,
            suggested_next_action=next_action,
            reference=reference,
            confidence=confidence,
            needs_clarification=needs_clarification,
            clarification_question=clarification,
            paraphrase=paraphrase,
            extractor=self.name,
        )

    # -- prose -------------------------------------------------------------
    #
    # The deterministic engine returns the factual summary unchanged. The
    # structured fields were already built by the domain layer; there is
    # nothing here for a model to add that would be safe to trust.

    def summarize_stuck_state(self, journey_snapshot):
        return ProseSummary(
            summary=(journey_snapshot or {}).get("summary", ""), extractor=self.name
        )

    def generate_handoff(self, journey_snapshot):
        return ProseSummary(
            summary=(journey_snapshot or {}).get("summary", ""), extractor=self.name
        )
