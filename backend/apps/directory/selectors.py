"""
Responsible-organization resolution (CLAUDE.md §21).

The rule this module exists to enforce: an organization is only ever named if it
is in the curated directory. A language model may help classify what a journey is
*about*, but the final answer resolves through known application data.

The honest null answer matters as much as the positive one. Two outcomes that
weaker tools get wrong:

* no confident match returns ``None`` with an explicit message, rather than the
  nearest plausible-sounding department;
* "nobody, you need to wait" is a legitimate, deliberate answer. A system that
  manufactures a human to contact when the correct answer is to wait sends
  people into phone queues for nothing.
"""
from .models import Organization

NO_MATCH_MESSAGE = (
    "We do not have enough verified information to identify the responsible "
    "organization."
)

WAIT_MESSAGE = (
    "No organization needs to hear from you right now. Your last recorded "
    "update said to wait."
)


def known_organizations():
    """
    Compact directory payload for the AI gateway.

    This is the allow-list: the extractor may only return an organization that
    appears here (§21).
    """
    return [
        {
            "name": org.name,
            "short_name": org.short_name,
            "aliases": list(org.aliases or []),
        }
        for org in Organization.objects.all()
    ]


def match_organization_by_name(name):
    """Resolve a free-text organization name to a directory record, or None."""
    if not name:
        return None
    wanted = name.strip().lower()
    if not wanted:
        return None

    for org in Organization.objects.all():
        candidates = [org.name, org.short_name] + list(org.aliases or [])
        if any(wanted == (c or "").strip().lower() for c in candidates):
            return org
    return None


def match_organization_by_topic(text):
    """
    Route a topic to the organization that handles it.

    Longest keyword wins, so "study permit" beats a bare "permit" and
    "health card" is not captured by a generic "health" rule.
    """
    if not text:
        return None
    lowered = text.lower()
    best = None
    best_length = 0
    for org in Organization.objects.all():
        for keyword in org.topic_keywords or []:
            keyword = (keyword or "").strip().lower()
            if keyword and keyword in lowered and len(keyword) > best_length:
                best = org
                best_length = len(keyword)
    return best


def resolve_responsible_organization(journey, state, breadcrumbs=None):
    """
    Decide who is responsible for the next step.

    Resolution order, most-specific evidence first:

    1. the organization named in the breadcrumb that produced the current state;
    2. the journey's own primary organization;
    3. the most recent organization the citizen actually interacted with;
    4. a topic match against the journey title and goal.

    Returns a dict describing the answer, including the case where the answer is
    that nobody needs contacting.
    """
    from apps.journeys import enums

    waiting = state.status == enums.JourneyStatus.WAITING

    organization = None
    basis = ""

    if state.evidence_organization:
        organization = match_organization_by_name(state.evidence_organization)
        basis = "LATEST_RECORDED_INTERACTION"

    if organization is None and journey.primary_organization_id:
        organization = journey.primary_organization
        basis = "JOURNEY_ORGANIZATION"

    if organization is None and breadcrumbs:
        for breadcrumb in sorted(
            breadcrumbs, key=lambda b: b.occurred_at, reverse=True
        ):
            if not breadcrumb.counts_as_evidence:
                continue
            organization = breadcrumb.organization or match_organization_by_name(
                breadcrumb.organization_name
            )
            if organization is not None:
                basis = "RECORDED_INTERACTION"
                break

    if organization is None:
        organization = match_organization_by_topic(
            " ".join([journey.title or "", journey.goal or ""])
        )
        if organization is not None:
            basis = "CURATED_DIRECTORY_TOPIC_MATCH"

    if organization is None:
        return {
            "responsible_organization": None,
            "basis": None,
            "message": NO_MATCH_MESSAGE,
            "action_needed": not waiting,
        }

    return {
        "responsible_organization": organization,
        "basis": basis,
        "message": WAIT_MESSAGE if waiting else "",
        "action_needed": not waiting,
    }


def official_sources_for(journey, organization=None, limit=5):
    """
    Curated official links relevant to a journey.

    Seeded and human-verified; never scraped at request time (§9.5). Each record
    carries ``verified_at`` so the citizen can judge freshness rather than
    trusting us implicitly.
    """
    from .models import OfficialSource

    queryset = OfficialSource.objects.filter(active=True).select_related(
        "organization"
    )

    org = organization or journey.primary_organization
    if org is not None:
        scoped = queryset.filter(organization=org)
        if scoped.exists():
            queryset = scoped

    haystack = " ".join([journey.title or "", journey.goal or ""]).lower()
    ranked = sorted(
        queryset,
        key=lambda source: (
            0 if source.topic and source.topic.lower() in haystack else 1,
            source.title,
        ),
    )
    return ranked[:limit]
