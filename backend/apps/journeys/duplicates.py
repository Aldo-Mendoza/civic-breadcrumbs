"""
Duplicate protection (CLAUDE.md §25).

People double-tap buttons and retry after a slow response. Two independent
mechanisms handle that, and neither needs a model:

1. **Idempotency by token.** A client-supplied ``request_id`` is unique per
   journey at the database level, so a retried submit returns the existing
   breadcrumb instead of creating a second one.
2. **Normalized-text warning.** If the same wording was already recorded
   recently, we surface a non-blocking warning. It stays a warning rather than a
   rejection on purpose: someone may genuinely have called the same office twice
   in one day and be right to record both.
"""
from django.utils.translation import gettext as _

from common.utils import normalize_text

#: How many recent breadcrumbs to compare against. Bounded so the check stays
#: cheap on a long journey.
RECENT_WINDOW = 10


def find_by_request_id(journey, request_id):
    """Return the breadcrumb already created for this token, if any."""
    if not request_id:
        return None
    return journey.breadcrumbs.filter(request_id=request_id).first()


def find_similar_recent(journey, raw_text, window=RECENT_WINDOW):
    """
    Find a recent breadcrumb with identical normalized wording.

    Exact-duplicate detection after folding case, accents and punctuation. No
    fuzzy matching and no embeddings: the cost of a false positive here is
    telling someone their real event looks like a duplicate.
    """
    normalized = normalize_text(raw_text)
    if not normalized:
        return None

    recent = journey.breadcrumbs.order_by("-created_at")[:window]
    for breadcrumb in recent:
        if normalize_text(breadcrumb.raw_text) == normalized:
            return breadcrumb
    return None


def duplicate_warning(breadcrumb):
    """The non-blocking warning payload for a suspected repeat."""
    from common.exceptions import ErrorCode

    return {
        "code": ErrorCode.DUPLICATE_EVENT,
        "message": _(
            "You recorded something with the same wording already. Save it "
            "anyway if it really happened twice."
        ),
        "existing_breadcrumb_id": str(breadcrumb.id),
    }
