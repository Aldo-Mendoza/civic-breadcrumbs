Yes. I would structure this as a **small, deeply implemented citizen-side prototype**, rather than trying to build a full “government platform.”

The core idea becomes:

# **Don’t Make Me Start Over.**

A citizen-owned journey tracker that helps people navigate fragmented government/institutional processes, remember what has already happened, understand what comes next, and hand their context to the next human or institution when they get stuck.

Hack the Hill III is particularly well suited to this because the event explicitly frames itself around impactful solutions to civic challenges, and the Civic Technology track is about bringing government and people closer together. ([Hack the Hill][1])

---

# 1. Full project context

## Working name

### **Civic Breadcrumbs**

**“Don’t make me start over.”**

The name can change later. I actually like **Civic Breadcrumbs** as the internal/project name because it connects directly to the original networking idea:

> Originally, we wanted to remember the people we meet.
> Now we're remembering the journey people take through institutions.

The product itself could eventually have a more consumer-friendly name such as:

* Civic
* Relay
* CivicPath
* NextStep
* Thread
* Waypoint
* Breadcrumbs

But I wouldn't waste hackathon time deciding this.

---

# 2. The problem

Government services are increasingly digital, but **digital does not necessarily mean connected**.

Statistics Canada's April 2026 analysis found that among Canadians using digital government services, the most common problems included:

* difficulty finding the right information — **46.0%**
* difficulty finding customer-service assistance — **31.6%**
* difficulty finding the correct website — **29.9%**

The proportion of digital-government users reporting at least one problem reached **65.8% in 2022**. ([Statistics Canada][2])

The federal government's own Digital Ambition also recognizes the problem: complex information flows can make government services difficult to find, navigate and use, and nearly 70% of respondents in the cited research reported at least one problem with digital government services. ([Canada][3])

This creates a very specific human experience:

> **Every institution remembers its own interaction.
> The citizen has to remember all of them.**

Imagine:

**Website → form → email → phone call → office → another department → another form**

Each interaction may be perfectly reasonable in isolation.

But the citizen has to maintain the entire state of the process in their head.

---

# 3. The insight

We're not trying to make government itself smarter.

We're asking:

> **What if the citizen had their own memory layer across government?**

The government doesn't need to integrate with us for the MVP.

The citizen can create a journey:

> **“I need to resolve my immigration application.”**

The app then becomes the place where they keep:

* what they discovered
* which official website they used
* what they submitted
* when they submitted it
* who they contacted
* what that person told them
* reference numbers
* documents they still need
* what they are waiting for
* what they should do next

That's a fundamentally different product from a chatbot.

---

# 4. The central UX

The app should essentially have two entry points.

## A. “What are you trying to get done?”

The citizen starts with a goal.

Examples:

> “I just moved to Ottawa.”

> “I need to renew my study permit.”

> “I need to find out why my application is delayed.”

> “I need to get a driver's licence.”

> “I need to help my mother access a government service.”

The application creates a **Journey**.

---

## B. “I'm stuck.”

This is arguably our most important button.

The user doesn't need to understand the bureaucracy.

They simply say:

> “I don't know what I'm supposed to do now.”

The application examines the journey and responds with:

**You left off here.**

> You submitted your application on September 18.
> You contacted the service centre on September 24.
> They told you the application is still under review.
> You were advised not to submit another application.
>
> **Next step:** Wait for the review to complete.
>
> **Need help?** Generate a summary for the next person you contact.

That is the product.

---

# 5. What exactly is a Breadcrumb?

A Breadcrumb is:

> **A piece of information or evidence that moves a citizen's journey forward.**

It can be:

### Official information

> “The Ontario website says I need X.”

### Action

> “I submitted the form.”

### Document

> “I uploaded my proof of address.”

### Interaction

> “I called IRCC.”

### Person

> “I spoke with Maria at the service centre.”

### Communication

> “They emailed me saying the application is incomplete.”

### Personal note

> “They told me not to submit another application.”

Every Breadcrumb gets structured into the journey.

---

# 6. The important architectural distinction

Don't model the application around **chat messages**.

Model it around:

```text
Journey
   │
   ├── Goal
   │
   ├── Breadcrumbs
   │      ├── Source
   │      ├── Interaction
   │      ├── Document
   │      ├── Person
   │      └── Action
   │
   ├── Current State
   │
   ├── Next Action
   │
   └── Handoff Summary
```

AI is then a service operating **on top of that structured state**.

This is important because otherwise a judge can reasonably say:

> “Why isn't this just ChatGPT?”

---

# 7. Why not just use ChatGPT?

This needs to be one of our strongest demo explanations.

## Scenario 1 — Immigration

Imagine an international student says:

> “I applied for my study permit extension three months ago. I called IRCC last week and they told me it's still processing. What should I do?”

### Google

Google can find:

* IRCC processing times
* application pages
* FAQs
* contact information

But Google doesn't know:

* what the user submitted
* when they submitted it
* who they contacted
* what they were told
* which steps they already completed
* what changed yesterday

---

### ChatGPT

ChatGPT can explain the situation and potentially help organize information the user provides.

But the user's actual problem isn't necessarily:

