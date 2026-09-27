from django.core.management.base import BaseCommand

from apps.directory.seed import seed_directory


class Command(BaseCommand):
    help = "Idempotently seed the approved official organization and source registry."

    def handle(self, *args, **options):
        seed_directory(stdout=self.stdout)
