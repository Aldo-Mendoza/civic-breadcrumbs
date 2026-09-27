"""
Curated directory of public institutions and their official sources.

Deliberately small (CLAUDE.md §9.4): this is not an attempt at a universal
public-sector directory. It exists so that the responsible organization for a
next step resolves through *known application data* rather than being invented
by a language model (§21).
"""
import uuid
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

#: The only hostnames a curated official link may point to: Government of
#: Canada (federal) and Government of Ontario (provincial). This is a
#: structural guarantee, not a policy statement -- a link that fails this
#: check cannot be saved as an OfficialSource, regardless of how it got there
#: (seed data, admin panel, or any future authoring path). Municipal and
#: institutional organizations (e.g. City of Ottawa, a university) can still
#: be named as the *responsible organization* for a journey (§21 allows that),
#: they simply never get an attached official-source link under this rule.
GOVERNMENT_DOMAIN_SUFFIXES = (
    "canada.ca",
    "gc.ca",
    "ontario.ca",
    "gov.on.ca",
)


def is_government_domain(url):
    """Whether a URL's hostname is (or is a subdomain of) an allowed
    federal or provincial government domain."""
    host = (urlparse(url or "").hostname or "").lower()
    return any(host == suffix or host.endswith("." + suffix) for suffix in GOVERNMENT_DOMAIN_SUFFIXES)


class Jurisdiction(models.TextChoices):
    FEDERAL = "FEDERAL", "Federal"
    PROVINCIAL = "PROVINCIAL", "Provincial"
    MUNICIPAL = "MUNICIPAL", "Municipal"
    INSTITUTIONAL = "INSTITUTIONAL", "Institutional"
    COMMUNITY = "COMMUNITY", "Community"


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    short_name = models.CharField(max_length=40, blank=True)
    jurisdiction = models.CharField(
        max_length=20, choices=Jurisdiction.choices, default=Jurisdiction.FEDERAL
    )
    description = models.TextField(blank=True)
    official_url = models.URLField(max_length=500, validators=[URLValidator()])
    #: Lowercase aliases used for deterministic organization matching.
    aliases = models.JSONField(default=list, blank=True)
    #: Lowercase topic keywords that route a journey to this organization (§21).
    topic_keywords = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.short_name or self.name


class OfficialSource(models.Model):
    """
    A curated link to authoritative public information (CLAUDE.md §9.5).

    Seeded and optionally refreshed through a restricted server-side pipeline;
    URLs are never discovered by a model or fetched during a citizen request.
    ``verified_at`` is surfaced so the citizen can judge human verification.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="official_sources"
    )
    title = models.CharField(max_length=300)
    url = models.URLField(max_length=500, validators=[URLValidator()])
    description = models.TextField(blank=True)
    topic = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
    final_url = models.URLField(max_length=500, blank=True)
    etag = models.CharField(max_length=300, blank=True)
    last_modified = models.CharField(max_length=300, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    refresh_status = models.CharField(
        max_length=20,
        choices=(
            ("VERIFIED", "Verified"),
            ("CHANGED", "Changed - review required"),
            ("BROKEN", "Broken"),
        ),
        default="VERIFIED",
    )
    refresh_error = models.CharField(max_length=500, blank=True)
    refresh_interval_hours = models.PositiveIntegerField(default=168)
    verified_at = models.DateTimeField(
        help_text="When a human last confirmed this link was correct."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["organization__name", "title"]

    def __str__(self) -> str:
        return self.title

    def clean(self):
        """
        Enforce the government-domain rule at the model layer, so it can never
        be bypassed by a future write path (admin panel, a new seed entry, an
        eventual authoring endpoint) that forgets to check it explicitly.
        """
        super().clean()
        if self.url and not is_government_domain(self.url):
            raise ValidationError(
                {
                    "url": (
                        "Official sources may only link to Government of "
                        "Canada (canada.ca / gc.ca) or Government of Ontario "
                        "(ontario.ca / gov.on.ca) domains. Never invent or "
                        "link an unofficial source (§21)."
                    )
                }
            )
        if self.organization_id and self.organization.jurisdiction not in (
            Jurisdiction.FEDERAL,
            Jurisdiction.PROVINCIAL,
        ):
            raise ValidationError(
                {
                    "organization": (
                        "Official sources may only be attached to a federal "
                        "or provincial organization. A municipal or "
                        "institutional organization can still be named as "
                        "the responsible organization for a journey (§21) -- "
                        "it just cannot carry an official-source link."
                    )
                }
            )


class OfficialSourceSection(models.Model):
    """A precise, retrievable passage from an approved official page."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(
        OfficialSource, on_delete=models.CASCADE, related_name="sections"
    )
    heading = models.CharField(max_length=300)
    heading_path = models.CharField(max_length=700, blank=True)
    anchor = models.CharField(max_length=300, blank=True)
    text = models.TextField(max_length=12000)
    position = models.PositiveIntegerField(default=1)
    content_hash = models.CharField(max_length=64)
    active = models.BooleanField(default=True)
    retrieved_at = models.DateTimeField()

    class Meta:
        ordering = ["source", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "position"], name="unique_source_section_position"
            )
        ]

    @property
    def deep_link(self):
        base = self.source.final_url or self.source.url
        return f"{base}#{self.anchor}" if self.anchor else base

    def __str__(self):
        return f"{self.source.title} — {self.heading}"


class OfficialSourceRevision(models.Model):
    """Immutable fetch history used to audit and review official-page changes."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(
        OfficialSource, on_delete=models.CASCADE, related_name="revisions"
    )
    retrieved_at = models.DateTimeField(auto_now_add=True)
    final_url = models.URLField(max_length=500)
    content_hash = models.CharField(max_length=64)
    page_title = models.CharField(max_length=300, blank=True)
    sections = models.JSONField(default=list)
    accepted = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-retrieved_at"]
