"""
Curated directory seed data (CLAUDE.md §9.4, §34).

Intentionally small. This is the set of institutions an international student in
Ottawa plausibly deals with for one journey, not an attempt at a universal
public-sector directory.

Every URL here is a well-known federal, provincial, municipal or institutional
landing page. ``verified_at`` records when a human last confirmed the link, and
it is shown to the citizen -- we ask them to trust the directory only as far as
its stated freshness.
"""
import hashlib

from django.utils import timezone

from .models import Jurisdiction, Organization, OfficialSource, OfficialSourceSection

ORGANIZATIONS = [
    {
        "name": "Immigration, Refugees and Citizenship Canada",
        "short_name": "IRCC",
        "jurisdiction": Jurisdiction.FEDERAL,
        "description": (
            "Federal department responsible for immigration applications, study "
            "and work permits, permanent residence and citizenship."
        ),
        "official_url": "https://www.canada.ca/en/immigration-refugees-citizenship.html",
        "aliases": [
            "IRCC",
            "immigration canada",
            "citizenship and immigration",
            "immigration refugees and citizenship canada",
            "cic",
        ],
        "topic_keywords": [
            "study permit",
            "work permit",
            "permanent residence",
            "citizenship",
            "visa",
            "immigration",
            "permit extension",
            "biometrics",
            "passport",
            "passport renewal",
        ],
    },
    {
        "name": "Service Canada",
        "short_name": "Service Canada",
        "jurisdiction": Jurisdiction.FEDERAL,
        "description": (
            "Federal service delivery for Social Insurance Numbers, Employment "
            "Insurance and other federal benefits."
        ),
        "official_url": "https://www.canada.ca/en/employment-social-development/corporate/portfolio/service-canada.html",
        "aliases": ["service canada", "sin office"],
        "topic_keywords": [
            "social insurance number",
            "sin",
            "employment insurance",
            "ei",
            "federal benefits",
            "pension",
        ],
    },
    {
        "name": "Government of Ontario",
        "short_name": "Ontario",
        "jurisdiction": Jurisdiction.PROVINCIAL,
        "description": (
            "Provincial services including health coverage, driver licensing and "
            "provincial identification."
        ),
        "official_url": "https://www.ontario.ca/page/government-ontario",
        "aliases": ["ontario", "service ontario", "serviceontario", "province of ontario"],
        "topic_keywords": [
            "health card",
            "ohip",
            "driver licence",
            "drivers license",
            "photo card",
            "provincial",
        ],
    },
    {
        "name": "City of Ottawa",
        "short_name": "City of Ottawa",
        "jurisdiction": Jurisdiction.MUNICIPAL,
        "description": (
            "Municipal services including property taxes, transit, recreation and "
            "local by-laws."
        ),
        "official_url": "https://ottawa.ca/en",
        "aliases": ["city of ottawa", "ottawa city", "municipality of ottawa"],
        "topic_keywords": [
            "property tax",
            "transit",
            "oc transpo",
            "garbage",
            "municipal",
            "parking",
            "recreation",
        ],
    },
    {
        "name": "University International Office",
        "short_name": "International Office",
        "jurisdiction": Jurisdiction.INSTITUTIONAL,
        "description": (
            "University office supporting international students with enrolment "
            "letters, study permit questions and campus services."
        ),
        "official_url": "https://www.uottawa.ca/en/students/international",
        "aliases": [
            "international office",
            "university international office",
            "international student office",
            "my university",
            "the university",
        ],
        "topic_keywords": [
            "enrolment letter",
            "enrollment letter",
            "student status",
            "tuition",
            "university",
            "campus",
        ],
    },
]