> “I need an explanation.”

It's:

> **“Where am I in my real-world process?”**

Our app has a persistent structured journey:

```text
Study Permit Extension

✓ Application submitted
✓ Confirmation received
✓ Called IRCC
✓ Told application is processing

CURRENT:
Waiting for processing

NEXT:
No action required unless circumstances change

LAST INTERACTION:
IRCC — Sept 24

REFERENCE:
XXXXXXX
```

Then two weeks later:

> **“You left off here.”**

That's the difference.

---

# 8. Why not just use a government website?

Because government websites generally describe **the institution's process**.

Our application describes:

> **the citizen's journey through multiple processes.**

For example:

```text
Citizen
   ↓
IRCC
   ↓
Ontario
   ↓
University
   ↓
Service Canada
```

The citizen sees one journey.

Each institution sees its own piece.

That distinction is the heart of the project.

---

# 9. Why not just use a notes app?

This is another important differentiator.

A notes app gives you:

> “Call IRCC on Monday.”

Our application understands:

> This is part of your **study-permit journey**.

And therefore can associate:

* the call
* the person
* the organization
* the application
* the previous action
* the next action

The value comes from **relationships between events**, not merely storing notes.

---

# 10. Why Canada / Ontario?

We should keep the PoC deliberately narrow.

### Suggested initial geography:

**Ottawa, Ontario**

And specifically:

> **People navigating complex public services across federal + provincial + municipal boundaries.**

Ottawa is particularly useful as a conceptual test environment because a resident may interact with multiple levels of government for a single real-world objective.

The federal government provides immigration, taxes, employment and many other services.

Ontario provides provincial services.

The City of Ottawa provides municipal services.

From the citizen's perspective:

> **It's all just “government.”**

The organizational boundaries are meaningful to institutions, but often aren't meaningful to the person's goal.

Canada's own research describes the complexity of government information flows and the challenge of navigating digital services. ([Canada][3])

---

# 11. Initial target demographics

We should **not** pitch this as “an app for everyone.”

That's too broad.

Instead:

## Primary PoC

### International students and newcomers

Why?

They frequently have to navigate multiple institutions and may not know:

* which level of government handles something
* which organization to contact
* what terminology means
* which document is being requested
* what they have already completed
* what to do after an interaction

The federal government itself provides newcomers with resources spanning housing, education, health care, employment, language, credentials, taxes and benefits. ([Canada][4])

That's an excellent example of a journey that crosses domains.

---

## Secondary demographic

### Older adults

This is an important accessibility scenario.

Statistics Canada reports that in 2022, digital government service use was **55.4% among people aged 65+**, compared with **91.3% among people aged 25–34**. ([Statistics Canada][2])

The federal research also notes that older people are more likely to prefer channels such as phone and mail. ([Canada][5])

This actually strengthens our concept.

We aren't saying:

> “Everything should be digital.”

We're saying:

> **Whatever channel you use, your journey should have continuity.**

Phone call?

Breadcrumb.

In-person visit?

Breadcrumb.

Paper letter?

Breadcrumb.

Website?

Breadcrumb.

That's much more interesting.

---

# 12. Accessibility becomes a feature, not a checkbox

Someone could:

### Type

> “They told me I need another document.”

### Speak

> “I went to the office today and the guy told me…”

### Upload

A letter/email.

### Scan

A reference number or QR code.

The application turns that into structured information.

This could also support multilingual interactions.

For example:

> User speaks French → journey stored structurally → next explanation in English/French.

We should **not** attempt to build a universal translation platform during the hackathon.

---

# 13. The MVP

This is where we need discipline.

For a 36-hour hackathon, I would build **one excellent vertical slice**.

## MVP:

### 1. Create Journey

```text
What are you trying to get done?
```

AI converts the user's description into:

```text
Journey:
Study Permit Extension

Goal:
Maintain valid student status

Relevant organization:
IRCC

Current state:
Application submitted

Potential next steps:
...
```

---

### 2. Journey Dashboard

Something like:

```text
┌─────────────────────────────────────┐
│ Study Permit Extension              │
│                                     │
│ ● Application submitted             │
│ ● Confirmation received             │
│ ● Called IRCC                       │
│                                     │
│ YOU ARE HERE                        │
│ Waiting for processing              │
│                                     │
│ NEXT                                 │
│ Wait for application update          │
│                                     │
│        [ I'M STUCK ]                 │
└─────────────────────────────────────┘
```

---

### 3. Add Breadcrumb

One simple interface:

> **What happened?**

User:

> “I called IRCC today. They said my application is still processing and I shouldn't submit another one.”

Gemini structures:

```json
{
  "type": "interaction",
  "organization": "IRCC",
  "date": "...",
  "status": "processing",
  "instruction": "Do not submit another application",
  "next_action": "wait"
}
```

The user confirms.

Save.

---

### 4. “You left off here”

This should be the hero feature.

Open the app tomorrow:

> **Welcome back.**

> You last updated this journey yesterday.

> **You were told your application is still processing.**

> **Your next action: Wait.**

That should feel almost magical despite being technically simple.

---

### 5. “Who Do I Talk To?”

