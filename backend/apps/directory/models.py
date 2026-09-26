"""
Curated directory of public institutions and their official sources.

Deliberately small (CLAUDE.md §9.4): this is not an attempt at a universal
public-sector directory. It exists so that the responsible organization for a
next step resolves through *known application data* rather than being invented
by a language model (§21).
"""
import uuid

from django.core.validators import URLValidator
from django.db import models


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

    Seeded, never scraped: uncontrolled live web browsing is out of scope (§9.5).
    ``verified_at`` is surfaced to the citizen so they can judge freshness
    themselves rather than trusting us implicitly.
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
    verified_at = models.DateTimeField(
        help_text="When a human last confirmed this link was correct."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["organization__name", "title"]

    def __str__(self) -> str:
        return self.title
