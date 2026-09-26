"""Small application services shared by authentication and Journey ownership."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.journeys import enums
from apps.journeys.models import Journey
from common.exceptions import GuestMigrationBlocked
from common.models import GuestSession


def migrate_guest_journeys(guest_user, account_user):
    """Transfer guest data once, or preserve it intact when capacity is full."""
    with transaction.atomic():
        guest = GuestSession.objects.select_for_update().get(user=guest_user)
        list(
            get_user_model().objects.select_for_update().filter(
                pk__in=[guest_user.pk, account_user.pk]
            ).order_by("pk")
        )

        if guest.migrated_to_id:
            return {
                "status": "already_migrated",
                "migrated_count": 0,
                "idempotent": True,
            }

        guest_journeys = Journey.objects.select_for_update().filter(user=guest_user)
        guest_count = guest_journeys.count()
        account_active = Journey.objects.filter(user=account_user).exclude(
            status__in=[enums.JourneyStatus.COMPLETED, enums.JourneyStatus.ARCHIVED]
        ).count()
        guest_active = guest_journeys.exclude(
            status__in=[enums.JourneyStatus.COMPLETED, enums.JourneyStatus.ARCHIVED]
        ).count()
        if account_active + guest_active > settings.USER_MAX_ACTIVE_JOURNEYS:
            raise GuestMigrationBlocked(settings.USER_MAX_ACTIVE_JOURNEYS)

        guest_journeys.update(user=account_user)
        guest.migrated_to = account_user
        guest.migrated_at = timezone.now()
        guest.save(update_fields=["migrated_to", "migrated_at"])
        return {
            "status": "migrated",
            "migrated_count": guest_count,
            "idempotent": True,
        }
