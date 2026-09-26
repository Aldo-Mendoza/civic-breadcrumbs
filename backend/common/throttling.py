"""
Rate limiting for AI-backed routes (CLAUDE.md §26).

Applied only where a request can reach a model, so browsing a journey is never
rate limited. The goals are to stop accidental loops, absorb button spam, and
protect a shared API quota.

Implemented as a SimpleRateThrottle with a fixed scope rather than DRF's
ScopedRateThrottle, which silently does nothing unless every view also declares a
throttle_scope attribute -- a failure mode that looks like working code.
"""
from rest_framework.throttling import SimpleRateThrottle


class AIThrottle(SimpleRateThrottle):
    """Per-user limit on routes that may call a model."""

    scope = "ai"

    def get_cache_key(self, request, view):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            ident = str(user.pk)
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
