"""
Base settings shared by every environment.

Configuration comes from environment variables (CLAUDE.md §37) so that the same
image can run against SQLite locally and PostgreSQL in production without code
changes.
"""
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv
import os
import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "dev-only-insecure-key-change-in-production"
)
DEBUG = env_bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "common",
    "apps.journeys",
    "apps.directory",
    "demo",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database
#
# DATABASE_URL indirection keeps the domain code identical across SQLite (fast
# local start) and the PostgreSQL 15 instance the spec calls for (CLAUDE.md §6).
# Migrations use only portable field types (UUIDField, JSONField) so switching
# engines needs no migration changes.
# ---------------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.parse(
        # `or` (not just .get's default) because .env commonly ships
        # DATABASE_URL= with no value -- that sets the key to "", which
        # .get() treats as present and would otherwise skip the fallback.
        os.environ.get("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-ca"
TIME_ZONE = "America/Toronto"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Swapping in Auth0 later (CLAUDE.md §31) is a one-line change here.
        "common.auth.DevUserAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Only AI-backed routes opt into the "ai" scope (CLAUDE.md §26).
    "DEFAULT_THROTTLE_RATES": {
        "ai": os.environ.get("AI_RATE_LIMIT", "10/min"),
    },
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Civic Breadcrumbs API",
    "DESCRIPTION": (
        "A citizen-owned memory layer for navigating fragmented public services. "
        "Government shouldn't make you start over."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CACHES = {
    # LocMemCache is enough for throttling; Redis is explicitly out of scope (§42).
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "civic-breadcrumbs",
    }
}

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)

# ---------------------------------------------------------------------------
# AI gateway (CLAUDE.md §12, §37)
#
# AI_ENABLED=false, or an absent key, selects the deterministic rule-based
# extractor. Every product action works in that mode.
# ---------------------------------------------------------------------------

# `manage.py test` must never depend on what happens to be in a developer's
# local .env (CLAUDE.md §32: "Never require live Gemini calls in the normal
# automated test suite"). Detecting the test runner directly, rather than
# trusting AI_ENABLED alone, means a real key sitting in .env can never make
# the suite flaky, slow, or dependent on network/quota -- regardless of who
# runs it or what they've configured locally.
RUNNING_TESTS = "test" in sys.argv or "pytest" in sys.modules

AI_ENABLED = False if RUNNING_TESTS else env_bool("AI_ENABLED", default=True)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
AI_TIMEOUT_SECONDS = float(os.environ.get("AI_TIMEOUT_SECONDS", "8"))

# A second, explicit gate on top of RUNNING_TESTS. RUNNING_TESTS protects the
# normal test suite automatically and needs no developer action; this flag
# protects the deliberately-live tools (`manage.py verify_gemini`,
# `manage.py eval_gemini`) from being run *by accident* -- e.g. copy-pasted by
# a teammate who doesn't realize the command spends real quota. Both refuse to
# proceed unless this is explicitly true. Defaults to false.
AI_LIVE_TESTS = env_bool("AI_LIVE_TESTS", default=False)

# Development identity. Never enabled when DEBUG is off (enforced in auth.py).
DEV_AUTH_ENABLED = env_bool("DEV_AUTH_ENABLED", default=True)
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "demo@civicbreadcrumbs.local")

# Bounded text limits (CLAUDE.md §29).
MAX_RAW_TEXT_LENGTH = int(os.environ.get("MAX_RAW_TEXT_LENGTH", "4000"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{levelname}] {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "civic": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
