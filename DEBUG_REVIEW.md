# Debug review — 2026-10-07

Reviewed the Django API, state derivation, guest authentication, AI gateway, official-source grounding, and related frontend code. The configured workspace path was missing; the checkout was found at `/Users/caesar/Documents/ChatGPT/civic-breadcrumbs`. Changes were prepared in `/private/tmp/civic-debug-review` before application.

## Confirmed findings and fixes

| Priority | Bug and impact | Fix |
| --- | --- | --- |
| P1 | State derivation combined independent historical instructions with newer statuses/actions. A later processing update could say “Wait, as you were told: Upload your passport”; an old WAIT could override a newer incomplete status. | Scope current instructions and WAIT codes to their chronology; explicit actions use their own instructions. Historical instructions remain available as recorded history. |
| P2 | English “Attend the service office” matched the French waiting stem “attend”, producing WAITING. | Match bounded words and explicit French forms such as “attendre” and “attendez”. |
| P2 | PATCHing ARCHIVED was immediately overwritten by evidence recalculation, so archival did not persist. | Preserve explicit archival status across reads and evidence changes; reopening restores evidence-derived status. Reopening also uses the owner lock and active-journey quota, rolling back all edits if capacity is full. |
| P2 | Guest authentication created a database user and guest session before checking CSRF. Rejected writes could allocate orphan guest accounts. | Validate CSRF before guest cleanup, lookup, and creation. |
| P2 | AI result cache omitted response language. Repeating identical input after switching to French could return cached English output. | Include the active language in the cache key, retaining same-language reuse and user isolation. |
| P2 | The HTML section extractor counted void tags as nested elements, although they have no end tags. Paragraphs containing br/img/wbr could disappear entirely from official-source excerpts. | Handle HTML void tags without altering nesting; cover both HTML and self-closing syntax. |

## Executed debug plan

1. Run the baseline suite: all 233 tests passed, demonstrating missing regression coverage.
2. Add targeted tests: reproduced all six bug categories before fixing them.
3. Apply focused fixes and quota protection for archive reopening.
4. Run the complete suite: all 242 tests passed (nine new tests, plus stronger assertions in an existing CSRF test).
5. Run Django system checks and migration drift checks: no issues; no schema changes required.

Tests used an in-memory SQLite database with AI disabled; mocked AI tests exercised caching without network access. Production PostgreSQL concurrency and browser interactions were not exercised. No production deployment, live AI call, or data migration was performed. Existing environment files, local databases, and the untracked SQL backup are outside this patch.
