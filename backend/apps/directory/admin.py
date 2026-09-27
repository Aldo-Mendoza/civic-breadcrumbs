"""Minimal admin for the curated directory."""
from django.contrib import admin

from .models import OfficialSource, OfficialSourceRevision, OfficialSourceSection, Organization


class OfficialSourceInline(admin.TabularInline):
    model = OfficialSource
    extra = 0
    fields = ("title", "url", "topic", "active", "verified_at")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name", "jurisdiction")
    list_filter = ("jurisdiction",)
    search_fields = ("name", "short_name")
    inlines = [OfficialSourceInline]


@admin.register(OfficialSource)
class OfficialSourceAdmin(admin.ModelAdmin):
    list_display = (
        "title", "organization", "topic", "refresh_status", "last_checked_at",
        "active", "verified_at",
    )
    list_filter = ("active", "refresh_status", "organization")


@admin.register(OfficialSourceSection)
class OfficialSourceSectionAdmin(admin.ModelAdmin):
    list_display = ("heading", "source", "position", "active", "retrieved_at")
    list_filter = ("active", "source__organization")
    search_fields = ("heading", "heading_path", "text")


@admin.register(OfficialSourceRevision)
class OfficialSourceRevisionAdmin(admin.ModelAdmin):
    list_display = ("source", "retrieved_at", "accepted", "content_hash")
    list_filter = ("accepted", "source__organization")
    readonly_fields = (
        "source", "retrieved_at", "final_url", "content_hash", "page_title",
        "sections", "accepted", "accepted_at",
    )
