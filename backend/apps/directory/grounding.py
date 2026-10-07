"""Restricted retrieval and section-level grounding for official sources.

This module never discovers or searches the open web.  It only fetches URLs
that already passed ``OfficialSource.full_clean()``, validates the final URL
again after redirects, and turns headings and their nearby text into bounded
passages that can be supplied to the language model.
"""
from __future__ import annotations

import hashlib
import re
from datetime import timedelta
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.utils import timezone

from .models import (
    OfficialSource,
    OfficialSourceRevision,
    OfficialSourceSection,
    is_government_domain,
)

MAX_DOWNLOAD_BYTES = 2_000_000
MAX_SECTION_CHARS = 12_000
USER_AGENT = "CivicBreadcrumbsSourceVerifier/1.0"


class SourceRefreshError(RuntimeError):
    pass


class _RestrictedRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        absolute = urljoin(req.full_url, newurl)
        if not is_government_domain(absolute) or not absolute.startswith("https://"):
            raise SourceRefreshError("Official source redirected outside the approved domains.")
        return super().redirect_request(req, fp, code, msg, headers, absolute)


def _clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


class _SectionParser(HTMLParser):
    """Small dependency-free HTML section extractor, organized by headings."""

    SKIP_TAGS = {"script", "style", "nav", "footer", "noscript", "svg"}
    TEXT_TAGS = {"p", "li", "dd", "dt", "td", "th"}
    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.page_title = ""
        self.sections = []
        self._skip_depth = 0
        self._title_depth = 0
        self._title_parts = []
        self._heading_level = None
        self._heading_parts = []
        self._heading_anchor = ""
        self._heading_stack = {}
        self._current_heading = "Overview"
        self._current_path = "Overview"
        self._current_anchor = ""
        self._current_parts = []
        self._text_depth = 0
        self._text_parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        # Void elements have no matching end tag and cannot change nesting.
        if tag in self.VOID_TAGS:
            if self._text_depth and tag in {"br", "hr"}:
                self._text_parts.append(" ")
            return
        attrs = dict(attrs)
        if tag == "title":
            self._title_depth += 1
        elif tag in {"h1", "h2", "h3", "h4"}:
            self._flush_section()
            self._heading_level = int(tag[1])
            self._heading_parts = []
            self._heading_anchor = attrs.get("id", "")[:300]
        elif tag in self.TEXT_TAGS and not self._text_depth:
            self._text_depth = 1
            self._text_parts = []
        elif self._text_depth:
            self._text_depth += 1

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.VOID_TAGS:
            return
        if self._skip_depth:
            if tag in self.SKIP_TAGS:
                self._skip_depth -= 1
            return
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
            self.page_title = _clean(" ".join(self._title_parts))[:300]
        elif self._heading_level and tag == f"h{self._heading_level}":
            heading = _clean(" ".join(self._heading_parts)) or "Untitled section"
            level = self._heading_level
            self._heading_stack[level] = heading
            for deeper in list(self._heading_stack):
                if deeper > level:
                    self._heading_stack.pop(deeper, None)
            self._current_heading = heading[:300]
            self._current_path = " > ".join(
                self._heading_stack[key] for key in sorted(self._heading_stack)
            )[:700]
            self._current_anchor = self._heading_anchor
            self._heading_level = None
        elif self._text_depth:
            self._text_depth -= 1
            if not self._text_depth:
                text = _clean(" ".join(self._text_parts))
                if text:
                    self._current_parts.append(text)

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._title_depth:
            self._title_parts.append(data)
        if self._heading_level:
            self._heading_parts.append(data)
        elif self._text_depth:
            self._text_parts.append(data)

    def _flush_section(self):
        text = _clean(" ".join(self._current_parts))[:MAX_SECTION_CHARS]
        if text:
            self.sections.append(
                {
                    "heading": self._current_heading,
                    "heading_path": self._current_path,
                    "anchor": self._current_anchor,
                    "text": text,
                }
            )
        self._current_parts = []

    def close(self):
        super().close()
        self._flush_section()


def extract_html_sections(html):
    parser = _SectionParser()
    parser.feed(html)
    parser.close()
    return parser.page_title, parser.sections


