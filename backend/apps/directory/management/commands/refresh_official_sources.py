from django.core.management.base import BaseCommand, CommandError

from apps.directory.grounding import refresh_source
from apps.directory.models import OfficialSource


class Command(BaseCommand):
    help = "Refresh registered official pages without discovering the open web."

    def add_arguments(self, parser):
        parser.add_argument("--source", help="Refresh one OfficialSource UUID")
        parser.add_argument(
            "--accept-changes",
            action="store_true",
            help="Activate changed content after review; otherwise changes are quarantined.",
        )

    def handle(self, *args, **options):
        queryset = OfficialSource.objects.filter(active=True)
        if options["source"]:
            queryset = queryset.filter(pk=options["source"])
        if not queryset.exists():
            raise CommandError("No matching active official source was found.")

        failures = 0
        for source in queryset:
            try:
                result = refresh_source(
                    source, accept_changes=options["accept_changes"]
                )
                self.stdout.write(f"{source.title}: {result}")
            except Exception as exc:
                failures += 1
                self.stderr.write(f"{source.title}: failed ({exc})")
        if failures:
            raise CommandError(f"{failures} official source(s) failed to refresh.")
