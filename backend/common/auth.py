"""Auth0 bearer authentication and server-owned guest sessions."""
import hashlib
import uuid
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, CSRFCheck, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from .models import AuthIdentity, GuestSession

_GUEST_SESSION_KEY = "civic_guest_user_id"


@lru_cache(maxsize=4)
def _jwks_client(issuer):
    import jwt

    return jwt.PyJWKClient(issuer + ".well-known/jwks.json", cache_keys=True)


def is_guest_user(user) -> bool:
    return bool(user and hasattr(user, "guest_session"))


def purge_expired_guests(limit=25):
    """Bounded lazy cleanup; deleting internal users cascades their Journeys."""
    user_ids = list(
        GuestSession.objects.filter(expires_at__lte=timezone.now())
        .order_by("expires_at")
        .values_list("user_id", flat=True)[:limit]
    )
    if user_ids:
        get_user_model().objects.filter(pk__in=user_ids).delete()


def guest_user_from_session(request, include_migrated=False):
    """Return the unexpired guest attached to this opaque Django session."""
    user_id = request.session.get(_GUEST_SESSION_KEY)
    if not user_id:
        return None
    try:
        guest = GuestSession.objects.select_related("user").get(user_id=user_id)
    except (GuestSession.DoesNotExist, ValueError, TypeError):
        request.session.pop(_GUEST_SESSION_KEY, None)
        return None
    if guest.is_expired:
        guest.user.delete()
        request.session.pop(_GUEST_SESSION_KEY, None)
        return None
    if guest.migrated_to_id and not include_migrated:
        request.session.pop(_GUEST_SESSION_KEY, None)
        return None
    return guest.user


class Auth0JWTAuthentication(BaseAuthentication):
    """Validate Auth0 API access tokens; never accept a client-supplied user id."""

    keyword = b"bearer"

    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if parts[0].lower() != self.keyword or len(parts) != 2:
            raise AuthenticationFailed("Use a Bearer access token.")
        if not settings.AUTH0_ISSUER or not settings.AUTH0_AUDIENCE:
            raise AuthenticationFailed("Auth0 is not configured.")

        try:
            import jwt

            token = parts[1].decode("ascii")
            signing_key = _jwks_client(settings.AUTH0_ISSUER).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(settings.AUTH0_ALGORITHMS),
                audience=settings.AUTH0_AUDIENCE,
                issuer=settings.AUTH0_ISSUER,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
        except Exception as exc:
            raise AuthenticationFailed("The access token is invalid or expired.") from exc

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthenticationFailed("The access token has no subject.")
        user = self._resolve_user(settings.AUTH0_ISSUER, subject, claims)
        return user, {"kind": "auth0", "claims": claims}

    @staticmethod
    def _resolve_user(issuer, subject, claims):
        try:
            return AuthIdentity.objects.select_related("user").get(
                issuer=issuer, subject=subject
            ).user
        except AuthIdentity.DoesNotExist:
            pass

        digest = hashlib.sha256(f"{issuer}\0{subject}".encode()).hexdigest()
        user_model = get_user_model()
        with transaction.atomic():
            identity = (
                AuthIdentity.objects.select_for_update()
                .select_related("user")
                .filter(issuer=issuer, subject=subject)
                .first()
            )
            if identity:
                return identity.user
            user = user_model(username=f"auth0_{digest}"[:150])
            email = claims.get("email")
            if isinstance(email, str):
                user.email = email[:254]
            user.set_unusable_password()
            user.save()
            AuthIdentity.objects.create(user=user, issuer=issuer, subject=subject)
            return user


class GuestSessionAuthentication(BaseAuthentication):
    """Create/resolve one internal guest user from an opaque session cookie."""

    def authenticate(self, request):
        purge_expired_guests()
        user = guest_user_from_session(request)
        if user is None:
            user_model = get_user_model()
            with transaction.atomic():
                user = user_model(username=f"guest_{uuid.uuid4().hex}")
                user.set_unusable_password()
                user.save()
                GuestSession.objects.create(
                    user=user,
                    expires_at=timezone.now()
                    + timedelta(seconds=settings.GUEST_SESSION_TTL_SECONDS),
                )
            request.session[_GUEST_SESSION_KEY] = user.pk
            request.session.set_expiry(settings.GUEST_SESSION_TTL_SECONDS)
        self._enforce_csrf(request)
        return user, {"kind": "guest"}

    @staticmethod
    def _enforce_csrf(request):
        check = CSRFCheck(lambda req: None)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise PermissionDenied(f"CSRF validation failed: {reason}")


class DevUserAuthentication(BaseAuthentication):
    """Optional fixed identity for legacy tests and explicitly enabled demos."""

    def authenticate(self, request):
        if not getattr(settings, "DEV_AUTH_ENABLED", False):
            return None
        user_model = get_user_model()
        email = settings.DEV_USER_EMAIL
        user, created = user_model.objects.get_or_create(
            username=email, defaults={"email": email}
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user, {"kind": "development"}