def _hash(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def fetch_source(source, opener=None):
    """Fetch one pre-approved URL, with redirect and response-size controls."""
    source.full_clean()
    if not source.url.startswith("https://"):
        raise SourceRefreshError("Official sources must use HTTPS.")
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    if source.etag:
        headers["If-None-Match"] = source.etag
    if source.last_modified:
        headers["If-Modified-Since"] = source.last_modified
    request = Request(source.url, headers=headers)
    opener = opener or build_opener(_RestrictedRedirectHandler())
    try:
        response = opener.open(
            request,
            timeout=getattr(settings, "OFFICIAL_SOURCE_FETCH_TIMEOUT_SECONDS", 30),
        )
    except HTTPError as exc:
        if exc.code == 304:
            return {"not_modified": True}
        raise SourceRefreshError(f"Official page returned HTTP {exc.code}.") from exc
    final_url = response.geturl()
    if not final_url.startswith("https://") or not is_government_domain(final_url):
        raise SourceRefreshError("Official source resolved outside the approved domains.")
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "text/html" not in content_type:
        raise SourceRefreshError("Only HTML official pages are currently refreshable.")
    raw = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(raw) > MAX_DOWNLOAD_BYTES:
        raise SourceRefreshError("Official page exceeded the safe download limit.")
    charset = response.headers.get_content_charset() or "utf-8"
    html = raw.decode(charset, errors="replace")
    title, sections = extract_html_sections(html)
    if not sections:
        raise SourceRefreshError("No usable instructional sections were found.")
    normalized = "\n".join(
        f"{item['heading']}\n{item['text']}" for item in sections
    )
    return {
        "not_modified": False,
        "final_url": final_url,
        "etag": response.headers.get("ETag", "")[:300],
        "last_modified": response.headers.get("Last-Modified", "")[:300],
        "content_hash": _hash(normalized),
        "page_title": title,
        "sections": sections,
    }


def refresh_source(source, *, accept_changes=False, opener=None):
    """Check a source and optionally activate a changed, immutable revision."""
    now = timezone.now()
    try:
        result = fetch_source(source, opener=opener)
    except Exception as exc:
        source.refresh_error = str(exc)[:500]
        fields = ["refresh_error"]
        # A confirmed unsafe redirect, unsupported response, or bad HTTP status
        # invalidates the source. A DNS error or timeout does not make previously
        # verified content fresh, nor does it immediately declare it broken.
        if isinstance(exc, SourceRefreshError):
            source.refresh_status = "BROKEN"
            fields.append("refresh_status")
        source.save(update_fields=fields)
        raise

    if result["not_modified"]:
        source.last_checked_at = now
        source.refresh_status = "VERIFIED"
        source.refresh_error = ""
        source.save(update_fields=["last_checked_at", "refresh_status", "refresh_error"])
        return "unchanged"

    changed = bool(source.content_hash and source.content_hash != result["content_hash"])
    revision = OfficialSourceRevision.objects.create(
        source=source,
        final_url=result["final_url"],
        content_hash=result["content_hash"],
        page_title=result["page_title"],
        sections=result["sections"],
        accepted=not changed or accept_changes,
        accepted_at=now if (not changed or accept_changes) else None,
    )
    if changed and not accept_changes:
        # Keep the validators for the accepted version. Saving the candidate's
        # ETag here could make the next review fetch return 304 and accidentally
        # bless content that was never accepted.
        source.last_checked_at = now
        source.refresh_status = "CHANGED"
        source.refresh_error = "Official content changed; review required."
        source.save(update_fields=["last_checked_at", "refresh_status", "refresh_error"])
        return "changed"

    source.last_checked_at = now
    source.final_url = result["final_url"]
    source.etag = result["etag"]
    source.last_modified = result["last_modified"]
    source.refresh_error = ""
    # Historical wording lives in the immutable revision and in each persisted
    # GuideStep's citation snapshot; the live retrieval index contains only the
    # accepted current version.
    OfficialSourceSection.objects.filter(source=source).delete()
    OfficialSourceSection.objects.bulk_create(
        [
            OfficialSourceSection(
                source=source,
                heading=item["heading"],
                heading_path=item["heading_path"],
                anchor=item["anchor"],
                text=item["text"],
                position=position,
                content_hash=_hash(item["heading"] + "\n" + item["text"]),
                active=True,
                retrieved_at=revision.retrieved_at,
            )
            for position, item in enumerate(result["sections"], start=1)
        ]
    )
    source.content_hash = result["content_hash"]
    source.refresh_status = "VERIFIED"
    source.save()
    return "updated" if changed else "initialized"


_STOP_WORDS = {
    "a", "an", "and", "at", "for", "from", "i", "in", "is", "my", "of",
    "on", "the", "to", "want", "with", "your",
}


def _tokens(value):
    return {
        token for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def source_is_fresh(source, now=None):
    checked = source.last_checked_at or source.verified_at
    return bool(
        source.active
        and source.refresh_status == "VERIFIED"
        and checked
        and checked >= (now or timezone.now()) - timedelta(hours=source.refresh_interval_hours)
    )


def source_context_for(query, organization, limit=8):
    """Return only relevant, active section IDs and bounded official excerpts."""
    if organization is None:
        return []
    wanted = _tokens(query)
    candidates = OfficialSourceSection.objects.filter(
        source__organization=organization,
        source__active=True,
        source__refresh_status="VERIFIED",
        active=True,
    ).select_related("source")

    ranked = []
    for section in candidates:
        if not source_is_fresh(section.source):
            continue
        topic_tokens = _tokens(section.source.topic)
        heading_tokens = _tokens(section.heading_path)
        body_tokens = _tokens(section.text[:4000])
        score = 8 * len(wanted & topic_tokens) + 4 * len(wanted & heading_tokens) + len(wanted & body_tokens)
        if score:
            ranked.append((score, section))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].position))
    return [
        {
            "id": str(section.id),
            "source_title": section.source.title,
            "section_heading": section.heading_path or section.heading,
            "url": section.deep_link,
            "excerpt": section.text[:1800],
            "retrieved_at": section.retrieved_at.isoformat(),
        }
        for _, section in ranked[:limit]
    ]
