"""Directory API routes."""
from django.urls import path

from . import views

urlpatterns = [
    path(
        "organizations/",
        views.OrganizationListView.as_view(),
        name="organization-list",
    ),
]
