"""Journey API routes (CLAUDE.md §23)."""
from django.urls import path

from . import views

urlpatterns = [
    path("journeys/", views.JourneyListCreateView.as_view(), name="journey-list"),
    path(
        "journeys/<uuid:journey_id>/",
        views.JourneyDetailView.as_view(),
        name="journey-detail",
    ),
    path(
        "journeys/<uuid:journey_id>/guide/",
        views.JourneyGuideView.as_view(),
        name="journey-guide",
    ),
    path(
        "guide-steps/<uuid:guide_step_id>/complete/",
        views.GuideStepCompleteView.as_view(),
        name="guide-step-complete",
    ),
    path(
        "journeys/<uuid:journey_id>/breadcrumbs/interpret/",
        views.BreadcrumbInterpretView.as_view(),
        name="breadcrumb-interpret",
    ),
    path(
        "journeys/<uuid:journey_id>/breadcrumbs/",
        views.BreadcrumbListCreateView.as_view(),
        name="breadcrumb-list",
    ),
    path(
        "journeys/<uuid:journey_id>/notes/",
        views.SaveAsNoteView.as_view(),
        name="breadcrumb-save-note",
    ),
    path(
        "breadcrumbs/<uuid:breadcrumb_id>/",
        views.BreadcrumbDetailView.as_view(),
        name="breadcrumb-detail",
    ),
    path(
        "journeys/<uuid:journey_id>/state/",
        views.JourneyStateView.as_view(),
        name="journey-state",
    ),
    path(
        "journeys/<uuid:journey_id>/stuck/",
        views.JourneyStuckView.as_view(),
        name="journey-stuck",
    ),
    path(
        "journeys/<uuid:journey_id>/responsible-organization/",
        views.ResponsibleOrganizationView.as_view(),
        name="journey-responsible-organization",
    ),
    path(
        "journeys/<uuid:journey_id>/official-sources/",
        views.OfficialSourcesView.as_view(),
        name="journey-official-sources",
    ),
    path(
        "journeys/<uuid:journey_id>/handoff/",
        views.HandoffView.as_view(),
        name="journey-handoff",
    ),
]
