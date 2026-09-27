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
        "description_fr": (
            "Ministère fédéral responsable des demandes d'immigration, des "
            "permis d'études et de travail, de la résidence permanente et de "
            "la citoyenneté."
        ),
        "official_url": "https://www.canada.ca/en/immigration-refugees-citizenship.html",
        # Verified live (2026-09-27): the page's own Français toggle link.
        "official_url_fr": "https://www.canada.ca/fr/immigration-refugies-citoyennete.html",
        "aliases": [
            "IRCC",
            "immigration canada",
            "citizenship and immigration",
            "immigration refugees and citizenship canada",
            "cic",
            "immigration, réfugiés et citoyenneté canada",
            "immigration, refugies et citoyennete canada",
            "citoyenneté et immigration canada",
            "citoyennete et immigration canada",
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
            "permis d'études",
            "permis d'etudes",
            "permis de travail",
            "résidence permanente",
            "residence permanente",
            "citoyenneté",
            "citoyennete",
            "prolongation de permis",
            "biométrie",
            "biometrie",
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
        "description_fr": (
            "Prestation de services fédéraux pour les numéros d'assurance "
            "sociale, l'assurance-emploi et d'autres prestations fédérales."
        ),
        "official_url": "https://www.canada.ca/en/employment-social-development/corporate/portfolio/service-canada.html",
        # Verified live (2026-09-27): the page's own Français toggle link.
        "official_url_fr": "https://www.canada.ca/fr/emploi-developpement-social/ministere/portefeuille/service-canada.html",
        "aliases": ["service canada", "sin office"],
        "topic_keywords": [
            "social insurance number",
            "sin",
            "employment insurance",
            "ei",
            "federal benefits",
            "pension",
            "numéro d'assurance sociale",
            "numero d'assurance sociale",
            "assurance sociale",
            "nas",
            "assurance-emploi",
            "prestations fédérales",
            "prestations federales",
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
        "description_fr": (
            "Services provinciaux, y compris la couverture santé, le permis de "
            "conduire et les pièces d'identité provinciales."
        ),
        "official_url": "https://www.ontario.ca/page/government-ontario",
        # Verified live (2026-09-27): the page's own Français toggle link.
        "official_url_fr": "https://www.ontario.ca/fr/page/gouvernement-de-lontario",
        "aliases": [
            "ontario",
            "service ontario",
            "serviceontario",
            "province of ontario",
            "gouvernement de l'ontario",
            "gouvernement de lontario",
        ],
        "topic_keywords": [
            "health card",
            "ohip",
            "driver licence",
            "drivers license",
            "photo card",
            "provincial",
            "carte santé",
            "carte sante",
            "permis de conduire",
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
        "description_fr": (
            "Services municipaux, y compris les taxes foncières, le transport "
            "en commun, les loisirs et les règlements municipaux."
        ),
        "official_url": "https://ottawa.ca/en",
        # Verified live (2026-09-27): ottawa.ca's own French homepage.
        "official_url_fr": "https://ottawa.ca/fr",
        "aliases": [
            "city of ottawa",
            "ottawa city",
            "municipality of ottawa",
            "ville d'ottawa",
            "ville dottawa",
        ],
        "topic_keywords": [
            "property tax",
            "transit",
            "oc transpo",
            "garbage",
            "municipal",
            "parking",
            "recreation",
            "taxes foncières",
            "taxes foncieres",
            "transport en commun",
            "stationnement",
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
        "description_fr": (
            "Bureau universitaire qui aide les étudiants internationaux pour "
            "les lettres d'inscription, les questions de permis d'études et "
            "les services sur le campus."
        ),
        "official_url": "https://www.uottawa.ca/en/students/international",
        # No official_url_fr: uottawa.ca blocked verification (HTTP 402) and
        # a guessed French slug would be exactly the kind of invented official
        # link CLAUDE.md §21 rules out. Leave blank rather than guess.
        "aliases": [
            "international office",
            "university international office",
            "international student office",
            "my university",
            "the university",
            "bureau international",
            "bureau des étudiants internationaux",
            "bureau des etudiants internationaux",
        ],
        "topic_keywords": [
            "enrolment letter",
            "enrollment letter",
            "student status",
            "tuition",
            "university",
            "campus",
            "lettre d'inscription",
            "statut d'étudiant",
            "statut d'etudiant",
            "frais de scolarité",
            "frais de scolarite",
            "université",
            "universite",
        ],
    },
]

OFFICIAL_SOURCES = [
    {
        "organization": "Immigration, Refugees and Citizenship Canada",
        "title": "Extend or change the conditions on your study permit",
        "title_fr": "Prolonger ou modifier les conditions de votre permis d'études",
        "url": "https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/extend-study-permit.html",
        # Verified live (2026-09-27): the page's own Français toggle link.
        "url_fr": "https://www.canada.ca/fr/immigration-refugies-citoyennete/services/etudier-canada/prolongation-permis-etudes.html",
        "description": (
            "Official IRCC guidance on extending a study permit, including what "
            "to do while an application is being processed."
        ),
        "description_fr": (
            "Renseignements officiels d'IRCC sur la prolongation d'un permis "
            "d'études, y compris quoi faire pendant qu'une demande est en "
            "traitement."
        ),
        "topic": "study permit",
    },
    {
        "organization": "Immigration, Refugees and Citizenship Canada",
        "title": "Check application processing times",
        "title_fr": "Vérifier les délais de traitement des demandes",
        "url": "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/check-processing-times.html",
        # Verified live (2026-09-27): the page's own Français toggle link.
        "url_fr": "https://www.canada.ca/fr/immigration-refugies-citoyennete/services/demande/verifier-delais-traitement.html",
        "description": "Official current processing times by application type.",
        "description_fr": "Délais de traitement actuels officiels par type de demande.",
        "topic": "processing times",
    },
    {
        "organization": "Immigration, Refugees and Citizenship Canada",
        "title": "Contact IRCC",
        "title_fr": "Communiquer avec IRCC",
        "url": "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/contact-ircc.html",
        # Verified live (2026-09-27): the page's own Français toggle link.
        "url_fr": "https://www.canada.ca/fr/immigration-refugies-citoyennete/organisation/contactez-ircc.html",
        "description": (
            "Official contact channels, including the client support centre and "
            "web form for case-specific enquiries."
        ),
        "description_fr": (
            "Moyens de contact officiels, y compris le centre de soutien à la "
            "clientèle et le formulaire Web pour les demandes propres à un cas."
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
        "title_fr": "Faire une demande de numéro d'assurance sociale",
        "url": "https://www.canada.ca/en/employment-social-development/services/sin.html",
        # Verified live (2026-09-27): the page's own Français toggle link.
        "url_fr": "https://www.canada.ca/fr/emploi-developpement-social/services/numero-assurance-sociale.html",
        "description": "Official process for obtaining or updating a SIN.",
        "description_fr": "Processus officiel pour obtenir ou mettre à jour un NAS.",
        "topic": "sin",
    },
    {
        "organization": "Government of Ontario",
        "title": "Apply for OHIP health coverage",
        "title_fr": "Faire une demande de couverture santé de l'OHIP",
        "url": "https://www.ontario.ca/page/apply-ohip-and-get-health-card",
        # Verified live (2026-09-27): the page's own Français toggle link.
        "url_fr": "https://www.ontario.ca/fr/page/sinscrire-lassurance-sante-de-lontario-et-obtenir-une-carte-sante",
        "description": "Official eligibility and application steps for Ontario health coverage.",
        "description_fr": "Admissibilité officielle et étapes de demande pour la couverture santé de l'Ontario.",
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
                "description_fr": entry.get("description_fr", ""),
                "official_url": entry["official_url"],
                "official_url_fr": entry.get("official_url_fr", ""),
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
                "title_fr": entry.get("title_fr", ""),
                "description": entry["description"],
                "description_fr": entry.get("description_fr", ""),
                "url_fr": entry.get("url_fr", ""),
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
