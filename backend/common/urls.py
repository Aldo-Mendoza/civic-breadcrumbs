from django.urls import path

from .api import AuthConfigView, AuthStatusView, CSRFView, GuestMigrationView

urlpatterns = [
    path("auth/config/", AuthConfigView.as_view(), name="auth-config"),
    path("auth/csrf/", CSRFView.as_view(), name="auth-csrf"),
    path("auth/status/", AuthStatusView.as_view(), name="auth-status"),
    path("auth/migrate-guest/", GuestMigrationView.as_view(), name="auth-migrate-guest"),
]
