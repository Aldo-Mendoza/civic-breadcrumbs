"""Minimal admin, useful for inspecting seeded data during the build."""
from django.contrib import admin

from .models import Breadcrumb, Journey


class BreadcrumbInline(admin.TabularInline):
    model = Breadcrumb
    extra = 0
    fields = ("occurred_at", "kind", "channel", "title", "source_type", "is_confirmed")
    readonly_fields = ("occurred_at",)


@admin.register(Journey)
class JourneyAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "status", "next_action_code", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "goal")
    inlines = [BreadcrumbInline]


@admin.register(Breadcrumb)
class BreadcrumbAdmin(admin.ModelAdmin):
    list_display = ("title", "journey", "kind", "channel", "occurred_at", "source_type")
    list_filter = ("kind", "channel", "source_type", "is_confirmed")
    search_fields = ("title", "raw_text", "organization_name")
