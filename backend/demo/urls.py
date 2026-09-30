"""Demo interface routes."""
from django.urls import path
from django.views.generic import RedirectView

from .views import DemoView, PrivacyView

urlpatterns = [
    path("", RedirectView.as_view(url="/demo/", permanent=False)),
    path("demo/", DemoView.as_view(), name="demo"),
    path("privacy/", PrivacyView.as_view(), name="privacy"),
]
