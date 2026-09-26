"""
HTTP orchestration (CLAUDE.md §7).

Views do four things: authorize, validate, call a service, shape a response. The
rules about what the product may claim live in the domain modules, not here.

Every handler documents its AI cost against the §17 budget. The GET endpoints are
all zero-call, which is why the demo stays fast and keeps working when a model is
unavailable.
"""
import logging

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.directory.selectors import (
    official_sources_for,
    resolve_responsible_organization,
)
from apps.journeys import enums, feedback, selectors, services
from apps.journeys.handoff import build_handoff
from apps.journeys.state import compute_staleness, derive_journey_state
from apps.journeys.stuck import build_stuck_summary
from common.exceptions import SuggestedAction
from common.throttling import AI_THROTTLES
from services.ai.factory import get_gateway
from services.ai.intent import classify_intent, out_of_scope_response
from services.ai.rules import RuleBasedAIService

from .serializers import (
    BreadcrumbCreateSerializer,
    BreadcrumbDetailSerializer,
    BreadcrumbDraftSerializer,
    BreadcrumbUpdateSerializer,
    GuideSerializer,
    GuideStepSerializer,
    InterpretRequestSerializer,
    JourneyCreateSerializer,
    JourneyDetailSerializer,
    JourneyListSerializer,
    JourneyStateSerializer,
    JourneyUpdateSerializer,
    OrganizationSummarySerializer,
    SaveAsNoteSerializer,
)

logger = logging.getLogger("civic.api")


def _state_payload(state, breadcrumbs=None, now=None):
    """
    The §19 "you left off here" contract.

    Provenance travels with the answer so the interface can always show where a
    claim came from, rather than presenting derived text as fact. Staleness
    rides along here too -- a proactive nudge about the citizen's own recording
    gap, never a government-timeline claim (§4.2).
    """
    payload = state.as_dict()
    payload["last_event"] = {
        "date": state.evidence_occurred_at,
        "summary": state.evidence_summary,
    }
    payload["source"] = {
        "type": state.evidence_source_type,
        "breadcrumb_id": state.evidence_breadcrumb_id,
    }
    payload["evidence_count"] = state.considered_count
    payload["references"] = list(state.references)

    staleness = compute_staleness(state.status, breadcrumbs, now or timezone.now())
    payload["staleness"] = {
        "is_stale": staleness.is_stale,
        "days_since_last_recorded": staleness.days_since_last_recorded,
        "last_recorded_at": staleness.last_recorded_at,
        "message": staleness.message,
    }
    return payload


def _change_payload(change):
    """What a create/correct/delete actually did (§9.1's cache, described)."""
    return {
        "changed": change.changed,
        "status_changed": change.status_changed,
        "next_action_changed": change.next_action_changed,
        "message": change.message,
    }


class JourneyListCreateView(APIView):
    """GET: 0 AI calls. POST: at most 1 (§17)."""

    throttle_classes = AI_THROTTLES

    def get_throttles(self):
        """
        Only creation can reach a model, so only creation spends AI quota.

        Without this, listing journeys would burn the same budget as
        interpretation and a citizen who refreshed a few times would be locked
        out of recording anything (§17, §26).
        """
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return []
        # A prose description is the explicit guide-generation action. Purely
        # structured clients get a deterministic guide and spend no model call.
        if not self.request.data.get("description"):
            return []
        return super().get_throttles()

    @extend_schema(responses=JourneyListSerializer(many=True))
    def get(self, request):
        journeys = selectors.list_journeys(request.user)
        data = []
        for journey in journeys:
            payload = JourneyListSerializer(journey).data
            payload["breadcrumb_count"] = journey.breadcrumbs.count()
            data.append(payload)
        return Response({"results": data})

    @extend_schema(
        request=JourneyCreateSerializer, responses=JourneyDetailSerializer
    )
    def post(self, request):
        serializer = JourneyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        title = payload.get("title", "").strip()
        goal = payload.get("goal", "").strip()
        description = payload.get("description", "").strip()
        degraded = False
        extractor = "none"
        draft = None

        # At most one model call proposes the intent and guide together.
        if description:
            if classify_intent(description) == enums.Intent.OUT_OF_SCOPE:
                return Response(out_of_scope_response())
            gateway = get_gateway(str(request.user.pk))
            draft, degraded = gateway.extract_journey(description)
            title = title or draft.title
            goal = goal or draft.goal
            extractor = draft.extractor
        else:
            draft = RuleBasedAIService().extract_journey(
                " ".join(part for part in (title, goal) if part)
            )
            extractor = "none"

        journey, state = services.create_journey(
            user=request.user,
            title=title or description[:60] or "My journey",
            goal=goal or description,
            organization_name=(
                payload.get("organization_name", "")
                or getattr(draft, "organization", "")
            ),
            guide_draft=draft,
        )

        body = JourneyDetailSerializer(journey).data
        body["state"] = _state_payload(state)
        body["ai"] = {"degraded": degraded, "extractor": extractor}
        return Response(body, status=http_status.HTTP_201_CREATED)


