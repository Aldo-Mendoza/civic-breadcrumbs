"""
Explicit serializers (CLAUDE.md §39).

No ``fields = "__all__"`` anywhere: every field crossing the API is named
deliberately, so adding a column to a model never silently widens what leaves the
server.

Separate serializers per use case keep the contract readable enough for the
frontend to work from without reading models.
"""
from rest_framework import serializers

from apps.journeys import enums
from apps.journeys.models import Breadcrumb, Journey


class OrganizationSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    short_name = serializers.CharField(read_only=True)
    jurisdiction = serializers.CharField(read_only=True)
    official_url = serializers.URLField(read_only=True)


class BreadcrumbDetailSerializer(serializers.ModelSerializer):
    """
    A saved breadcrumb.

    ``raw_text`` and the structured reading are both exposed, separately, so the
    interface can show the citizen their own words next to our interpretation of
    them (§10).
    """

    organization = OrganizationSummarySerializer(read_only=True)
    reported_status = serializers.CharField(read_only=True)
    instruction = serializers.CharField(read_only=True)
    suggested_next_action = serializers.CharField(read_only=True)
    counts_as_evidence = serializers.BooleanField(read_only=True)

    class Meta:
        model = Breadcrumb
        fields = [
            "id",
            "kind",
            "channel",
            "title",
            "raw_text",
            "organization_name",
            "organization",
            "occurred_at",
            "source_type",
            "structured_data",
            "reported_status",
            "instruction",
            "suggested_next_action",
            "is_confirmed",
            "counts_as_evidence",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class StalenessSerializer(serializers.Serializer):
    """A proactive nudge about the citizen's own recording gap, never a
    government timeline claim (CLAUDE.md §4.2)."""

    is_stale = serializers.BooleanField()
    days_since_last_recorded = serializers.IntegerField(allow_null=True)
    last_recorded_at = serializers.DateTimeField(allow_null=True)
    message = serializers.CharField(allow_blank=True)


class StateChangeSerializer(serializers.Serializer):
    """What a create/correct/delete actually did to the journey."""

    changed = serializers.BooleanField()
    status_changed = serializers.BooleanField()
    next_action_changed = serializers.BooleanField()
    message = serializers.CharField(allow_blank=True)


class JourneyStateSerializer(serializers.Serializer):
    """The "you left off here" payload (§19)."""

    status = serializers.CharField()
    current_state = serializers.CharField()
    next_action = serializers.CharField()
    next_action_code = serializers.CharField()
    unresolved_issue = serializers.CharField()
    latest_reported_status = serializers.CharField()
    latest_instruction = serializers.CharField(allow_blank=True)
    last_event = serializers.DictField(required=False)
    source = serializers.DictField(required=False)
    staleness = StalenessSerializer(required=False)


class JourneyListSerializer(serializers.ModelSerializer):
    breadcrumb_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Journey
        fields = [
            "id",
            "title",
            "goal",
            "status",
            "current_state",
            "next_action",
            "next_action_code",
            "breadcrumb_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class JourneyDetailSerializer(serializers.ModelSerializer):
    primary_organization = OrganizationSummarySerializer(read_only=True)
    breadcrumbs = BreadcrumbDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Journey
        fields = [
            "id",
            "title",
            "goal",
            "status",
            "current_state",
            "next_action",
            "next_action_code",
            "primary_organization",
            "breadcrumbs",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class JourneyCreateSerializer(serializers.Serializer):
    """
    Create a journey, either from structured fields or from a description.

    Supplying ``description`` alone triggers at most one interpretation call to
    propose a title and goal; supplying ``title`` skips AI entirely (§17).
    """

    title = serializers.CharField(required=False, allow_blank=True, max_length=200)
    goal = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=4000
    )
    organization_name = serializers.CharField(
        required=False, allow_blank=True, max_length=200
    )

    def validate(self, attrs):
        if not (attrs.get("title") or attrs.get("description") or attrs.get("goal")):
            raise serializers.ValidationError(
                "Tell us what you are trying to get done."
            )
        return attrs


class JourneyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Journey
        fields = ["title", "goal", "status"]
        extra_kwargs = {
            "title": {"required": False},
            "goal": {"required": False},
            "status": {"required": False},
        }


class InterpretRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000)


class BreadcrumbDraftSerializer(serializers.Serializer):
    """The reviewable draft returned by the interpret endpoint (§24)."""

    kind = serializers.ChoiceField(choices=enums.BreadcrumbKind.choices)
    channel = serializers.ChoiceField(choices=enums.Channel.choices)
    title = serializers.CharField(allow_blank=True)
    organization = serializers.CharField(allow_blank=True)
    occurred_on = serializers.DateField(allow_null=True)
    reported_status = serializers.ChoiceField(choices=enums.ReportedStatus.choices)
    instruction = serializers.CharField(allow_blank=True)
    suggested_next_action = serializers.ChoiceField(
        choices=enums.NextActionCode.choices
    )
    reference = serializers.CharField(allow_blank=True)
    confidence = serializers.FloatField()
    needs_clarification = serializers.BooleanField()
    clarification_question = serializers.CharField(allow_null=True)
    paraphrase = serializers.CharField(allow_blank=True)
    extractor = serializers.CharField()


class BreadcrumbCreateSerializer(serializers.Serializer):
    """
    Confirmed evidence. This is the only path that writes to the journey.

    Every field is explicit because the citizen may have corrected any of them
    during review; we save what they confirmed, not what was extracted.
    """

    kind = serializers.ChoiceField(choices=enums.BreadcrumbKind.choices)
    channel = serializers.ChoiceField(
        choices=enums.Channel.choices, required=False, default=enums.Channel.UNKNOWN
    )
    title = serializers.CharField(max_length=300)
    raw_text = serializers.CharField(
        required=False, allow_blank=True, max_length=4000
    )
    organization_name = serializers.CharField(
        required=False, allow_blank=True, max_length=200
    )
    occurred_at = serializers.DateTimeField(required=False)
    occurred_on = serializers.DateField(required=False)
    source_type = serializers.ChoiceField(
        choices=[
            (enums.SourceType.USER_REPORTED, "User reported"),
            (enums.SourceType.OFFICIAL, "Official"),
            (enums.SourceType.COMMUNITY, "Community"),
        ],
        required=False,
        default=enums.SourceType.USER_REPORTED,
    )
    reported_status = serializers.ChoiceField(
        choices=enums.ReportedStatus.choices,
        required=False,
        default=enums.ReportedStatus.UNKNOWN,
    )
    instruction = serializers.CharField(
        required=False, allow_blank=True, max_length=500
    )
    suggested_next_action = serializers.ChoiceField(
        choices=enums.NextActionCode.choices,
        required=False,
        default=enums.NextActionCode.NONE,
    )
    reference = serializers.CharField(required=False, allow_blank=True, max_length=64)
    request_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    confidence = serializers.FloatField(required=False, min_value=0.0, max_value=1.0)
    extractor = serializers.CharField(required=False, allow_blank=True, max_length=32)

    def validate_source_type(self, value):
        # AI output can never be submitted as evidence (§14 Rule 2). The choice
        # list already excludes it; this is the belt-and-braces check.
        if value == enums.SourceType.AI_INTERPRETATION:
            raise serializers.ValidationError(
                "Generated content cannot be saved as evidence."
            )
        return value


class BreadcrumbUpdateSerializer(BreadcrumbCreateSerializer):
    """A correction. Every field optional; raw_text is never editable (§10)."""

    kind = serializers.ChoiceField(choices=enums.BreadcrumbKind.choices, required=False)
    title = serializers.CharField(max_length=300, required=False)
    raw_text = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("raw_text", None)
        self.fields.pop("request_id", None)


class SaveAsNoteSerializer(serializers.Serializer):
    """The fallback when interpretation is not possible (§28)."""

    text = serializers.CharField(max_length=4000)
    request_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
