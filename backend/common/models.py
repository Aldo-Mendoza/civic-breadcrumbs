"""Server-owned identities for Auth0 accounts and short-lived guests."""
from django.conf import settings
from django.db import models


class AuthIdentity(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_identity"
    )
    issuer = models.URLField(max_length=255)
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["issuer", "subject"], name="unique_auth0_identity"
            )
        ]


class GuestSession(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="guest_session"
    )
    expires_at = models.DateTimeField(db_index=True)
    migrated_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="migrated_guest_sessions",
    )
    migrated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_expired(self):
        from django.utils import timezone

        return self.expires_at <= timezone.now()


class AIUsageBucket(models.Model):
    """Cross-worker counters for per-identity and global Gemini protection."""
    scope = models.CharField(max_length=32)
    identity = models.CharField(max_length=160)
    window_started_at = models.DateTimeField()
    window_ends_at = models.DateTimeField(db_index=True)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "identity", "window_started_at"],
                name="unique_ai_usage_bucket",
            )
        ]
