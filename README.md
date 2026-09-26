# Civic Breadcrumbs

> **Government shouldn't make you start over.**

Every institution remembers its own interaction. The citizen has to remember all
of them. Civic Breadcrumbs is a citizen-owned memory layer across fragmented
public services: you record what happened, and it tells you where you left off,
who is responsible, and hands the next person your whole story so you don't have
to explain it again.

Built for **Hack the Hill III**, Civic Technology track.

---

## What this is, in the challenge's own terms

| The challenge asks | Our answer |
|---|---|
| **Who is being served** | International students and newcomers in Ottawa, who routinely cross federal, provincial, municipal and university boundaries for a single goal. Secondarily, older adults and the family members who help them — a phone call, a letter or a counter visit is first-class evidence here, not a second-class input |
| **Which institution / civic process** | A study permit extension with IRCC, touching Service Canada, the Government of Ontario, the City of Ottawa and a university international office |
| **Which interaction we improve** | Continuity. The citizen stops re-assembling their own case history from memory every time they reach a new desk, and the person they reach gets a structured, accurate summary instead of a confused retelling |

The direction runs both ways: the citizen keeps their context, and the next
official receives a better-organized account of it than they would otherwise get.

### Why this isn't a chatbot

The core object is a **Journey** with structured, timestamped evidence — not a
conversation. Ask ChatGPT what "still processing" means and it will tell you.
It cannot tell you that *you* submitted on September 18, that IRCC told you on
September 24 not to reapply, and that nothing has changed since. That gap is the
product.

**Most of the app never calls a model at all.** The timeline, the current state,
"you left off here", the responsible organization and the handoff summary are all
derived deterministically from what you recorded. An AI helps read your sentence
into structure; it never becomes the record.

### Guidance and evidence are deliberately separate

Creating a Journey now produces a small ordered guide (three to six suggested
steps) before the citizen starts recording events. The guide is organizational
help, not evidence and not a claim about current official requirements. When a
jurisdiction or another load-bearing detail is missing, the guide asks one
focused clarification and stays generic rather than inventing a form, deadline,
fee or department.

A guide step becomes **in progress** only when the citizen records something
against it. It becomes **complete** only after an explicit confirmation, which
creates one idempotent user-reported Breadcrumb. The timeline therefore remains
an auditable record of what the citizen actually did, while reopening the guide,
viewing progress, editing, or deleting records uses zero Gemini calls.

---

## Run it

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py seed_demo
.venv/Scripts/python.exe manage.py runserver
```

Then open **http://127.0.0.1:8000/demo/**. API docs are at `/api/docs/`.

No API key, no database server and no network are required to run the whole
thing. SQLite is the default; point `DATABASE_URL` at PostgreSQL when you want
it:

```bash
DATABASE_URL=postgres://civic:civic@127.0.0.1:5432/civic_breadcrumbs
```

Copy `.env.example` to `.env` to configure anything. Every value has a working
default.

### Guest access and Auth0 Google sign-in

Guest mode is the default. Django issues an HttpOnly opaque session cookie and
owns the temporary identity, Journey ownership, quotas, and authorization. Guest
data expires after seven days by default; expired guest users and their Journeys
are removed by bounded cleanup during guest traffic.

To enable sign-in, create an Auth0 **Single Page Application** and API, enable
Google in Auth0's Social Connections, and attach that connection to the
application. Configure the allowed callback/logout/web origins for the frontend,
then set `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, and `AUTH0_AUDIENCE` from
`backend/.env.example`. No Auth0 client secret or Google OAuth credential belongs
in this repository. Auth0 performs Google sign-in through Universal Login;
Django validates the resulting RS256 API token and remains the authorization
system.

The demo keeps its access token in memory. The React client should use
`@auth0/auth0-react` with an `Auth0Provider`, the API audience, and the default
memory cache, then obtain tokens with `getAccessTokenSilently()` and send them as
Bearer tokens. Do not put access tokens in `localStorage`. After login, call
`POST /api/v1/auth/migrate-guest/` with both the bearer token and guest cookie;
the operation is idempotent and returns a recoverable conflict without deleting
guest data when the account is at capacity.

### Using a live Gemini key

Set `GEMINI_API_KEY` and `AI_ENABLED=true` in `.env`. Two commands verify it —
neither runs as part of `manage.py test`, neither spends quota unless you set
`AI_LIVE_TESTS=true` first:

```bash
python manage.py verify_gemini   # confirms the model id is still live, then
                                  # exercises all four AI operations for real
python manage.py eval_gemini     # 8 realistic prompts, printed for a human to
                                  # judge extraction quality by eye
```

