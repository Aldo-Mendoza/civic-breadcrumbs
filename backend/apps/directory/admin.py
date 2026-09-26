"""Minimal admin for the curated directory."""
from django.contrib import admin

from .models import OfficialSource, Organization


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
    list_display = ("title", "organization", "topic", "active", "verified_at")
    list_filter = ("active", "organization")
