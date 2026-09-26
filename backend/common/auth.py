"""
Development identity (CLAUDE.md §31).

Authentication must not block the core journey flow, so development runs against
a single controlled user. Two guarantees make this safe:

* it authenticates nobody unless ``DEV_AUTH_ENABLED`` is set, and the production
  settings module hard-codes that to false;
* it never reads a user id from the request, so a client cannot claim to be
  someone else. Ownership is always enforced against ``request.user``.

The safety net is a deploy check (``common.checks``) that fails
``manage.py check --deploy`` if this is ever enabled alongside ``DEBUG=False``.
That is deliberately a deploy-time check rather than a runtime ``DEBUG`` test:
Django forces ``DEBUG=False`` while running tests, so a runtime check would make
the shim untestable and push the suite towards bypassing authentication
altogether -- which would leave the ownership rules unexercised.

Swapping in Auth0 later means adding a JWT authentication class to
``DEFAULT_AUTHENTICATION_CLASSES``. Nothing in the domain layer changes.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication


class DevUserAuthentication(BaseAuthentication):
    """Resolve every request to a fixed local demo user."""

    def authenticate(self, request):
        if not getattr(settings, "DEV_AUTH_ENABLED", False):
            return None

        user_model = get_user_model()
        email = settings.DEV_USER_EMAIL
        user, created = user_model.objects.get_or_create(
            username=email, defaults={"email": email}
        )
        if created:
            # Not a login route: no usable password is ever set.
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return (user, None)