Given the journey, identify the appropriate **organization/channel**, not necessarily an individual.

Example:

```text
WHO DO I TALK TO?

Your next issue appears to concern:
Immigration application status

Organization:
IRCC

Recommended channel:
Official IRCC contact/service channel

[OPEN OFFICIAL SOURCE]
```

Eventually this can become much smarter.

---

### 6. “Hand Me Off”

Generate:

```text
CASE SUMMARY

Issue:
Study permit extension application

Application:
Submitted September 18

Previous interactions:
• Application submitted
• Confirmation received
• Contacted IRCC September 24

Last information received:
Application remains under processing.

Current question:
Is any additional action required?

Reference:
XXXXXXXX
```

Then:

**Copy summary**

or eventually:

**Share**

This is where the product becomes extremely tangible.

---

# 14. What we should NOT build

This is just as important.

### ❌ No government API integrations

Not required for the MVP.

### ❌ No automatic government submissions

Too risky and too much scope.

### ❌ No universal government chatbot

That's not the problem we're solving.

### ❌ No social network

The original business-card idea evolves into the Breadcrumb model.

### ❌ No full document-management system

We can mock/document-reference things.

### ❌ No massive government database

Use a tiny curated set of official sources.

### ❌ No autonomous AI agent making decisions

AI structures information.

The citizen remains in control.

### ❌ No “official case record”

This is explicitly:

> **Citizen-owned journey information.**

Not a government record.

---

# 15. Modules / separation of concerns

I'd structure the application into approximately these modules.

## Module 1 — Identity

Responsible for:

* authentication
* user profile
* sessions
* authorization

Potentially use Auth0.

---

## Module 2 — Journeys

Core domain.

Responsible for:

* creating journeys
* goals
* status
* current state
* next action
* completion

Example:

```text
Journey
id
title
goal
status
created_at
updated_at
```

---

## Module 3 — Breadcrumbs

The core domain object.

Responsible for:

* interactions
* actions
* documents
* people
* notes
* sources
* timestamps

Example:

```text
Breadcrumb
id
journey_id
type
title
description
organization
person
occurred_at
source
created_at
```

---

## Module 4 — Organizations & Sources

Responsible for trusted external references.

Example:

```text
IRCC
Ontario
City of Ottawa
Service Canada
University
Community organization
```

Sources have:

* URL
* organization
* title
* source type
* retrieved date

Important:

**Official information should be visibly different from AI-generated interpretation.**

---

## Module 5 — AI Interpretation

Gemini sits here.

Responsibilities:

### Intent extraction

User:

> “I went to Service Canada and they said I need another document.”

AI → structured Breadcrumb.

### Summarization

Turn 8 Breadcrumbs into:

> “Your application is waiting for proof of X.”

### Next-action extraction

Turn interactions into:

> “Your next action is to upload X.”

### Handoff generation

Turn journey state into a concise summary.

AI should **not** be responsible for the underlying truth.

---

# 16. Source trust model

This is a potentially excellent UI feature.

Every piece of information gets a source classification.

### 🏛 Official

Government website or official communication.

### 👤 User reported

Something the citizen says happened.

### 🤖 AI interpretation

Something generated from the available information.

### 🤝 Community

Settlement organization, university, community organization, etc.

This helps solve the biggest problem with AI civic tools:

> **How do I know what I should trust?**

The application shouldn't pretend every statement has equal authority.

---

# 17. Privacy model

This is particularly important because immigration, taxes and benefits can contain sensitive information.

For the hackathon:

### Use synthetic data.

Do not put real:

* passport numbers
* immigration IDs
* SINs
* banking information
* sensitive documents

into the demo.

The architecture should conceptually follow:

```text
Citizen owns data
       ↓
Explicit sharing
       ↓
Temporary handoff
       ↓
Recipient sees only selected information
```

Future:

> **Share this journey for 24 hours**

or:

> **Share only these three Breadcrumbs.**

Then:

> **Revoke access.**

---

# 18. The killer “handoff” scenario

Imagine an international student.

They've:

1. looked at IRCC
2. submitted an application
3. emailed their university
4. called IRCC
5. spoken to an advisor
6. received another email

Now they need help.

Normally:

> “Can you explain what happened?”

And the student has to reconstruct everything.

Our application:

**HAND ME OFF**

```text
I'm trying to extend my study permit.

Application submitted:
Sept 12

Reference:
XXXX

I contacted IRCC:
Sept 20

They said:
Application remains under processing.

University international office:
Confirmed that no additional document is
currently required from the university.

Current issue:
I haven't received an update.

Question:
Does the current status require any action?
```

**That is the demo moment.**

---

# 19. Another scenario: elderly parent

Suppose a 72-year-old needs help with a government service.

Their daughter creates:

> **“Help Mom manage her government paperwork.”**

She records:

> “Mom called yesterday.”

Breadcrumb:

> Phone interaction.

Then:

> “The person told her to visit the office with identification.”

Breadcrumb:

> Action required.

The daughter can see:

> **Next step: visit office with identification.**

The system doesn't require Mom to become digitally sophisticated.

It simply preserves the journey.

