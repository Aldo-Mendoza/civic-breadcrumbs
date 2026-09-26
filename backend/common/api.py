"""Public auth configuration/status and the explicit guest migration action."""
from django.conf import settings
from django.middleware.csrf import get_token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied

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
