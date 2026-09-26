"""Independent per-minute, daily, and application-wide AI action limits."""
from django.conf import settings
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from common.auth import is_guest_user


class _DynamicAIThrottle(SimpleRateThrottle):
    def identity(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return str(user.pk)
        return self.get_ident(request)

    def configure(self, request):
        raise NotImplementedError

    def allow_request(self, request, view):
        self.rate = self.configure(request)
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)


class AIThrottle(_DynamicAIThrottle):
    """Low guest and bounded account per-minute limits."""

    scope = "ai_minute"

    def configure(self, request):
        amount = (
            settings.GUEST_AI_REQUESTS_PER_MINUTE
            if is_guest_user(getattr(request, "user", None))
            else settings.USER_AI_REQUESTS_PER_MINUTE
        )
        return f"{amount}/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.identity(request)}


class AIDailyThrottle(_DynamicAIThrottle):
    """Daily allowance independent from the number of Journeys."""

    scope = "ai_daily"

    def configure(self, request):
        amount = (
            settings.GUEST_AI_DAILY_LIMIT
            if is_guest_user(getattr(request, "user", None))
            else settings.USER_AI_DAILY_LIMIT
        )
        return f"{amount}/day"

    def get_cache_key(self, request, view):
        day = timezone.localdate().isoformat()
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{self.identity(request)}:{day}",
        }


class GlobalAIThrottle(_DynamicAIThrottle):
    """Project-wide circuit breaker so one account cannot consume all quota."""

    scope = "ai_global_daily"

    def configure(self, request):
        return f"{settings.GLOBAL_AI_DAILY_LIMIT}/day"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": timezone.localdate().isoformat(),
        }


AI_THROTTLES = [AIThrottle, AIDailyThrottle, GlobalAIThrottle]
