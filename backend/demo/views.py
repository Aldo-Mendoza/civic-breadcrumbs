"""
The fallback demo interface.

Served by Django with no build step so the core flow is demonstrable even if the
separate React client is unavailable. Deliberately unopinionated about layout;
the real frontend owns presentation (CLAUDE.md §43).
"""
from django.views.generic import TemplateView


class DemoView(TemplateView):
    template_name = "demo/index.html"
