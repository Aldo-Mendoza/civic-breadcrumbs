"""Local development settings."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver", "[::1]"]

# Origins remain explicit even in development; add another local origin through
# CORS_ALLOWED_ORIGINS rather than silently trusting every website.
CORS_ALLOW_ALL_ORIGINS = False
