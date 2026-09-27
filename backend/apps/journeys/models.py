"""
The Journey domain (CLAUDE.md §9).

Two structural commitments here carry the whole product:

1. ``Breadcrumb.raw_text`` is never overwritten by an interpretation. The
   citizen's own words and the structured reading of them stay separately
   identifiable, which is what makes correction, audit and re-processing
   possible (§10).
2. ``Journey.current_state`` / ``next_action`` are a denormalized cache,
   recalculated from confirmed evidence whenever breadcrumbs change. They are
   never an independent source of truth (§9.1).

Privacy by construction (§30): there is no field here for a SIN, date of birth,
passport number, address or financial detail. A reference number is optional and
free-text so the citizen decides what, if anything, to record.
"""
import uuid

from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models

from apps.directory.models import Organization

from . import enums


class Journey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="journeys"
    )
    title = models.CharField(max_length=200)
    goal = models.TextField(max_length=1000)
    status = models.CharField(
        max_length=20,
        choices=enums.JourneyStatus.choices,
        default=enums.JourneyStatus.ACTIVE,
    )
    #: Derived cache -- see apps.journeys.state.derive_journey_state.
    current_state = models.TextField(blank=True)
    next_action = models.TextField(blank=True)
    next_action_code = models.CharField(
        max_length=32,
        choices=enums.NextActionCode.choices,
        default=enums.NextActionCode.NONE,
    )
    primary_organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="journeys",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["user", "-updated_at"])]

    def __str__(self) -> str:
        return self.title


class Guide(models.Model):
    """A suggested plan for a Journey, never evidence about what happened."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    journey = models.OneToOneField(
        Journey, on_delete=models.CASCADE, related_name="guide"
    )
    summary = models.TextField(max_length=1000, blank=True)
    generated_by = models.CharField(max_length=32, default="rules")
    needs_clarification = models.BooleanField(default=False)
    clarification_question = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Guide for {self.journey.title}"


class GuideStep(models.Model):
    """One ordered suggestion. Progress changes only through user action."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guide = models.ForeignKey(Guide, on_delete=models.CASCADE, related_name="steps")
    position = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(max_length=700, blank=True)
    status = models.CharField(
        max_length=20,
        choices=enums.GuideStepStatus.choices,
        default=enums.GuideStepStatus.NOT_STARTED,
    )
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guide_steps",
    )
    official_source = models.ForeignKey(
        "directory.OfficialSource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guide_steps",
    )
    official_source_section = models.ForeignKey(
        "directory.OfficialSourceSection",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guide_steps",
    )
    # Immutable citation snapshot: refreshing a page must not rewrite the
    # historical guidance the citizen actually saw.
    citation_heading = models.CharField(max_length=300, blank=True)
    citation_excerpt = models.TextField(max_length=1200, blank=True)
    citation_url = models.URLField(max_length=800, blank=True)
    citation_retrieved_at = models.DateTimeField(null=True, blank=True)
    completion_breadcrumb = models.OneToOneField(
        "Breadcrumb",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_guide_step",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["guide", "position"], name="unique_guide_step_position"
            )
        ]

    def __str__(self) -> str:
        return f"{self.position}. {self.title}"


class Breadcrumb(models.Model):
    """A piece of evidence that moves a citizen's journey forward."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    journey = models.ForeignKey(
        Journey, on_delete=models.CASCADE, related_name="breadcrumbs"
    )
    guide_step = models.ForeignKey(
        GuideStep,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="breadcrumbs",
    )
    kind = models.CharField(max_length=20, choices=enums.BreadcrumbKind.choices)
    channel = models.CharField(
        max_length=20, choices=enums.Channel.choices, default=enums.Channel.UNKNOWN
    )
    #: The citizen's original wording. Preserved verbatim, forever (§10).
    raw_text = models.TextField(
        blank=True, validators=[MaxLengthValidator(settings.MAX_RAW_TEXT_LENGTH)]
    )
    title = models.CharField(max_length=300)
    organization_name = models.CharField(max_length=200, blank=True)
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="breadcrumbs",
    )
    occurred_at = models.DateTimeField()
    source_type = models.CharField(
        max_length=20,
        choices=enums.SourceType.choices,
        default=enums.SourceType.USER_REPORTED,
    )
    #: reported_status, instruction, suggested_next_action, reference,
    #: confidence, extractor, ai_draft. See services.ai.schemas.
    structured_data = models.JSONField(default=dict, blank=True)
    #: False only for drafts that were explicitly parked; confirmed evidence is
    #: the sole input to state derivation (§24).
    is_confirmed = models.BooleanField(default=True)
    #: Client-supplied idempotency token (§25).
    request_id = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["occurred_at", "created_at"]
        indexes = [
            models.Index(fields=["journey", "occurred_at"]),
            models.Index(fields=["journey", "is_confirmed"]),
        ]
        constraints = [
            # A retried submit must not create a second breadcrumb (§25).
            models.UniqueConstraint(
                fields=["journey", "request_id"],
                condition=models.Q(request_id__isnull=False),
                name="unique_journey_request_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}: {self.title}"

    # -- convenience accessors over structured_data ------------------------

    @property
    def reported_status(self) -> str:
        return self.structured_data.get("reported_status") or enums.ReportedStatus.UNKNOWN

    @property
    def instruction(self) -> str:
        return self.structured_data.get("instruction") or ""

    @property
    def suggested_next_action(self) -> str:
        return (
            self.structured_data.get("suggested_next_action")
            or enums.NextActionCode.NONE
        )

    @property
    def reference(self) -> str:
        return self.structured_data.get("reference") or ""

    @property
    def organization_display(self) -> str:
        """
        The name to show a person.

        A resolved directory record wins and its short name is preferred, because
        people say "IRCC", not "Immigration, Refugees and Citizenship Canada".
        Unresolved free text falls back to whatever the citizen typed.
        """
        if self.organization_id and self.organization:
            return self.organization.short_name or self.organization.name
        return self.organization_name or ""

    @property
    def counts_as_evidence(self) -> bool:
        """
        Whether this breadcrumb may inform derived state.

        AI-generated content is excluded by design: a summary describes
        evidence, it does not create evidence (§14 Rule 2, test Case G).
        """
        return (
            self.is_confirmed
            and self.source_type != enums.SourceType.AI_INTERPRETATION
        )
