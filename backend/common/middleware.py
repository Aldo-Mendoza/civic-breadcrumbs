"""Keep private responses out of caches and constrain the citizen UI."""
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.cache import add_never_cache_headers, patch_vary_headers


class PrivacyHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            add_never_cache_headers(response)
            patch_vary_headers(response, ("Authorization", "Cookie"))
        if request.path in {"/", "/demo/", "/privacy/", "/terms/"}:
            add_never_cache_headers(response)
            domain = settings.AUTH0_DOMAIN
            parsed = urlsplit("https://" + domain)
            # Configuration must never become additional header directives.
            origin = (
                "https://" + domain
                if domain and parsed.hostname == domain and not any(
                    char in domain for char in "; \r\n\t"
                )
                else ""
            )
            response["Content-Security-Policy"] = "; ".join((
                "default-src 'self'", "base-uri 'self'", "object-src 'none'",
                "frame-ancestors 'none'", "script-src 'self'", "style-src 'self'",
                "img-src 'self' data:", "font-src 'self'",
                "connect-src 'self'" + (" " + origin if origin else ""),
                "frame-src " + (origin or "'none'"),
                "form-action 'self'" + (" " + origin if origin else ""),
            ))
            response["Referrer-Policy"] = "no-referrer"
            response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