Gemini model ids get retired on a schedule this codebase can't track — trusting
a hardcoded default is trusting a guess, which is exactly what `verify_gemini`
exists to check before you rely on it.

---

## The demo, in six steps

1. **Open the seeded journey.** A study permit extension with four recorded
   events across IRCC and a university office.
2. **Read "You are here."**
   *"Your last recorded interaction with IRCC, on September 24, 2026, reported
   the matter as still processing."* Note the tense — see below.
3. **Add something in plain words.** Type
   *"I called IRCC today. They said it's still processing and told me not to
   submit another one."* The system reflects back what it understood —
   *"Got it — you called IRCC and they said your application is still
   processing"* — with one button: **Yes, that's right.** One tap, not a
   seven-field form. "Edit details" is there if something's off, and a draft
   the system itself flags as unsure skips straight to the form instead of
   pretending to be confident.
4. **See what changed.** *"Because you recorded this, your status moved from
   Active to Waiting."* The app tells you what your action actually did,
   instead of silently refreshing.
5. **Press "I'm stuck."** A bounded answer: what happened, what's unresolved,
   the last instruction, the responsible organization, and official links with
   the date each was last checked. Not a chat window.
6. **Press "Hand me off."** A copyable case summary, generated from confirmed
   records only, ending with an actual question the recipient can answer.

Come back after a few quiet days and the journey card says so — *"You haven't
recorded anything new in 9 days"* — never a claim about how long the
government normally takes, only about your own recording gap. Correcting or
deleting a past entry (Edit/Delete on any timeline row) reports what changed
the same way.

Then the part worth watching:

```bash
AI_ENABLED=false .venv/Scripts/python.exe manage.py runserver
```

**Every screen above still works.** Not a degraded mode with features missing —
the same product.

---

## Two decisions that shape everything

### 1. The deterministic engine is the default, not the fallback

`services/ai/` defines one interface with two real implementations. `RuleBasedAIService`
reads cue words, resolves relative dates and matches organizations against a
curated directory. `GeminiAIService` does the same job with a model, behind
constrained JSON decoding and Pydantic validation. A factory picks one; any
timeout, malformed response or provider outage falls through to the deterministic
engine and reports `degraded: true`.

This is not a hedge. A civic tool that stops working when a vendor has an outage,
a quota runs out, or the library wifi drops is not dependable enough for the
people who need it most. It also keeps the core free of proprietary dependencies
and makes the AI genuinely replaceable rather than nominally so.

The honest tradeoff: the rule-based reading is more literal than a model's and
will miss unusual phrasings. That is exactly why every draft goes to the citizen
for review before it is saved. The review step isn't a formality bolted onto an AI
feature — it's the mechanism that makes a modest extractor safe to depend on.

### 2. Generated content can never become evidence

`derive_journey_state()` is a pure function over confirmed, non-AI breadcrumbs.
The exclusion is enforced in the ORM query *and* on the model, so no caller can
bypass it. Handoff summaries are generated and returned but never stored —
persisting one would create a record that could later be mistaken for something
an official actually said.

**Tense is a correctness requirement, not copy polish.** The system says *"your
last recorded interaction reported X"*, never *"your application is X"*. It has no
authoritative live data and must not imply that it does. There is a test
asserting the forbidden phrasings never appear. The difference between reporting
evidence and asserting fact is the difference between a trustworthy civic tool and
one that misleads someone about their immigration status.

### 3. Gemini is a limited external resource, not a normal function call

Every read that doesn't need language understanding — the timeline, the
current state, confirming a breadcrumb, correcting one, deleting one,
official-source lookup — costs zero AI calls, always. Only three actions ever
reach a model, each capped at one call: interpreting a new sentence, creating
a journey from a description, and (opt-in only) rewording an already-complete
summary. `AIGateway` enforces the one-call budget in code — a second call
within one action raises rather than silently proceeding, so a future change
that tried to chain calls together would fail a test, not ship.

Provider failures are never automatically retried. A **429** cannot resolve
within the request, and even a transient **503** falls through immediately to
the deterministic engine. This keeps the stronger invariant that one explicit
action can spend at most one Gemini call.

