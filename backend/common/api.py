"""Public auth configuration/status and the explicit guest migration action."""
from django.conf import settings
from django.middleware.csrf import get_token
from django.utils import translation
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError

from common.auth import guest_user_from_session, is_guest_user
from common.services import migrate_guest_journeys


class AuthConfigView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(
            {
                "enabled": bool(settings.AUTH0_DOMAIN and settings.AUTH0_CLIENT_ID and settings.AUTH0_AUDIENCE),
                "domain": settings.AUTH0_DOMAIN,
                "client_id": settings.AUTH0_CLIENT_ID,
                "audience": settings.AUTH0_AUDIENCE,
            }
        )


class SetLanguageView(APIView):
    """Sets the django_language cookie LocaleMiddleware reads on every later
    request -- the single source of truth the rest of the backend (deterministic
    state/stuck/handoff text, AI prompt language, error messages) keys off via
    django.utils.translation.get_language()."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        language = str(request.data.get("language", "")).strip()
        if language not in dict(settings.LANGUAGES):
            raise ValidationError({"language": "Unsupported language."})
        translation.activate(language)
        response = Response({"language": language})
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            language,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            path=settings.LANGUAGE_COOKIE_PATH,
            domain=settings.LANGUAGE_COOKIE_DOMAIN,
            secure=settings.LANGUAGE_COOKIE_SECURE,
            httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
            samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )
        return response


class CSRFView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"csrf_token": get_token(request)})


class AuthStatusView(APIView):
    def get(self, request):
        guest = is_guest_user(request.user)
        return Response(
            {
                "authenticated": not guest,
                "mode": "guest" if guest else "account",
                "journey_limit": settings.GUEST_MAX_ACTIVE_JOURNEYS if guest else settings.USER_MAX_ACTIVE_JOURNEYS,
                "show_save_prompt": guest and request.user.journeys.exists(),
            }
        )


class GuestMigrationView(APIView):
    def post(self, request):
        if not isinstance(request.auth, dict) or request.auth.get("kind") != "auth0":
            raise PermissionDenied("A validated Auth0 access token is required.")
        guest_user = guest_user_from_session(request, include_migrated=True)
        if guest_user is None:
            return Response(
                {"status": "no_guest_journey", "migrated_count": 0, "idempotent": True}
            )
        return Response(migrate_guest_journeys(guest_user, request.user))