This is also why the architecture should support **authorized helpers/delegates** eventually.

---

# 20. Another scenario: newcomer

Goal:

> **“Settle in Ottawa.”**

The journey could eventually contain:

```text
Housing
    ↓
Health coverage
    ↓
SIN
    ↓
Banking
    ↓
Employment
    ↓
Language services
    ↓
Education
    ↓
Taxes / benefits
```

The Government of Canada's newcomer resources already span many of these categories. ([Canada][4])

We don't need to implement all of them.

We only need to demonstrate the underlying mechanism with **one journey**.

---

# 21. Why the architecture can eventually become much bigger

The long-term platform isn't really about government.

The deeper abstraction is:

> **A person's journey across fragmented organizations.**

The same model works for:

### Healthcare

```text
Family doctor
↓
Specialist
↓
Diagnostic test
↓
Hospital
↓
Insurance
```

### Education

```text
University
↓
Registrar
↓
Financial aid
↓
Government
```

### Insurance

```text
Accident
↓
Police report
↓
Insurance
↓
Repair shop
↓
Rental vehicle
```

### Utilities

```text
Move
↓
Electricity
↓
Internet
↓
Water
↓
Municipality
```

The hackathon project is civic.

The underlying architecture is a **cross-institution journey layer**.

---

# 22. The future opportunity: Civic Friction Map

This is something I would **mention but not build extensively**.

If citizens voluntarily and anonymously contribute journey events, we could eventually identify:

> Where are people getting stuck?

For example:

```text
Service
   ↓
Website
   ↓
Application
   ↓
Phone
   ↓
Office
   ↓
Handoff
   ↓
?????
```

Aggregate thousands of journeys.

Maybe the system discovers:

> “42% of journeys involving Service X contain a handoff between Department A and Department B.”

That's potentially valuable to institutions.

But there's an important product philosophy:

> **The citizen product comes first.**

Government can eventually benefit from aggregated friction data without owning the individual journey.

Tiger Data/PostgreSQL could become useful here later for event/time-series analysis.

---

# 23. The “Who Do I Talk To?” evolution

The original idea was:

> “Who is the person I should talk to?”

We should turn that into:

# **“Who is responsible for my next step?”**

That's much more powerful.

The answer might be:

* IRCC
* Ontario
* City of Ottawa
* university office
* community organization
* service centre
* specific department
* **nobody — you simply need to wait**

That last one is important.

A good system shouldn't manufacture a human contact when the correct answer is:

> **No action is currently required.**

---

# 24. Sponsor/track strategy

For the hackathon, the natural primary track is:

## **Civic Technology**

This concept directly fits the stated objective of bringing people and government closer together. ([Hack the Hill][1])

Then we can layer in sponsor/minor challenges without compromising the product.

### Gemini

Very natural.

Use it for:

* natural-language journey creation
* Breadcrumb extraction
* summarization
* handoff generation
* multilingual interpretation

---

### Auth0

Natural.

Use it for:

* authentication
* secure identity
* controlled sharing

---

### UI/UX

Extremely important.

The app's value should be visible in seconds.

---

### ElevenLabs

Potential extension:

> “Tell me what happened.”

User speaks.

The app converts speech into a Breadcrumb.

Later:

> “What do I need to do next?”

The app reads the answer.

Useful accessibility feature, not a gimmick.

---

### Tiger Data

Potential future:

**Civic Friction Map**

Not necessary for MVP.

---

### FOSS

Potentially compatible if we ensure the core isn't dependent on proprietary technology.

---

### Solana / hardware / other challenges

Don't force them.

A bad sponsor integration can make a good product look like a sponsor demo.

---

# 25. What judges should understand in 30 seconds

The pitch can be extremely simple:

> **“Government services are fragmented, but your problem isn't.**
>
> Today, if you deal with multiple departments, websites, phone calls and people, you're responsible for remembering everything.
>
> We built a citizen-owned memory layer for those interactions.
>
> You create a journey, add what happens along the way, and our system turns those interactions into a structured timeline.
>
> When you come back, it tells you:
>
> **‘You left off here.’**
>
> And when you need help, it creates a handoff summary so you don't have to start over.
>
> **Government shouldn't make you start over.”**

That's the story.

---

# 26. What we actually need to build during the hackathon

I'd divide the 36 hours roughly into:

### Phase 1 — Foundation

* repository
* Django
* PostgreSQL
* authentication
* basic React frontend
* database models

### Phase 2 — Core journey

* create journey
* journey dashboard
* Breadcrumb CRUD
* timeline

### Phase 3 — AI

* natural-language journey creation
* Breadcrumb extraction
* journey summary
* next-action extraction

### Phase 4 — Handoff

* generated case summary
* copy/share flow

### Phase 5 — Polish

* accessibility
* source labels
* visual timeline
* empty/loading/error states
* demo data

### Phase 6 — Demo

Prepare **one exceptional story**.

Don't build 20 mediocre features.

---

# 27. The demo story I'd use

I'd use an **international student/newcomer** because it naturally demonstrates fragmented institutions without requiring us to claim the product is only for immigrants.

Start with:

> “I submitted my application three weeks ago and I don't know what I'm supposed to do now.”