A live evaluation suite (`manage.py eval_gemini`, 8 varied prompts) caught
something a mocked test never could: Gemini's own judgment about whether a
detail needs clarifying isn't reliable — it sometimes said no even with an
unconfirmed organization on an interaction, and once said yes with no actual
question attached. Both are now enforced as invariants on the data contract
itself (`BreadcrumbDraft`'s validators), so they hold no matter which
extractor produced the draft, not just the one that happened to get tested.

---

## How the constraints were actually addressed

- **Accessibility** — the API returns structure, never prose-only, so a client can
  render large type and high contrast. Provenance is shown as words
  (*"Recorded by you"*, *"Official source"*), never colour alone. The state panel
  is an `aria-live` region; every control is a real button with visible focus.
  Non-digital channels — phone, letter, in person — are first-class breadcrumb
  types, because telling someone their government interactions should have been
  online is not help.
- **Privacy** — data minimization by construction. There is no field in the schema
  for a SIN, date of birth, passport number, address or financial detail. A
  reference number is optional and only captured when the citizen labelled it as
  one, so we never hoover up stray digits. Context sent to a model is the journey
  goal and current state — never the full history.
- **Trust** — four-way provenance on every record, an explicit "we don't know"
  answer when no organization matches, and official links carrying the date a
  human last verified them.
- **Limited resources and connectivity** — zero AI calls on every read path;
  full function offline.
- **Legacy systems** — requires no government integration and no institution's
  cooperation to be useful on day one.

### What it deliberately will not do

Make government decisions · determine legal status · give legal or immigration
advice · submit applications on your behalf · invent an official contact, form or
deadline · claim a live application status it cannot verify · behave as a
general-purpose chatbot.

A refusal, for instance, produces *"No further action has been recorded"* — not a
suggestion to appeal. That's a legal question and not ours to answer. Equally,
when the correct answer is *"nobody needs to hear from you, wait"*, it says so
rather than manufacturing someone to call.

---

## Architecture

```
React client  →  DRF API  →  domain services  →  models / PostgreSQL
                                   ↓
                            AI gateway (optional)  →  Gemini
```

A modular monolith, two Django apps.

```
backend/
├── apps/journeys/     Journey + Breadcrumb, state derivation, stuck, handoff
├── apps/directory/    Curated organizations and official sources
├── services/ai/       One interface, two implementations, intent gate, prompts
├── common/            Error envelope, dev auth, throttling, deploy checks
└── demo/              Dependency-free fallback UI
```

Files worth reading first:

| File | Why |
|---|---|
| `apps/journeys/state.py` | The pure function the whole product rests on |
| `services/ai/factory.py` | Fallback and the one-call-per-action invariant |
| `services/ai/rules.py` | The deterministic engine |
| `services/ai/intent.py` | Scope gate; injection handled as data |
| `apps/directory/selectors.py` | Why we never invent an institution |

### API

```
POST   /api/v1/journeys/                                ≤1 AI call
GET    /api/v1/journeys/{id}/                            0   ← staleness rides along
POST   /api/v1/journeys/{id}/breadcrumbs/interpret/     ≤1, persists nothing, paraphrase included
POST   /api/v1/journeys/{id}/breadcrumbs/                0, the only write path, reports what changed
PATCH|DELETE /api/v1/breadcrumbs/{id}/                   0, reports what changed
GET    /api/v1/journeys/{id}/state/                      0   ← "you left off here"
GET    /api/v1/journeys/{id}/stuck/                      0 unless ?polish=true, then ≤1, prose only
GET    /api/v1/journeys/{id}/responsible-organization/   0
POST   /api/v1/journeys/{id}/handoff/                    0 unless polish requested, then ≤1, persists nothing
POST   /api/v1/journeys/{id}/notes/                      0   ← always-open escape hatch
```

Other guarantees: ownership failures return **404, not 403**, so journey ids
can't be enumerated; a client `request_id` makes submission idempotent; AI-backed
routes are rate limited while reads never are, and the throttle itself only
engages when a request can actually reach a model.

---

## Tests

```bash
cd backend
.venv/Scripts/python.exe manage.py test
```

128 tests, no network access required — `manage.py test` forces AI off
regardless of what's in `.env`, so a real key sitting there can never make the
suite flaky or dependent on quota. They cover state derivation (including the
tense rule and the staleness thresholds), the full API lifecycle including
closing-the-loop reporting, ownership, idempotency, throttling, schema
validation of model output (including the cross-extractor clarification
invariants), the no-automatic-retry Gemini policy, the out-of-scope gate,
prompt injection, prompt
fencing, and an end-to-end pass with AI switched off entirely.

---

## Status and what's next

Complete: the full vertical slice above, plus the curated directory, official
sources, rate limiting, OpenAPI and the demo interface.

Not built, deliberately: Auth0 (the dev identity is one line from being swapped
out — ownership is already enforced against `request.user` everywhere), voice
input, bilingual content, and the aggregate "civic friction map". Each is a real
idea; none of them make the core flow better, and a demo of eleven things that
work beats a demo of thirty that half-work.

**All demo data is synthetic.** Nothing here is an official government record.
