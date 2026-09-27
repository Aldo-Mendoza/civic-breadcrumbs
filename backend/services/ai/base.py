"""
The AI service boundary (CLAUDE.md §12).

Exactly one interface sits between the application and any language model. Two
implementations satisfy it:

* ``RuleBasedAIService`` -- deterministic, offline, no dependencies. This is the
  default and it is a real implementation, not a stub.
* ``GeminiAIService`` -- used only when a key is configured, and it falls back to
  the rule-based service on any failure.

Because the interface is narrow and the fallback is a peer rather than an error
path, the product keeps working with no network, no key and no quota. For the
people this is built for -- newcomers on prepaid data, a public library
terminal, a service centre with patchy wifi -- that is the difference between a
tool and a demo.
"""
from typing import Protocol

from .schemas import BreadcrumbDraft, JourneyDraft, ProseSummary


class AIService(Protocol):
    """Every AI-touching capability the product has. Nothing else calls a model."""

    #: Identifier recorded on persisted breadcrumbs for provenance.
    name: str

    def extract_journey(self, user_text: str, source_context: list | None = None) -> JourneyDraft:
        """Propose a journey title and goal from a free-text description."""
        ...

    def classify_organization(self, user_text: str, known_organizations: list) -> str:
        """Name the single best-matching curated organization, or "" if unsure."""
        ...

    def extract_breadcrumb(
        self, user_text: str, minimal_context: dict
    ) -> BreadcrumbDraft:
        """Propose a structured reading of something that happened."""
        ...

    def summarize_stuck_state(self, journey_snapshot: dict) -> ProseSummary:
        """Rephrase an already-built factual summary more clearly."""
        ...

    def generate_handoff(self, journey_snapshot: dict) -> ProseSummary:
        """Rephrase an already-built handoff summary more clearly."""
        ...
