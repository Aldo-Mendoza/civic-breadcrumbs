"""Read-only directory endpoints."""
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.directory.models import Organization


class OrganizationListView(APIView):
    """The curated directory. 0 AI calls."""

    def get(self, request):
        organizations = Organization.objects.prefetch_related("official_sources")
        return Response(
            {
                "results": [
                    {
                        "id": str(org.id),
                        "name": org.name,
                        "short_name": org.short_name,
                        "jurisdiction": org.jurisdiction,
                        "description": org.localized_description,
                        "official_url": org.localized_official_url,
                        "source_count": org.official_sources.count(),
                    }
                    for org in organizations
                ]
            }
        )
