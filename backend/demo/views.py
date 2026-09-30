"""
The fallback demo interface.

Served by Django with no build step so the core flow is demonstrable even if the
separate React client is unavailable. Deliberately unopinionated about layout;
the real frontend owns presentation (CLAUDE.md §43).
"""
from django.conf import settings
from django.views.generic import TemplateView


class DemoView(TemplateView):
    template_name = "demo/index.html"


class PrivacyView(TemplateView):
    template_name = "demo/privacy.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["privacy_contact_email"] = settings.PRIVACY_CONTACT_EMAIL
        return context
