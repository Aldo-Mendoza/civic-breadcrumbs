"""Small shared helpers."""
import re
import unicodedata

from django.utils import formats
from django.utils.translation import get_language
from django.utils.translation import gettext as _

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s]")


def normalize_text(value):
    """
    Fold text for duplicate comparison (CLAUDE.md §25).

    Case, accents, punctuation and whitespace are all discarded so that
    "I called IRCC today." and "i called ircc today" compare equal. No AI
    needed for exact-duplicate detection.
    """
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = _PUNCTUATION.sub(" ", folded.lower())
    return _WHITESPACE.sub(" ", folded).strip()


def truncate(value, limit):
    """Hard-cap a string, preferring a word boundary."""
    if not value or len(value) <= limit:
        return value or ""
    clipped = value[:limit].rsplit(" ", 1)[0]
    return (clipped or value[:limit]).rstrip() + "..."


def format_day(value):
    """
    Render a date the way a person says it: "September 24, 2026" in English,
    "24 septembre 2026" in French.

    English is built without platform-specific strftime padding flags so it
    behaves identically on Windows and Linux. French goes through Django's
    own date_format(), which already ships correct French month names and
    word order -- no need to reinvent either here.
    """
    if value is None:
        return _("an unrecorded date")
    if not hasattr(value, "strftime"):
        return str(value)
    if (get_language() or "en").startswith("fr"):
        return formats.date_format(value, "j F Y")
    return "{month} {day}, {year}".format(
        month=value.strftime("%B"), day=value.day, year=value.year
    )
