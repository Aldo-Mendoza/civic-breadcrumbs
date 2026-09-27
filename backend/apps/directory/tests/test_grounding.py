from email.message import Message
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.directory.grounding import (
    SourceRefreshError,
    extract_html_sections,
    refresh_source,
    source_context_for,
)
from apps.directory.models import Organization, OfficialSourceRevision
from apps.directory.seed import seed_directory


class _Response:
    def __init__(self, body, url, *, etag='"v1"'):
        self._body = body.encode()
        self._url = url
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"
        self.headers["ETag"] = etag

    def read(self, amount):
        return self._body[:amount]

    def geturl(self):
        return self._url


class _Opener:
    def __init__(self, response):
        self.response = response

    def open(self, request, timeout):
        return self.response


class _FailingOpener:
    def open(self, request, timeout):
        raise TimeoutError("temporary timeout")


def _html(text="Apply using the official online account."):
    return f"""
        <html><head><title>Study permit extension</title></head><body>
        <nav>Unrelated navigation</nav>
        <h1 id="how-to-apply">How to apply</h1><p>{text}</p>
        <h2 id="documents">Documents</h2><p>Review the document list for your situation.</p>
        </body></html>
    """


class SectionExtractionTests(TestCase):
    def test_extracts_heading_paths_anchors_and_body_not_navigation(self):
        title, sections = extract_html_sections(_html())
        self.assertEqual(title, "Study permit extension")
        self.assertEqual(sections[0]["heading_path"], "How to apply")
        self.assertEqual(sections[0]["anchor"], "how-to-apply")
        self.assertNotIn("navigation", sections[0]["text"])
        self.assertEqual(sections[1]["heading_path"], "How to apply > Documents")


class SourceRefreshTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_directory()

    def setUp(self):
        self.source = Organization.objects.get(short_name="IRCC").official_sources.get(
            topic="study permit"
        )

    def response(self, html, url=None, etag='"v1"'):
        return _Response(html, url or self.source.url, etag=etag)

    def test_initial_refresh_activates_precise_sections_and_revision(self):
        result = refresh_source(self.source, opener=_Opener(self.response(_html())))
        self.assertEqual(result, "initialized")
        self.source.refresh_from_db()
        self.assertEqual(self.source.refresh_status, "VERIFIED")
        self.assertEqual(self.source.sections.count(), 2)
        self.assertEqual(OfficialSourceRevision.objects.get().accepted, True)
        section = self.source.sections.get(position=1)
        self.assertTrue(section.deep_link.endswith("#how-to-apply"))

    def test_changed_content_is_quarantined_until_explicitly_accepted(self):
        refresh_source(self.source, opener=_Opener(self.response(_html(), etag='"old"')))
        self.source.refresh_from_db()
        original_hash = self.source.content_hash
        original_text = self.source.sections.get(position=1).text

        result = refresh_source(
            self.source,
            opener=_Opener(self.response(_html("The official instructions changed."), etag='"new"')),
        )
        self.assertEqual(result, "changed")
        self.source.refresh_from_db()
        self.assertEqual(self.source.refresh_status, "CHANGED")
        self.assertEqual(self.source.content_hash, original_hash)
        self.assertEqual(self.source.etag, '"old"')
        self.assertEqual(self.source.sections.get(position=1).text, original_text)
        self.assertFalse(self.source.revisions.first().accepted)

        result = refresh_source(
            self.source,
            accept_changes=True,
            opener=_Opener(self.response(_html("The official instructions changed."), etag='"new"')),
        )
        self.assertEqual(result, "updated")
        self.source.refresh_from_db()
        self.assertEqual(self.source.refresh_status, "VERIFIED")
        self.assertIn("changed", self.source.sections.get(position=1).text)

    def test_final_redirect_destination_must_still_be_official(self):
        with self.assertRaises(SourceRefreshError):
            refresh_source(
                self.source,
                opener=_Opener(self.response(_html(), url="https://reddit.com/not-official")),
            )
        self.source.refresh_from_db()
        self.assertEqual(self.source.refresh_status, "BROKEN")

    def test_transient_failure_does_not_bless_or_invalidate_cached_content(self):
        self.assertIsNone(self.source.last_checked_at)
        with self.assertRaises(TimeoutError):
            refresh_source(self.source, opener=_FailingOpener())
        self.source.refresh_from_db()
        self.assertEqual(self.source.refresh_status, "VERIFIED")
        self.assertIsNone(self.source.last_checked_at)
        self.assertIn("timeout", self.source.refresh_error)

    def test_only_relevant_verified_sections_enter_model_context(self):
        context = source_context_for(
            "I need to extend my study permit",
            Organization.objects.get(short_name="IRCC"),
        )
        self.assertTrue(context)
        self.assertTrue(all("id" in item and "excerpt" in item for item in context))
        self.assertTrue(all("canada.ca" in item["url"] for item in context))

        self.source.refresh_status = "CHANGED"
        self.source.save(update_fields=["refresh_status"])
        ids = {item["id"] for item in source_context_for(
            "I need to extend my study permit",
            Organization.objects.get(short_name="IRCC"),
        )}
        self.assertNotIn(str(self.source.sections.get().id), ids)

    def test_stale_source_is_not_sent_to_the_model(self):
        self.source.refresh_interval_hours = 1
        self.source.verified_at = timezone.now() - timedelta(hours=2)
        self.source.last_checked_at = None
        self.source.save(
            update_fields=["refresh_interval_hours", "verified_at", "last_checked_at"]
        )
        ids = {item["id"] for item in source_context_for(
            "extend my study permit", self.source.organization
        )}
        self.assertNotIn(str(self.source.sections.get().id), ids)