The application creates:

**Study Permit Journey**

Then show:

```text
✓ Application submitted
✓ Confirmation received
✓ Contacted institution
✓ Called IRCC

YOU ARE HERE

Waiting for processing

NEXT ACTION
No action currently required
```

Then:

**I'm stuck**

The system explains why.

Then:

**Who do I talk to?**

→ IRCC official channel.

Then:

**Hand me off**

→ Generates the entire history.

That is a complete narrative.

---

# 28. README for the AI development agent

Below is the version I would actually put into the repository as `README.md`.

```markdown
# Civic Breadcrumbs

> Government shouldn't make you start over.

Civic Breadcrumbs is a citizen-side civic technology prototype that helps people
navigate fragmented government and institutional processes by maintaining a
citizen-owned record of their journey.

Instead of treating each government interaction as an isolated event, the
application connects websites, actions, phone calls, emails, people, documents,
and instructions into one persistent journey.

The core interaction is:

    What are you trying to get done?
                ↓
             Journey
                ↓
           Breadcrumbs
                ↓
        Current state / next action
                ↓
           I'm stuck
                ↓
           Human handoff

The project is being built as a prototype for Hack the Hill III 2026 at uOttawa.

---

# 1. Hackathon Context

Hack the Hill III is taking place September 25–27, 2026 at the University of
Ottawa.

The hackathon focuses on impactful and innovative solutions to real-world
civic challenges.

Primary track:

    Civic Technology

The project should prioritize depth over breadth.

Do NOT attempt to build a complete government-services platform.

The goal is to build one polished vertical slice demonstrating the central
concept:

    "Don't make me start over."

Relevant challenge/sponsor opportunities include:

- Civic Technology
- Best UI/UX
- Gemini
- Auth0
- ElevenLabs
- potentially Tiger Data
- potentially Best FOSS

Only use sponsor technologies where they provide genuine product value.

---

# 2. Problem

Government services increasingly use digital channels, but citizens often have
to navigate multiple disconnected organizations, websites, phone numbers,
forms, offices, and people.

The citizen is responsible for remembering the complete process.

Examples:

    Government website
        ↓
    Online application
        ↓
    Email
        ↓
    Phone call
        ↓
    Service centre
        ↓
    Another department
        ↓
    Another form

Each institution may know its own part of the process.

The citizen has to know all of it.

Statistics Canada reported in 2026 that among Canadians using digital
government services, common problems included:

- 46.0% had difficulty finding the right information on websites
- 31.6% had difficulty finding customer service assistance
- 29.9% had difficulty finding the correct websites
- 65.8% reported at least one problem accessing digital government services
  in 2022

Source:

https://www150.statcan.gc.ca/n1/pub/22-20-0001/222000012026001-eng.htm

The Government of Canada's Digital Ambition also identifies complex
information flows and difficulty finding, navigating and using digital
services as ongoing challenges.

Source:

https://www.canada.ca/en/government/system/digital-government/canada-digital-ambition/canada-digital-ambition-2023-24.html

---

# 3. Core Insight

Government systems remember their own interactions.

Citizens have to remember the journey between them.

Civic Breadcrumbs creates a citizen-owned memory layer across those
interactions.

The product is NOT:

- a government portal
- a government CRM
- a generic chatbot
- a search engine
- a digital business card application
- an official government case-management system

It IS:

    A citizen-owned journey and context layer.

---

# 4. Core Value Proposition

Primary:

    Don't make me start over.

Alternative:

    Government is fragmented. Your problem isn't.

Product explanation:

    Civic Breadcrumbs helps citizens keep track of what they are trying to
    accomplish, what they have already done, what they were told, where they
    currently are, and what they should do next.

When they need help, the application creates a concise handoff summary so
they don't have to explain the entire story again.

---

# 5. Primary PoC User

The initial prototype should focus on:

    International students and newcomers in Ottawa/Ontario.

This is a demonstration demographic, not a permanent product restriction.

Relevant journeys can cross:

- federal government
- provincial government
- municipal government
- universities
- settlement organizations
- service centres

The Government of Canada provides newcomer resources covering areas such as
housing, education, healthcare, employment, language, credentials, taxes,
benefits and community services.

Sources:

https://www.canada.ca/en/immigration-refugees-citizenship/services/settle-canada.html

https://www.canada.ca/en/immigration-refugees-citizenship/campaigns/newcomers.html

---

# 6. Secondary User Scenario

Older adults and people who rely on family members or caregivers for
navigating services.

The application should not assume that every interaction is digital.

A Breadcrumb can come from:

- website
- phone call
- email
- in-person visit
- paper letter
- conversation
- uploaded document
- personal note

Statistics Canada reported that in 2022 digital government service use was
55.4% among Canadians aged 65+ versus 91.3% among those aged 25–34.

Source:

https://www150.statcan.gc.ca/n1/pub/22-20-0001/222000012026001-eng.htm

Therefore the application should bridge digital and physical interactions
rather than attempting to make every government interaction digital.

---

# 7. Primary User Flow

## Step 1 — Create a Journey

User sees:

    What are you trying to get done?

Example:

    "I applied to extend my study permit and I'm not sure what I need to do
    next."

The system creates:

    Journey:
        Study Permit Extension

    Goal:
        Maintain valid status / complete the application process

    Organization:
        IRCC

The user confirms the generated interpretation.

---

## Step 2 — Journey Dashboard

The dashboard displays:

    JOURNEY TITLE

    Goal

    Timeline

    Current state

    Next action

    Official sources

    [ADD BREADCRUMB]

    [I'M STUCK]

Example:

    STUDY PERMIT EXTENSION

    ✓ Application submitted
    ✓ Confirmation received
    ✓ Contacted university
    ✓ Contacted IRCC

    YOU ARE HERE

    Application remains under processing.

    NEXT ACTION

    No action currently required.

    [ I'M STUCK ]

---

# 8. Breadcrumbs

A Breadcrumb is:

    A piece of information or evidence that moves a journey forward.

Possible types:

- ACTION
- INTERACTION
- DOCUMENT
- PERSON
- OFFICIAL_SOURCE
- EMAIL
- NOTE
- STATUS_UPDATE

Example:

User enters:

    "I called IRCC today. They said my application is still processing and I
    should not submit another application."

AI extracts:

    type:
        INTERACTION

    organization:
        IRCC

    status:
        PROCESSING

    instruction:
        Do not submit another application

    next_action:
        WAIT

The user confirms before saving.

AI suggestions must not silently alter the user's journey.

---

# 9. Source Trust Model

Every important piece of information should have a source classification.

Types:

    OFFICIAL
        Government or institution source.

    USER_REPORTED
        Information directly entered by the citizen.

    AI_INTERPRETATION
        AI-generated interpretation of other information.

    COMMUNITY
        Community organization or other third-party source.

The UI should visually distinguish these.

AI-generated information must never be presented as an official government
decision.

---

# 10. "I'm Stuck"

This is one of the most important features.

The user can press:

    I'M STUCK

The system analyzes the structured journey and explains:

- what has already happened
- current state
- unresolved issue
- likely next action
- responsible organization/channel
- relevant official source

Example:

    YOU LEFT OFF HERE

    You submitted your application on September 18.

    On September 24 you contacted IRCC and were told that the application
    remains under processing.

    No additional action was recorded.

    NEXT ACTION:
    Wait for an update unless your circumstances change.

The AI should use the existing structured journey rather than inventing
history.

---

# 11. "Who Do I Talk To?"

The original networking concept evolved into:

    Who is responsible for my next step?

This does not necessarily mean finding an individual.

The answer may be:

- IRCC
- Ontario
- City of Ottawa
- a university office
- a service centre
- a community organization
- a specific department
- nobody; the citizen simply needs to wait

The system should prioritize official channels.

Do not invent government contacts.

---

# 12. "Hand Me Off"

This is a core differentiator.

When the user needs human assistance, generate a concise summary.

Example:

    CASE SUMMARY

    Goal:
        Extend study permit

    Application:
        Submitted September 18

    Previous interactions:
        - Application submitted
        - Confirmation received
        - Contacted university
        - Contacted IRCC September 24

    Last information received:
        Application remains under processing.

    Current question:
        Is any additional action required?

    Reference:
        XXXXXXXX

Actions:

    [COPY SUMMARY]

Future:

    [SHARE]

    [SHARE FOR 24 HOURS]

    [REVOKE ACCESS]

The MVP only needs Copy Summary.

---

# 13. Why This Is Not Just ChatGPT

ChatGPT can explain government information.

Google can find government information.

Government websites can provide official information.

Civic Breadcrumbs manages the citizen's real-world journey.

Example:

User:

    "I called the government and they told me to wait."

ChatGPT can explain what "wait" might mean.

Civic Breadcrumbs records:

    Organization: X
    Date: Y
    Interaction: phone call
    Status: waiting
    Instruction: wait
    Reference: Z

Two weeks later:

    "You left off here."

The core object is a Journey with structured events, not a conversation.

---

# 14. Why This Is Not Just a Notes App

A notes application might contain:

    "Call IRCC Monday."

Civic Breadcrumbs understands that this belongs to:

    Journey:
        Study Permit Extension

and connects the note to:

- organization
- previous interactions
- current state
- next action
- source
- handoff summary

The differentiator is the structured relationship between events.

---

# 15. Why This Is Not Just a Government Portal

A government portal describes one institution's services.

Civic Breadcrumbs follows the citizen across institutions.

Example:

    Citizen goal
         ↓
    IRCC
         ↓
    University
         ↓
    Service Canada
         ↓
    Ontario
         ↓
    City of Ottawa

The user experiences one journey.

The institutions remain separate.

---

# 16. MVP Scope

The MVP MUST contain:

1. Authentication
2. Create Journey
3. Journey dashboard
4. Breadcrumb CRUD
5. Timeline
6. Natural-language Breadcrumb extraction
7. Current-state summary
8. Next-action extraction
9. "I'm Stuck"
10. "Who Do I Talk To?"
11. Handoff summary
12. Official-source links
13. Source labels
14. Seeded demo journey

Everything else is optional.

---

# 17. Explicitly Out of Scope

Do NOT build:

- government API integrations
- automatic government form submission
- automatic immigration decisions
- legal advice engine
- full document management
- universal government directory
- complete government-service database
- social network
- government employee CRM
- autonomous agent contacting officials
- blockchain
- complex analytics dashboard
- broad healthcare functionality
- full multilingual platform

The demo should show depth, not breadth.

---

# 18. Suggested Technical Architecture

Frontend:

    React
    TypeScript
    Tailwind CSS

Backend:

    Django
    Django REST Framework

Database:

    PostgreSQL

Authentication:

    Auth0

AI:

    Gemini

Deployment:

    Any practical hackathon deployment platform.

Potential future:

    Tiger Data / PostgreSQL event analytics

Repository structure:

    /
    ├── frontend/
    │   ├── src/
    │   │   ├── features/
    │   │   │   ├── journeys/
    │   │   │   ├── breadcrumbs/
    │   │   │   ├── handoff/
    │   │   │   ├── sources/
    │   │   │   └── auth/
    │   │   ├── components/
    │   │   ├── services/
    │   │   └── types/
    │
    ├── backend/
    │   ├── config/
    │   ├── apps/
    │   │   ├── journeys/
    │   │   ├── breadcrumbs/
    │   │   ├── sources/
    │   │   ├── organizations/
    │   │   ├── ai/
    │   │   └── handoff/
    │
    ├── docs/
    ├── seed/
    ├── docker-compose.yml
    └── README.md

---

# 19. Separation of Concerns

## journeys

Owns:

- Journey
- goal
- state
- status
- next action

Should NOT contain AI-specific logic.

---

## breadcrumbs

Owns:

- Breadcrumb
- event types
- timestamps
- relationships to Journey

Should NOT call Gemini directly.

---

## sources

Owns:

- Source
- URL
- source type
- organization
- metadata

---

## organizations

Owns:

- organization
- department
- official channels

---

## ai

Owns:

- prompt construction
- Gemini client
- structured extraction
- summarization
- classification

AI service returns structured data.

It should not directly mutate unrelated domain objects.

---

## handoff

Owns:

- case-summary generation
- formatting
- future sharing functionality

---

# 20. Suggested Data Model

User

    id
    auth_provider_id
    created_at

Journey

    id
    user_id
    title
    goal
    status
    current_state
    next_action
    created_at
    updated_at

Breadcrumb

    id
    journey_id
    type
    title
    description
    organization_id
    person_name
    occurred_at
    source_id
    metadata
    created_at

Organization

    id
    name
    jurisdiction
    official_url

Source

    id
    organization_id
    title
    url
    source_type
    retrieved_at

HandoffSummary

    id
    journey_id
    summary
    created_at

Avoid over-normalization during the hackathon.

The schema should be easy to understand and modify.

---

# 21. AI Contract

Gemini should return structured JSON whenever possible.

Example:

{
    "breadcrumb_type": "INTERACTION",
    "organization": "IRCC",
    "status": "PROCESSING",
    "instruction": "Do not submit another application",
    "next_action": "WAIT",
    "confidence": 0.91
}

The backend must validate the output.

Never trust arbitrary model output directly.

The user should confirm important extracted information before it becomes
part of the persistent journey.

---

# 22. AI Responsibilities

Use AI for:

- extracting structured information from natural language
- summarizing a journey
- identifying possible next actions
- generating handoff summaries
- classifying intent
- translating/rephrasing where useful

Do NOT use AI as:

- an official source
- an immigration lawyer
- a government decision maker
- an autonomous government agent
- the sole source of truth

---

# 23. Demo Data

Use synthetic data.

Do NOT put real:

- SINs
- passport numbers
- immigration application numbers
- banking information
- sensitive medical information
- real private documents

into the public hackathon demo.

The application should be designed as if users could eventually store sensitive
information, but the prototype should avoid real sensitive information.

---

# 24. Recommended Demo Scenario

Primary demo:

    International student in Ottawa

Goal:

    Extend study permit

Breadcrumbs:

    1. Application submitted
    2. Confirmation received
    3. University contacted
    4. IRCC contacted
    5. IRCC says application is processing
    6. No additional action currently required

Demo flow:

    Create Journey
        ↓
    Show timeline
        ↓
    Add natural-language Breadcrumb
        ↓
    AI structures Breadcrumb
        ↓
    Show updated current state
        ↓
    Press I'M STUCK
        ↓
    Show next action
        ↓
    Press WHO DO I TALK TO?
        ↓
    Show responsible organization/channel
        ↓
    Press HAND ME OFF
        ↓
    Generate concise case summary

The audience should understand the value without needing a technical
explanation.

---

# 25. Secondary Demo Scenarios

## Newcomer

Goal:

    Settle in Ottawa

Potential journey:

    housing
    health services
    employment
    language services
    education
    taxes/benefits

Do not implement all of these.

Use one or two to demonstrate extensibility.

---

## Older Adult

Goal:

    Resolve a government-service issue

Breadcrumbs:

    phone call
    paper letter
    family member note
    in-person appointment

Demonstrates that the product is not limited to digital interactions.

---

# 26. Accessibility

The interface should prioritize:

- large readable typography
- high contrast
- keyboard navigation
- simple language
- clear status indicators
- minimal navigation
- voice input as an optional extension
- no information conveyed only through colour

Statistics Canada has documented accessibility barriers involving online
government information, services and supports.

Source:

https://www150.statcan.gc.ca/n1/pub/89-654-x/89-654-x2025004-eng.htm

---

# 27. Future Features

These are NOT MVP requirements.

Potential future features:

## Delegated journeys

Allow a trusted family member or caregiver to help manage a journey.

## Temporary sharing

Share a journey for a limited period.

## Selective sharing

Share only selected Breadcrumbs.

## Voice

Tell the application what happened after a phone call.

## Multilingual journeys

Allow users to interact in English or French and eventually additional
languages.

## Civic Friction Map

Aggregate anonymous journey events to identify where citizens repeatedly
get stuck.

## Organization feedback

Eventually allow institutions to understand aggregated friction without
accessing individual citizen journeys.

## Cross-sector journeys

Healthcare, education, insurance, utilities, etc.

---

# 28. Long-Term Product Vision

The long-term abstraction is not:

    Government chatbot

It is:

    Personal Journey Infrastructure

A person has a goal.

The goal crosses organizations.

The application maintains continuity.

Conceptually:

    PERSON
       ↓
    JOURNEY
       ↓
    ORGANIZATION
       ↓
    INTERACTION
       ↓
    ACTION
       ↓
    NEXT ACTION
       ↓
    RESOLUTION

This model could apply to government, healthcare, education, insurance,
utilities, and other fragmented systems.

---

# 29. Potential Future Civic Analytics

If users voluntarily contribute anonymized journey data, the platform could
eventually identify systemic friction.

Example:

    Service A
        ↓
    Department B
        ↓
    Handoff
        ↓
    Department C
        ↓
    Repeated user confusion

This could produce aggregated insights such as:

- common handoff points
- repeated information requests
- common unresolved states
- frequent sources of confusion
- services with unusually long journeys

This is a future capability, not part of the hackathon MVP.

---

# 30. Key Differentiators

1. Citizen-owned rather than government-owned.

2. Journey-centric rather than conversation-centric.

3. Cross-institution rather than institution-specific.

4. Persistent context rather than one-off answers.

5. Human handoff rather than AI-only assistance.

6. Official information is explicitly distinguished from AI interpretation.

7. Digital and physical interactions can coexist.

8. AI is used to structure and interpret the journey rather than pretending to
   be the source of truth.

9. The system can tell the user that no action is required.

10. The underlying architecture can eventually support multiple sectors.

---

# 31. Success Criteria for the Hackathon

A judge should be able to understand the product within 60 seconds.

A successful demo should demonstrate:

    1. "I have a problem."
    2. "I create a journey."
    3. "I record what happened."
    4. "The application structures it."
    5. "The application remembers."
    6. "I come back later."
    7. "It tells me where I left off."
    8. "I'm stuck."
    9. "It identifies the next responsible channel."
    10. "It generates a handoff."

If these work well, additional features are secondary.

---

# 32. Product Principle

The most important design principle is:

    DO NOT MAKE THE USER START OVER.

Every major feature should be evaluated against this principle.

If a feature does not help:

- preserve context
- understand state
- identify the next action
- connect the citizen to the right organization/person
- communicate existing context

then it probably does not belong in the MVP.

---

# 33. Useful Official References

Hack the Hill III:

https://hackthehill.com/

Government of Canada — settling in Canada:

https://www.canada.ca/en/immigration-refugees-citizenship/services/settle-canada.html

Government of Canada — newcomer services:

https://www.canada.ca/en/immigration-refugees-citizenship/campaigns/newcomers.html

IRCC newcomer service finder:

https://ircc.canada.ca/english/newcomers/services/

Statistics Canada — Digital Government Services:

https://www150.statcan.gc.ca/n1/pub/22-20-0001/222000012026001-eng.htm

Canada's Digital Ambition:

https://www.canada.ca/en/government/system/digital-government/canada-digital-ambition/canada-digital-ambition-2023-24.html

Statistics Canada — Internet accessibility barriers:

https://www150.statcan.gc.ca/n1/pub/89-654-x/89-654-x2025004-eng.htm

---

# 34. Final Product Statement

Civic Breadcrumbs is a citizen-owned memory layer for navigating fragmented
public services.

It doesn't replace government websites.

It doesn't replace government employees.

It doesn't replace search engines.

It doesn't try to become another chatbot.

It remembers the journey.

The central promise is:

    Government shouldn't make you start over.

And the core interaction is:

    "You left off here."
```

The official Canadian data gives us a particularly strong evidence base for this framing: **the problem isn't that Canadians have no digital government access; it's that finding the right information, assistance, and website remains a substantial source of friction.** ([Statistics Canada][2])

And I think the most important strategic decision is this: **don't make the hackathon demo “AI for government.” Make it a beautifully simple demonstration of continuity.** The AI is almost invisible. The thing the judge remembers is:

> **“I talked to three different people, and I didn't have to explain everything again.”**

That's the product.
