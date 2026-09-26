"""
Deploy-time safety checks (CLAUDE.md §29, §31).

These run under `manage.py check --deploy` rather than at import time, so they
catch a misconfigured production deployment without interfering with the test
suite (which Django always runs with DEBUG=False).
"""
from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def dev_auth_must_be_disabled_in_production(app_configs, **kwargs):
    """The development identity shim must never ship enabled."""
    if getattr(settings, "DEV_AUTH_ENABLED", False) and not settings.DEBUG:
        return [
            Error(
                "DEV_AUTH_ENABLED is on while DEBUG is off. This would "
                "authenticate every request as the shared demo user.",
                hint="Set DEV_AUTH_ENABLED=false and configure real authentication.",
                id="civic.E001",
            )
        ]
    return []


@register(Tags.security, deploy=True)
def secret_key_must_be_changed(app_configs, **kwargs):
    if "dev-only-insecure-key" in settings.SECRET_KEY:
        return [
            Error(
                "DJANGO_SECRET_KEY is still the development default.",
                hint="Set DJANGO_SECRET_KEY in the environment.",
                id="civic.E002",
            )
        ]
    return []


@register(Tags.security, deploy=True)
def cors_must_not_be_open(app_configs, **kwargs):
    if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False):
        return [
            Error(
                "CORS_ALLOW_ALL_ORIGINS is enabled.",
                hint="Set CORS_ALLOWED_ORIGINS explicitly instead.",
                id="civic.E003",
            )
        ]
    return []
