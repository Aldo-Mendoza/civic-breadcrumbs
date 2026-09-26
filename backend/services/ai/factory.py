"""
AI gateway construction and the no-chaining guarantee (CLAUDE.md §12, §14, §17).

``AIGateway`` wraps a primary implementation with the deterministic one and
enforces the feedback-loop protections as runtime invariants rather than
conventions:

* **Rule 1, no autonomous chaining.** One gateway is built per request and
  allows at most one model call. A second attempt raises immediately, so a
  future code path that tried to feed a summary back into the model would fail
  loudly in tests instead of quietly burning quota in production.
* **Rule 3, explicit user action.** A gateway only exists inside a view handling
  a supported action, so every model call is traceable to something the citizen
  chose to do. There are no background loops.

Degradation is reported, never hidden: when the primary fails, the response
carries ``degraded: true`` so the interface can tell the citizen their draft was
organized without AI.
"""
import logging

from django.conf import settings

from common.exceptions import AIUnavailable

from .rules import RuleBasedAIService

logger = logging.getLogger("civic.ai")


def ai_configured():
    """Whether a live model is both enabled and credentialed."""
    return bool(getattr(settings, "AI_ENABLED", False)) and bool(
        getattr(settings, "GEMINI_API_KEY", "")
    )


def build_primary_service():
    """The live service if available, otherwise the deterministic one."""
    if not ai_configured():
        return RuleBasedAIService()
    # Imported lazily so the SDK is never required for the deterministic path.
    from .gemini import GeminiAIService

    return GeminiAIService()


class AICallBudgetExceeded(RuntimeError):
    """Raised when a single user action attempts more than one model call."""


class AIGateway:
    """
    A per-request façade over the AI service contract.

    Every method returns ``(result, degraded)``. ``degraded`` is true when the
    deterministic engine produced the result after a live call failed -- the
    citizen still gets their draft, and the interface can say so plainly.
    """

    def __init__(self, primary=None, fallback=None, max_calls=1):
        self._fallback = fallback or RuleBasedAIService()
        self._primary = primary if primary is not None else build_primary_service()
        self._max_calls = max_calls
        self.calls = 0
        self.provider = getattr(self._primary, "name", "rules")

    @property
    def uses_live_model(self):
        return self._primary is not self._fallback and self.provider != "rules"

    def _spend(self, operation):
        if not self.uses_live_model:
            return False
        if self.calls >= self._max_calls:
            raise AICallBudgetExceeded(
                "One user action may trigger at most {n} AI request(s); "
                "{op} would exceed that.".format(n=self._max_calls, op=operation)
            )
        self.calls += 1
        return True

    def _run(self, operation, *args):
        """Attempt the primary implementation, degrade to deterministic."""
        if not self._spend(operation):
            return getattr(self._fallback, operation)(*args), False
        try:
            return getattr(self._primary, operation)(*args), False
        except AIUnavailable as exc:
            logger.warning(
                "ai_operation=%s status=degraded reason=%s", operation, exc.code
            )
            return getattr(self._fallback, operation)(*args), True
        except Exception:
            # An unexpected SDK error must not cost the citizen their input.
            logger.exception("ai_operation=%s status=degraded reason=unexpected", operation)
            return getattr(self._fallback, operation)(*args), True

    # -- contract ----------------------------------------------------------

    def extract_journey(self, user_text):
        return self._run("extract_journey", user_text)

    def extract_breadcrumb(self, user_text, minimal_context):
        return self._run("extract_breadcrumb", user_text, minimal_context)

    def summarize_stuck_state(self, journey_snapshot):
        return self._run("summarize_stuck_state", journey_snapshot)

    def generate_handoff(self, journey_snapshot):
        return self._run("generate_handoff", journey_snapshot)


def get_gateway():
    """Build the gateway for one user action."""
    return AIGateway()
