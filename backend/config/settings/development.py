"""Local development settings."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver", "[::1]"]

# Convenience during the hackathon: allow any local frontend port.
CORS_ALLOW_ALL_ORIGINS = True
