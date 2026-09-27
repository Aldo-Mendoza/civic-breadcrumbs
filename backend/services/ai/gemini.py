"""
Gemini adapter (CLAUDE.md §12, §13, §14).

This is the optional upgrade path, not the engine. It is selected only when a key
is configured, and every method is wrapped so that a timeout, an invalid
response, a quota error or a provider outage degrades to the deterministic
extractor rather than to an error page.

Gemini is treated throughout as a **limited, rate-constrained external
service**, not a normal function call:

* one logical request per call. A single ``extract_breadcrumb`` etc. costs at
  most one low-level HTTP attempt; provider failures degrade immediately.
* **429 (quota/rate-limited) is never retried.** A quota error will not
  resolve itself within this request's lifetime; retrying only spends more of
  an already-exhausted budget for the exact same failure. This was the actual,
  measured cause of a free-tier daily quota being exhausted in minutes during
  development: the previous version of this file retried on *any* exception,
  429 included, immediately and with no delay -- silently doubling the request
  count against a budget that was already gone.
* **503 is not retried either.** One explicit action must never spend two
  provider calls.
* constrained JSON decoding plus Pydantic validation, so unvalidated text never
  reaches the domain (§13);
* minimal context only; the full journey history is never transmitted (§17);
* model output is never fed back into another model call -- see
  ``services.ai.factory.AIGateway`` for the per-action call budget that
  enforces this across the whole gateway, not just within one method here.

This adapter has been exercised against the live API (all four contract
methods, plus the model-catalog check) via ``manage.py verify_gemini`` and the
manual ``manage.py eval_gemini`` suite -- neither of which runs as part of
``manage.py test``, and both of which require ``AI_LIVE_TESTS=true`` to be set
explicitly before they will spend real quota.
"""
import json
import logging

from django.conf import settings

from common.exceptions import AIInvalidOutput, AIUnavailable

from . import prompts
from .schemas import (
    BREADCRUMB_RESPONSE_SCHEMA,
    JOURNEY_RESPONSE_SCHEMA,
    PROSE_RESPONSE_SCHEMA,
    BreadcrumbDraft,
    JourneyDraft,
    ProseSummary,
)

logger = logging.getLogger("civic.ai")

_MAX_ATTEMPTS = 1


