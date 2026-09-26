"""
Production settings.

DEBUG is forced off and the development identity shim is refused outright
(CLAUDE.md §29, §31).
"""
from .base import *  # noqa: F401,F403

DEBUG = False
DEV_AUTH_ENABLED = False

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
}

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
CORS_ALLOW_ALL_ORIGINS = False
