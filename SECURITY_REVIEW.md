# Cybersecurity review — 2026-10-07

## Result and scope

Local code review and synthetic regression tests found actionable confidentiality and security weaknesses. No live service was attacked and no actual third-party access or public disclosure has been established. Authentication, private API ownership, guest sessions, browser rendering, dependency advisories, and Git data handling were reviewed. Production infrastructure, logs, Auth0 tenant settings, historical remote refs, and copies held by other people were not audited.

## Findings and remediation

| Priority | Finding and attacker prerequisite | Remediation |
| --- | --- | --- |
| P1 | The latest local commit, `f40b665`, includes `breadcrumbs-db-2026-10-06.sql`. Repository readers could bypass API authorization and read exported account, identity, session, and journey data if this commit is shared. Metadata inspection found 77 user rows, 2 identity rows, 196 session rows, 16 journeys, and 7 breadcrumbs. Values were not printed or transmitted. | Preserve the export in an ignored owner-only `.private-backups` directory; preserve the original commit in an owner-only recovery bundle; rewrite only the latest unpushed local commit to exclude the export. Add database-export ignore rules and a CI guard for tracked private files. Local recovery objects and reflogs intentionally remain recoverable. |
| P1 | A valid Auth0 token continued to authenticate a locally disabled user (`is_active=False`). Someone retaining a valid token could still read the disabled account's journeys. | Reject disabled accounts and disabled guests before returning authenticated identities. Auth0-side revocation/expiry remains a separate deployment responsibility. |
| P1, conditional | The development identity authenticated arbitrary callers when enabled with DEBUG off. Normal production settings already remove this authenticator, but an alternate configuration could expose the shared demo account. | Enforce the DEBUG/test-runner boundary inside the authenticator itself and run deployment security checks during builds. |
| P2 | Private API responses had no no-store policy or identity-based cache variation. This left private journey data vulnerable to storage/reuse if a browser, proxy, or future cache cached responses. No actual shared-cache disclosure was reproduced. | Apply private, no-store cache headers and vary by Authorization/Cookie on API responses. Prevent caching of the citizen interface and reload restored browser-history pages. |
| P2, dependency | Dependency advisory scanning identified known vulnerabilities in Django 5.2.3, DRF 3.16.0, and PyJWT 2.10.1. Not every advisory affects this application's enabled features. | Pin Django 5.2.18, DRF 3.17.2, and PyJWT 2.15.0, test the upgraded runtime, and add weekly/PR/push dependency audits. |
| Defense in depth | The interface executed an Auth0 CDN script on every visit and lacked a Content Security Policy. A compromised script supply chain could act with the user's page privileges. No working stored/reflected XSS was established; reviewed user-text rendering escapes HTML. | Vendor the existing official Auth0 SDK with its provenance/digest; allow scripts only from this application, constrain network/frame access to the configured Auth0 tenant, block framing/objects, and suppress referrer leakage. Clear the access token and current journey on sign-out. |

## Remote exposure check

The two current remote branch tips were read from GitHub without fetching database contents:

- `main`: `4a19d2186572f656c7e399f4ec93ef6aa1566c9e`
- `Cesar's-cut`: `5188d6d9160acfd1e8a16dad94f93237cc924b19`

Neither commit contains the backup path, and neither contains the local backup commit in its ancestry. This supports cleaning the unpushed commit without a force-push. It does not prove the file has never been shared through another channel, deleted ref, or copy.

## Validation

- New tests reproduced disabled-account access, the development-auth boundary failure, missing private-cache headers, and missing browser policy before changes.
- 248 tests pass against Django 5.2.18, DRF 3.17.2, and PyJWT 2.15.0. Tests use synthetic data, in-memory SQLite, and no live AI calls.
- Cross-account read tests cover detail, guide, breadcrumbs, state, stuck summary, organization, and official-source routes; all return 404 for another owner's IDs.
- The updated dependency scan reports no known vulnerabilities in the resolved requirements. This is an advisory snapshot, not proof that unknown vulnerabilities do not exist.
- Django ordinary checks and migration-drift checks pass; JavaScript syntax checks pass. Deployment checks have no blocking security errors; HSTS subdomain/preload warnings remain because ownership and HTTPS readiness of every subdomain were not established. Broader schema checks also report pre-existing OpenAPI documentation warnings.
- Browser CSP enforcement and live Auth0 sign-in were not exercised in a browser. PostgreSQL concurrency and the production service were not tested or deployed.

## Deployment and incident response

The fixes must be reviewed, committed, and deployed before they protect the live service. The CI workflow begins operating when pushed. If the backup was shared outside the inspected current remote branches, treat those copies as exposed: investigate access, purge reachable hosted history/cached artifacts with the host, invalidate affected Django sessions, and assess account/password or credential rotation based on what was disclosed. No production session deletion, credential rotation, force-push, or disclosure notification was performed in this task.

## Primary references

- Django security guidance: https://docs.djangoproject.com/en/5.2/topics/security/
- Django's October 6 security fixes: https://www.djangoproject.com/weblog/2026/oct/06/security-releases/
- Django no-cache helpers: https://docs.djangoproject.com/en/5.2/ref/utils/#django.utils.cache.add_never_cache_headers