class JourneyDetailView(APIView):
    """0 AI calls."""

    @extend_schema(responses=JourneyDetailSerializer)
    def get(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        breadcrumbs = list(selectors.get_breadcrumbs(journey))
        state = derive_journey_state(journey, breadcrumbs)

        body = JourneyDetailSerializer(journey).data
        body["state"] = _state_payload(state, breadcrumbs, timezone.now())
        body["timeline"] = selectors.build_timeline(breadcrumbs)
        return Response(body)

    @extend_schema(request=JourneyUpdateSerializer, responses=JourneyDetailSerializer)
    def patch(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        serializer = JourneyUpdateSerializer(journey, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # A manual status change is respected, but the derived fields are
        # refreshed so the two can never disagree (§9.1).
        state = services.recalculate_journey_state(journey)
        breadcrumbs = list(selectors.evidence_breadcrumbs(journey))
        body = JourneyDetailSerializer(journey).data
        body["state"] = _state_payload(state, breadcrumbs, timezone.now())
        return Response(body)


class JourneyGuideView(APIView):
    """Read the saved suggested plan. This always costs zero AI calls."""

    @extend_schema(responses=GuideSerializer)
    def get(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        return Response(GuideSerializer(journey.guide).data)


class GuideStepCompleteView(APIView):
    """Explicit user confirmation: complete one step and create audit evidence."""

    @extend_schema(responses=GuideStepSerializer)
    def post(self, request, guide_step_id):
        step = selectors.get_owned_guide_step(request.user, guide_step_id)
        step, breadcrumb, created = services.complete_guide_step(step)
        body = GuideStepSerializer(step).data
        body["created"] = created
        body["breadcrumb_id"] = str(breadcrumb.id)
        return Response(
            body,
            status=http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK,
        )


class BreadcrumbInterpretView(APIView):
    """
    Propose a structured reading. At most 1 AI call, and persists nothing.

    This separation is the trust model (§24): interpretation is disposable, only
    confirmation writes to the journey.
    """

    throttle_classes = AI_THROTTLES

    @extend_schema(
        request=InterpretRequestSerializer, responses=BreadcrumbDraftSerializer
    )
    def post(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        serializer = InterpretRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data["text"].strip()

        # The gate runs first, so unrelated input and injection attempts never
        # reach a prompt and never cost quota (§15, §16).
        intent = classify_intent(text)
        if intent == enums.Intent.OUT_OF_SCOPE:
            body = out_of_scope_response()
            body["raw_text"] = text
            return Response(body)

        breadcrumbs = list(selectors.evidence_breadcrumbs(journey))
        state = derive_journey_state(journey, breadcrumbs)
        context = selectors.build_minimal_context(
            journey, state, today=timezone.localdate()
        )

        gateway = get_gateway(str(request.user.pk))
        draft, degraded = gateway.extract_breadcrumb(text, context)

        return Response(
            {
                "raw_text": text,
                "intent": intent,
                "draft": BreadcrumbDraftSerializer(draft.model_dump()).data,
                "needs_clarification": draft.needs_clarification,
                "clarification_question": draft.clarification_question,
                "ai": {
                    "degraded": degraded,
                    "extractor": draft.extractor,
                    "calls": gateway.calls,
                },
                # Always offered, so an unusable draft is never a dead end (§28).
                "fallback_action": SuggestedAction.SAVE_AS_NOTE,
            }
        )


class BreadcrumbListCreateView(APIView):
    """0 AI calls. POST here is the only write path for evidence."""

    @extend_schema(responses=BreadcrumbDetailSerializer(many=True))
    def get(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        breadcrumbs = selectors.get_breadcrumbs(journey)
        return Response(
            {
                "results": BreadcrumbDetailSerializer(breadcrumbs, many=True).data,
                "timeline": selectors.build_timeline(breadcrumbs),
            }
        )

    @extend_schema(
        request=BreadcrumbCreateSerializer, responses=BreadcrumbDetailSerializer
    )
    def post(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        serializer = BreadcrumbCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        occurred_at = data.get("occurred_at")
        if occurred_at is None and data.get("occurred_on"):
            occurred_at = timezone.make_aware(
                timezone.datetime.combine(
                    data["occurred_on"], timezone.datetime.min.time()
                )
            )

        # Snapshot "where things stood" immediately before the write, so the
        # response can say what actually changed as a result (closes the loop
        # -- zero AI calls, just describing the §9.1 cache's diff).
        before_state = derive_journey_state(
            journey, list(selectors.evidence_breadcrumbs(journey))
        )

        guide_step = None
        if data.get("guide_step_id"):
            guide_step = selectors.get_owned_guide_step(
                request.user, data["guide_step_id"]
            )
            if guide_step.guide.journey_id != journey.id:
                from django.http import Http404

                raise Http404("Guide step not found.")

        breadcrumb, created, warnings = services.add_breadcrumb(
            journey,
            kind=data["kind"],
            channel=data.get("channel", enums.Channel.UNKNOWN),
            title=data["title"],
            raw_text=data.get("raw_text", ""),
            organization_name=data.get("organization_name", ""),
            occurred_at=occurred_at,
            source_type=data.get("source_type", enums.SourceType.USER_REPORTED),
            structured_data={
                "reported_status": data.get(
                    "reported_status", enums.ReportedStatus.UNKNOWN
                ),
                "instruction": data.get("instruction", ""),
                "suggested_next_action": data.get(
                    "suggested_next_action", enums.NextActionCode.NONE
                ),
                "reference": data.get("reference", ""),
                "confidence": data.get("confidence"),
                "extractor": data.get("extractor", ""),
            },
            request_id=data.get("request_id") or None,
            guide_step=guide_step,
        )

        after_breadcrumbs = list(selectors.evidence_breadcrumbs(journey))
        state = derive_journey_state(journey, after_breadcrumbs)
        change = feedback.describe_change(before_state, state, verb="recorded this")

        body = BreadcrumbDetailSerializer(breadcrumb).data
        body["created"] = created
        body["warnings"] = warnings
        body["state"] = _state_payload(state, after_breadcrumbs, timezone.now())
        body["change"] = _change_payload(change)
        return Response(
            body,
            status=(
                http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK
            ),
        )


class BreadcrumbDetailView(APIView):
    """0 AI calls. Both handlers trigger state recalculation."""

    @extend_schema(
        request=BreadcrumbUpdateSerializer, responses=BreadcrumbDetailSerializer
    )
    def patch(self, request, breadcrumb_id):
        breadcrumb = selectors.get_owned_breadcrumb(request.user, breadcrumb_id)
        serializer = BreadcrumbUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        structured = {
            key: data[key]
            for key in (
                "reported_status",
                "instruction",
                "suggested_next_action",
                "reference",
            )
            if key in data
        }

        occurred_at = data.get("occurred_at")
        if occurred_at is None and data.get("occurred_on"):
            occurred_at = timezone.make_aware(
                timezone.datetime.combine(
                    data["occurred_on"], timezone.datetime.min.time()
                )
            )

        journey = breadcrumb.journey
        before_state = derive_journey_state(
            journey, list(selectors.evidence_breadcrumbs(journey))
        )

        breadcrumb, state = services.update_breadcrumb(
            breadcrumb,
            kind=data.get("kind"),
            channel=data.get("channel"),
            title=data.get("title"),
            organization_name=data.get("organization_name"),
            occurred_at=occurred_at,
            source_type=data.get("source_type"),
            structured_data=structured or None,
        )

        after_breadcrumbs = list(selectors.evidence_breadcrumbs(journey))
        change = feedback.describe_change(before_state, state, verb="corrected this")

        body = BreadcrumbDetailSerializer(breadcrumb).data
        body["state"] = _state_payload(state, after_breadcrumbs, timezone.now())
        body["change"] = _change_payload(change)
        return Response(body)

    def delete(self, request, breadcrumb_id):
        breadcrumb = selectors.get_owned_breadcrumb(request.user, breadcrumb_id)
        journey = breadcrumb.journey
        before_state = derive_journey_state(
            journey, list(selectors.evidence_breadcrumbs(journey))
        )

        state = services.delete_breadcrumb(breadcrumb)

        after_breadcrumbs = list(selectors.evidence_breadcrumbs(journey))
        change = feedback.describe_change(
            before_state, state, verb="deleted that", ack="Removed"
        )
        return Response(
            {
                "deleted": True,
                "state": _state_payload(state, after_breadcrumbs, timezone.now()),
                "change": _change_payload(change),
            }
        )


class JourneyStateView(APIView):
    """
    "You left off here" -- 0 AI calls (§19).

    The hero feature needs no model at all, because the backend already holds
    structured data. That is the whole argument of the project in one endpoint.
    """

    @extend_schema(responses=JourneyStateSerializer)
    def get(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        breadcrumbs = list(selectors.evidence_breadcrumbs(journey))
        state = derive_journey_state(journey, breadcrumbs)
        return Response(_state_payload(state, breadcrumbs, timezone.now()))


class JourneyStuckView(APIView):
    """
    "I am stuck" -- 0 AI calls by default, at most 1 if wording polish is
    explicitly requested, and only ever to reword (§20).

    Every factual field is built deterministically before the model is asked
    anything, so a degraded or absent model changes the prose and nothing
    else. Rewording an already-complete deterministic summary is not natural-
    language interpretation of new citizen input, so it stays opt-in rather
    than automatic -- this is "current state display" in substance, and that
    is meant to cost nothing.
    """

    throttle_classes = AI_THROTTLES

    def get_throttles(self):
        """Only spend AI-route throttle budget when polish is actually
        requested; a plain status check must not compete with interpretation
        for the same budget."""
        if not self._polish_requested(self.request):
            return []
        return super().get_throttles()

    @staticmethod
    def _polish_requested(request):
        return request.query_params.get("polish", "false").lower() == "true"

    def get(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        breadcrumbs = list(selectors.evidence_breadcrumbs(journey))
        state = derive_journey_state(journey, breadcrumbs)

        organization_result = resolve_responsible_organization(
            journey, state, breadcrumbs
        )
        organization = organization_result.get("responsible_organization")
        sources = official_sources_for(journey, organization)

        body = build_stuck_summary(
            journey, breadcrumbs, state, organization_result, sources
        )

        degraded = False
        polish = self._polish_requested(request)
        if polish and breadcrumbs:
            snapshot = selectors.build_ai_snapshot(
                journey, state, breadcrumbs, body["summary"]
            )
            gateway = get_gateway(str(request.user.pk))
            prose, degraded = gateway.summarize_stuck_state(snapshot)
            if prose.summary:
                body["summary"] = prose.summary
            body["ai"] = {
                "degraded": degraded,
                "extractor": prose.extractor,
                "calls": gateway.calls,
                # Named explicitly so the UI can label generated prose and keep
                # it visually distinct from recorded evidence (§4.1).
                "summary_is_generated": prose.extractor != "rules",
            }
        else:
            body["ai"] = {
                "degraded": False,
                "extractor": "rules",
                "calls": 0,
                "summary_is_generated": False,
            }

        return Response(body)


class ResponsibleOrganizationView(APIView):
    """"Who handles this?" -- 0 AI calls (§21)."""

    def get(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        breadcrumbs = list(selectors.evidence_breadcrumbs(journey))
        state = derive_journey_state(journey, breadcrumbs)
        result = resolve_responsible_organization(journey, state, breadcrumbs)

        organization = result.get("responsible_organization")
        return Response(
            {
                "responsible_organization": (
                    OrganizationSummarySerializer(organization).data
                    if organization is not None
                    else None
                ),
                "source": "CURATED_DIRECTORY" if organization is not None else None,
                "basis": result.get("basis"),
                "message": result.get("message", ""),
                "action_needed": result.get("action_needed", False),
                "official_sources": [
                    {
                        "id": str(source.id),
                        "title": source.title,
                        "url": source.url,
                        "verified_at": source.verified_at,
                    }
                    for source in official_sources_for(journey, organization)
                ],
            }
        )


class OfficialSourcesView(APIView):
    """0 AI calls. Curated links only (§9.5)."""

    def get(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        sources = official_sources_for(journey, limit=10)
        return Response(
            {
                "results": [
                    {
                        "id": str(source.id),
                        "title": source.title,
                        "url": source.url,
                        "description": source.description,
                        "topic": source.topic,
                        "organization": {
                            "name": source.organization.name,
                            "short_name": source.organization.short_name,
                        },
                        "source_type": enums.SourceType.OFFICIAL,
                        "verified_at": source.verified_at,
                    }
                    for source in sources
                ]
            }
        )


class HandoffView(APIView):
    """
    "Hand me off" -- at most 1 AI call, and persists nothing (§22).

    POST rather than GET because it may reach a model, but it is deliberately
    not a create: storing generated prose would risk it being mistaken later for
    something the citizen was actually told (§33 Case G).
    """

    throttle_classes = AI_THROTTLES

    def get_throttles(self):
        if str(self.request.data.get("polish", "false")).lower() != "true":
            return []
        return super().get_throttles()

    def post(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        breadcrumbs = list(selectors.evidence_breadcrumbs(journey))
        state = derive_journey_state(journey, breadcrumbs)

        organization_result = resolve_responsible_organization(
            journey, state, breadcrumbs
        )
        body = build_handoff(
            journey,
            breadcrumbs,
            state,
            organization_result.get("responsible_organization"),
        )

        degraded = False
        polish = str(request.data.get("polish", "false")).lower() == "true"
        if polish and breadcrumbs:
            snapshot = selectors.build_ai_snapshot(
                journey, state, breadcrumbs, body["summary"]
            )
            gateway = get_gateway(str(request.user.pk))
            prose, degraded = gateway.generate_handoff(snapshot)
            if prose.summary:
                body["summary"] = prose.summary
            body["ai"] = {
                "degraded": degraded,
                "extractor": prose.extractor,
                "calls": gateway.calls,
                "summary_is_generated": prose.extractor != "rules",
            }
        else:
            body["ai"] = {
                "degraded": False,
                "extractor": "rules",
                "calls": 0,
                "summary_is_generated": False,
            }

        body["persisted"] = False
        return Response(body)


class SaveAsNoteView(APIView):
    """
    The fallback path -- 0 AI calls (§28).

    Exists so that a model outage, an unreadable response, or wording we cannot
    parse never costs the citizen their record.
    """

    def post(self, request, journey_id):
        journey = selectors.get_owned_journey(request.user, journey_id)
        serializer = SaveAsNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        before_state = derive_journey_state(
            journey, list(selectors.evidence_breadcrumbs(journey))
        )

        guide_step = None
        guide_step_id = serializer.validated_data.get("guide_step_id")
        if guide_step_id:
            guide_step = selectors.get_owned_guide_step(request.user, guide_step_id)
            if guide_step.guide.journey_id != journey.id:
                from django.http import Http404

                raise Http404("Guide step not found.")

        breadcrumb, created, warnings = services.save_draft_as_note(
            journey,
            serializer.validated_data["text"],
            request_id=serializer.validated_data.get("request_id") or None,
            guide_step=guide_step,
        )
        after_breadcrumbs = list(selectors.evidence_breadcrumbs(journey))
        state = derive_journey_state(journey, after_breadcrumbs)
        change = feedback.describe_change(
            before_state, state, verb="saved that note"
        )

        body = BreadcrumbDetailSerializer(breadcrumb).data
        body["created"] = created
        body["warnings"] = warnings
        body["state"] = _state_payload(state, after_breadcrumbs, timezone.now())
        body["change"] = _change_payload(change)
        return Response(
            body,
            status=(
                http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK
            ),
        )