OFFICIAL_SOURCES = [
    {
        "organization": "Immigration, Refugees and Citizenship Canada",
        "title": "Extend or change the conditions on your study permit",
        "url": "https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/extend-study-permit.html",
        "description": (
            "Official IRCC guidance on extending a study permit, including what "
            "to do while an application is being processed."
        ),
        "topic": "study permit",
    },
    {
        "organization": "Immigration, Refugees and Citizenship Canada",
        "title": "Check application processing times",
        "url": "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/check-processing-times.html",
        "description": "Official current processing times by application type.",
        "topic": "processing times",
    },
    {
        "organization": "Immigration, Refugees and Citizenship Canada",
        "title": "Contact IRCC",
        "url": "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/contact-ircc.html",
        "description": (
            "Official contact channels, including the client support centre and "
            "web form for case-specific enquiries."
        ),
        "topic": "contact",
    },
    {
        "organization": "Immigration, Refugees and Citizenship Canada",
        "title": "Renew a passport in Canada",
        "url": "https://www.canada.ca/en/immigration-refugees-citizenship/services/canadian-passports/renew-adult-passport.html",
        "description": (
            "Official Passport Program guidance for checking whether an adult "
            "passport can be renewed and following the applicable renewal route."
        ),
        "topic": "passport renewal",
    },
    {
        "organization": "Immigration, Refugees and Citizenship Canada",
        "title": "Apply for a child passport in Canada",
        "url": "https://www.canada.ca/en/immigration-refugees-citizenship/services/canadian-passports/child-passport.html",
        "description": (
            "Official Passport Program guidance for a child or minor passport "
            "application, including situation-specific instructions."
        ),
        "topic": "child passport minor",
    },
    {
        "organization": "Service Canada",
        "title": "Apply for a Social Insurance Number",
        "url": "https://www.canada.ca/en/employment-social-development/services/sin.html",
        "description": "Official process for obtaining or updating a SIN.",
        "topic": "sin",
    },
    {
        "organization": "Government of Ontario",
        "title": "Apply for OHIP health coverage",
        "url": "https://www.ontario.ca/page/apply-ohip-and-get-health-card",
        "description": "Official eligibility and application steps for Ontario health coverage.",
        "topic": "health card",
    },
]


def seed_directory(stdout=None):
    """
    Create or update the curated directory. Idempotent.

    Matching on ``name`` means running this repeatedly refreshes descriptions and
    keywords without duplicating institutions.
    """
    created_orgs = 0
    for entry in ORGANIZATIONS:
        _, created = Organization.objects.update_or_create(
            name=entry["name"],
            defaults={
                "short_name": entry["short_name"],
                "jurisdiction": entry["jurisdiction"],
                "description": entry["description"],
                "official_url": entry["official_url"],
                "aliases": entry["aliases"],
                "topic_keywords": entry["topic_keywords"],
            },
        )
        created_orgs += int(created)

    now = timezone.now()
    created_sources = 0
    for entry in OFFICIAL_SOURCES:
        organization = Organization.objects.get(name=entry["organization"])
        source, created = OfficialSource.objects.get_or_create(
            organization=organization,
            url=entry["url"],
            defaults={
                "title": entry["title"],
                "description": entry["description"],
                "topic": entry["topic"],
                "active": True,
                "verified_at": now,
            },
        )
        if not created:
            # A deployment may update catalog labels, but it must never make a
            # stale or changed page look freshly verified. Freshness advances
            # only through the restricted refresh/review workflow.
            source.title = entry["title"]
            source.description = entry["description"]
            source.topic = entry["topic"]
            source.active = True
            source.save(update_fields=["title", "description", "topic", "active"])
        # Belt-and-braces: fail the seed loudly rather than silently persist a
        # non-government link. update_or_create doesn't run model validation
        # on its own, so this is what actually makes OfficialSource.clean()
        # (government-domain + federal/provincial-only rule) bite here.
        source.full_clean()
        # A manually verified, minimal section keeps a freshly seeded install
        # useful before its first network refresh. The restricted refresher
        # replaces this with heading-level page content after deployment.
        OfficialSourceSection.objects.update_or_create(
            source=source,
            position=1,
            defaults={
                "heading": entry["title"],
                "heading_path": entry["title"],
                "anchor": "",
                "text": entry["description"],
                "content_hash": hashlib.sha256(entry["description"].encode()).hexdigest(),
                "active": True,
                "retrieved_at": now,
            },
        )
        created_sources += int(created)

    if stdout is not None:
        stdout.write(
            "Directory: {o} organizations, {s} official sources "
            "({no} new organizations, {ns} new sources).".format(
                o=Organization.objects.count(),
                s=OfficialSource.objects.count(),
                no=created_orgs,
                ns=created_sources,
            )
        )
