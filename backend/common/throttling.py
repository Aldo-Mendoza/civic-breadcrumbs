"""Database-backed per-minute, daily, and application-wide AI limits."""
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from common.auth import is_guest_user
from common.models import AIUsageBucket


def _reserve(scope, identity, limit, duration):
    now = timezone.now()
    epoch = int(now.timestamp())
    started_epoch = epoch - (epoch % duration)
    started = datetime.fromtimestamp(started_epoch, tz=datetime_timezone.utc)
    ends = started + timedelta(seconds=duration)

    for _ in range(2):
        try:
            with transaction.atomic():
                bucket, _ = AIUsageBucket.objects.select_for_update().get_or_create(
                    scope=scope,
                    identity=identity,
                    window_started_at=started,
                    defaults={"window_ends_at": ends},
                )
                if bucket.count >= limit:
                    return False, max(1, int((ends - now).total_seconds()))
                bucket.count += 1
                bucket.save(update_fields=["count"])
                return True, 0
        except IntegrityError:
            # Two workers created the same bucket simultaneously; retry and
            # lock the winner instead of allowing both actions through.
            continue
    return False, max(1, int((ends - now).total_seconds()))


class _DatabaseAIThrottle(SimpleRateThrottle):
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
        allowed, self._wait_seconds = _reserve(
            self.scope, self.bucket_identity(request), self.num_requests, self.duration
        )
        return allowed

    def bucket_identity(self, request):
        return self.identity(request)

    def wait(self):
        return getattr(self, "_wait_seconds", 1)

    def get_cache_key(self, request, view):  # pragma: no cover - not cache-backed
        return None


class AIThrottle(_DatabaseAIThrottle):
    scope = "ai_minute"

    def configure(self, request):
        amount = (
            settings.GUEST_AI_REQUESTS_PER_MINUTE
            if is_guest_user(getattr(request, "user", None))
            else settings.USER_AI_REQUESTS_PER_MINUTE
        )
        return f"{amount}/min"


class AIDailyThrottle(_DatabaseAIThrottle):
    scope = "ai_daily"

    def configure(self, request):
        amount = (
            settings.GUEST_AI_DAILY_LIMIT
            if is_guest_user(getattr(request, "user", None))
            else settings.USER_AI_DAILY_LIMIT
        )
        return f"{amount}/day"


class GlobalAIThrottle(_DatabaseAIThrottle):
    scope = "ai_global_daily"

    def configure(self, request):
        return f"{settings.GLOBAL_AI_DAILY_LIMIT}/day"

    def bucket_identity(self, request):
        return "application"


AI_THROTTLES = [AIThrottle, AIDailyThrottle, GlobalAIThrottle]