class GeminiAIService:
    """Structured extraction backed by the Gemini API."""

    name = "gemini"

    def __init__(self, api_key=None, model=None, timeout=None):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model = model or settings.GEMINI_MODEL
        self._timeout = timeout or settings.AI_TIMEOUT_SECONDS
        self._client = None

    # -- transport ---------------------------------------------------------

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise AIUnavailable("No AI key is configured.")
        try:
            from google import genai
        except ImportError as exc:
            raise AIUnavailable("The AI client library is not installed.") from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _generate(self, prompt, response_schema, operation):
        """
        One model call, treated as a limited external resource rather than an
        ordinary function.

        Three outcomes, handled differently on purpose:

        * a malformed response is never retried -- retrying an invalid shape
          tends to produce another invalid shape, and the deterministic
          extractor is a better use of the next second;
        * a client error (429 included) is never retried -- a quota error
          cannot resolve itself mid-request, and retrying only spends more of
          a budget that is already exhausted;
        * a server error is not retried; the deterministic path is immediately
          available and one action must never spend two provider calls.
        """
        from google.genai import errors as genai_errors

        client = self._get_client()
        last_error = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": response_schema,
                        "temperature": 0.1,
                        "max_output_tokens": 1024,
                        "http_options": {"timeout": int(self._timeout * 1000)},
                    },
                )
                logger.info(
                    "ai_operation=%s provider=gemini attempt=%s status=ok",
                    operation,
                    attempt,
                )
                return self._parse(response)
            except AIInvalidOutput:
                raise
            except genai_errors.ClientError as exc:
                # 4xx, including 429 RESOURCE_EXHAUSTED. Fail fast: retrying a
                # quota error immediately doubles wasted requests against a
                # budget that will not refill within this call's lifetime.
                last_error = exc
                logger.warning(
                    "ai_operation=%s provider=gemini attempt=%s status=client_error code=%s",
                    operation,
                    attempt,
                    getattr(exc, "code", "?"),
                )
                break
            except genai_errors.ServerError as exc:
                # Do not turn one citizen action into multiple provider calls.
                last_error = exc
                logger.warning(
                    "ai_operation=%s provider=gemini attempt=%s status=server_error code=%s",
                    operation,
                    attempt,
                    getattr(exc, "code", "?"),
                )
                break
            except Exception as exc:  # transport/library error, e.g. a DNS blip
                last_error = exc
                logger.warning(
                    "ai_operation=%s provider=gemini attempt=%s status=error error=%s",
                    operation,
                    attempt,
                    type(exc).__name__,
                )
                break

        raise AIUnavailable("The AI service did not respond in time.") from last_error

    def _parse(self, response):
        text = getattr(response, "text", None)
        if not text:
            raise AIInvalidOutput("The AI service returned an empty response.")
        try:
            payload = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise AIInvalidOutput("The AI service returned unreadable output.") from exc
        if not isinstance(payload, dict):
            raise AIInvalidOutput("The AI service returned an unexpected shape.")
        return payload

    # -- contract ----------------------------------------------------------

    def extract_journey(self, user_text, source_context=None):
        payload = self._generate(
            prompts.journey_prompt(user_text, source_context),
            JOURNEY_RESPONSE_SCHEMA,
            "extract_journey",
        )
        try:
            draft = JourneyDraft(**payload)
        except Exception as exc:
            raise AIInvalidOutput("The AI service returned invalid fields.") from exc
        return draft.model_copy(update={"extractor": self.name})

    def extract_breadcrumb(self, user_text, minimal_context):
        payload = self._generate(
            prompts.breadcrumb_prompt(user_text, minimal_context),
            BREADCRUMB_RESPONSE_SCHEMA,
            "extract_breadcrumb",
        )
        # Empty strings are common in constrained decoding; normalise them to
        # None so Pydantic applies the documented defaults (§13).
        for key in ("occurred_on", "clarification_question"):
            if payload.get(key) in ("", "null", "none"):
                payload[key] = None
        try:
            draft = BreadcrumbDraft(**payload)
        except Exception as exc:
            raise AIInvalidOutput("The AI service returned invalid fields.") from exc

        organization = self._restrict_organization(draft.organization, minimal_context)
        return draft.model_copy(
            update={"extractor": self.name, "organization": organization}
        )

    @staticmethod
    def _restrict_organization(candidate, minimal_context):
        """
        Only allow organizations that exist in the curated directory.

        This is the guard against the model naming a plausible-sounding public
        body that does not exist (§21). A name we cannot verify is dropped, and
        the citizen supplies it during review instead.
        """
        if not candidate:
            return ""
        known = (minimal_context or {}).get("known_organizations") or []
        wanted = candidate.strip().lower()
        for entry in known:
            names = [entry.get("name", "")] + list(entry.get("aliases") or [])
            if any(wanted == (name or "").strip().lower() for name in names):
                return entry.get("name", "")
        logger.info("Dropped unverified organization from AI output: %r", candidate)
        return ""

    def summarize_stuck_state(self, journey_snapshot):
        payload = self._generate(
            prompts.stuck_prose_prompt(journey_snapshot),
            PROSE_RESPONSE_SCHEMA,
            "summarize_stuck_state",
        )
        return ProseSummary(
            summary=payload.get("summary", ""), extractor=self.name
        )

    def generate_handoff(self, journey_snapshot):
        payload = self._generate(
            prompts.handoff_prose_prompt(journey_snapshot),
            PROSE_RESPONSE_SCHEMA,
            "generate_handoff",
        )
        return ProseSummary(
            summary=payload.get("summary", ""), extractor=self.name
        )
