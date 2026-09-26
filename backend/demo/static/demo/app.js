/*
 * Demo interface logic.
 *
 * Plain ES2020, no framework, no build step. The point of this file is to prove
 * the API is complete and usable: every panel here is driven purely by the
 * documented endpoints, with no client-side business logic. State derivation,
 * organization resolution and summary wording all come from the server, so this
 * file has no opinion about what the journey means.
 */
(function () {
  "use strict";

  const API = "/api/v1";
  let journeys = [];
  let organizations = [];
  let currentId = null;
  let lastDraft = null;
  let lastRawText = "";
  // Set only while correcting an existing record (Edit on a timeline row);
  // null means the form, when shown, will POST a new breadcrumb instead.
  let editingBreadcrumbId = null;

  // --- tiny helpers -------------------------------------------------------

  const $ = (id) => document.getElementById(id);

  const PANELS = [
    "new-journey-panel",
    "add-panel",
    "review-panel",
    "stuck-panel",
    "who-panel",
    "handoff-panel",
  ];

  function show(id) {
    PANELS.forEach((p) => {
      $(p).hidden = p !== id;
    });
    if (id) {
      const panel = $(id);
      // Bring the panel into view and move focus to its heading, so both
      // sighted and screen-reader users land on the new content.
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
      const heading = panel.querySelector("h2");
      if (heading) {
        heading.setAttribute("tabindex", "-1");
        heading.focus({ preventScroll: true });
      }
    }
  }

  function hideAll() {
    PANELS.forEach((p) => {
      $(p).hidden = true;
    });
    resetReviewPanelToCreateMode();
  }

  function resetReviewPanelToCreateMode() {
    editingBreadcrumbId = null;
    $("review-h").textContent = "Confirm what happened";
    $("review-confirm").textContent = "Save to my journey";
    $("review-note").hidden = false;
  }

  async function api(path, options) {
    const response = await fetch(API + path, Object.assign({
      headers: { "Content-Type": "application/json" },
    }, options || {}));
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      // The server always supplies a readable message and a suggested action.
      const err = body.error || {};
      const message = err.message || "Something went wrong.";
      alert(message);
      throw new Error(err.code || "REQUEST_FAILED");
    }
    return body;
  }

  function formatDate(value) {
    if (!value) return "";
    const d = new Date(value);
    if (isNaN(d)) return String(value);
    return d.toLocaleDateString(undefined, {
      year: "numeric", month: "long", day: "numeric",
    });
  }

  /*
   * Provenance as words.
   *
   * Never colour alone: a label has to survive greyscale, low vision and a
   * screen reader (README §26). "Recorded by you" also reads more honestly than
   * a coloured dot nobody has a legend for.
   */
  const SOURCE_LABELS = {
    USER_REPORTED: "Recorded by you",
    OFFICIAL: "Official source",
    COMMUNITY: "Community source",
    AI_INTERPRETATION: "AI interpretation - not evidence",
  };

  const CHANNEL_LABELS = {
    PHONE: "Phone", EMAIL: "Email", IN_PERSON: "In person", WEB: "Website",
    LETTER: "Letter", UPLOAD: "Upload", OTHER: "Other", UNKNOWN: "",
  };

  const STATUS_WORDS = {
    WAITING: "Waiting", ACTION_REQUIRED: "Action needed",
    COMPLETED: "Completed", ACTIVE: "Active", ARCHIVED: "Archived",
  };

  // --- rendering ----------------------------------------------------------

  function renderJourneyList() {
    const list = $("journey-list");
    list.innerHTML = "";
    journeys.forEach((journey) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.className = "journey-btn";
      button.type = "button";
      button.setAttribute("aria-current", journey.id === currentId ? "true" : "false");
      button.innerHTML =
        "<strong></strong><small></small>";
      button.querySelector("strong").textContent = journey.title;
      button.querySelector("small").textContent =
        (STATUS_WORDS[journey.status] || journey.status) +
        " · " + journey.breadcrumb_count + " recorded";
      button.addEventListener("click", () => selectJourney(journey.id));
      li.appendChild(button);
      list.appendChild(li);
    });
  }

  function renderState(journey) {
    const state = journey.state || {};
    $("journey-title").textContent = journey.title;
    $("journey-goal").textContent = journey.goal || "";

    const pill = $("status-pill");
    pill.className = "pill " + (state.status || "ACTIVE");
    pill.textContent = STATUS_WORDS[state.status] || state.status || "";

    $("current-state").textContent = state.current_state || "";
    $("next-action").textContent = state.next_action || "";

    // Always cite where the answer came from.
    const source = state.source || {};
    const parts = [];
    if (state.last_event && state.last_event.summary) {
      parts.push(state.last_event.summary);
    }
    if (source.type) {
      parts.push(SOURCE_LABELS[source.type] || source.type);
    }
    if (typeof state.evidence_count === "number") {
      parts.push(
        state.evidence_count + (state.evidence_count === 1 ? " confirmed record" : " confirmed records")
      );
    }
    $("provenance").textContent = parts.join(" · ");

    // Proactive check-in: the app saying something without being asked. This
    // only ever describes when *you* last recorded something -- never a
    // government processing-time claim (server enforces that; see
    // apps/journeys/state.py compute_staleness).
    const staleness = state.staleness || {};
    const banner = $("staleness-banner");
    banner.hidden = !staleness.is_stale;
    banner.textContent = staleness.message || "";
  }

  /*
   * Closes the loop: what a create/correct/delete actually did, in the
   * citizen's own words, instead of the timeline just silently refreshing.
   */
  function showActionFeedback(change) {
    const el = $("action-feedback");
    if (!change || !change.message) {
      el.hidden = true;
      return;
    }
    el.hidden = false;
    el.textContent = change.message;
  }

  function renderTimeline(rows) {
    const list = $("timeline");
    list.innerHTML = "";
    if (!rows || !rows.length) {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = "Nothing recorded yet. Use “What happened?” to start.";
      list.appendChild(li);
      return;
    }
    rows.forEach((row) => {
      const li = document.createElement("li");

      const when = document.createElement("p");
      when.className = "when";
      when.style.margin = "0";
      when.textContent = formatDate(row.occurred_at);
      li.appendChild(when);

      const what = document.createElement("p");
      what.className = "what";
      what.style.margin = "2px 0 0";
      what.textContent = row.title;
      li.appendChild(what);

      if (row.instruction) {
        const said = document.createElement("p");
        said.className = "said";
        said.textContent = "“" + row.instruction + "”";
        li.appendChild(said);
      }

      const tags = document.createElement("p");
      tags.style.margin = "0";
      [
        row.organization_display,
        CHANNEL_LABELS[row.channel],
        SOURCE_LABELS[row.source_type],
      ].filter(Boolean).forEach((text) => {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = text;
        tags.appendChild(tag);
      });
      li.appendChild(tags);

      // The backend has always supported correcting and deleting a record
      // (§25/§9.1: recalculation on either); this is what actually lets
      // "closes the loop" be seen working in the product, not just the API.
      const rowActions = document.createElement("p");
      rowActions.className = "row-actions";

      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.textContent = "Edit";
      editBtn.setAttribute("aria-label", "Edit: " + row.title);
      editBtn.addEventListener("click", () => startEditBreadcrumb(row.id));
      rowActions.appendChild(editBtn);

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.textContent = "Delete";
      deleteBtn.setAttribute("aria-label", "Delete: " + row.title);
      deleteBtn.addEventListener("click", () => deleteBreadcrumbRow(row.id, row.title));
      rowActions.appendChild(deleteBtn);

      li.appendChild(rowActions);

      list.appendChild(li);
    });
  }

  // --- data ---------------------------------------------------------------

  async function loadJourneys() {
    const body = await api("/journeys/");
    journeys = body.results || [];
    renderJourneyList();
    if (!currentId && journeys.length) {
      await selectJourney(journeys[0].id);
    } else if (!journeys.length) {
      $("journey-title").textContent = "No journeys yet";
      $("journey-goal").textContent = "Create one to get started.";
      renderTimeline([]);
    }
  }

  async function loadOrganizations() {
    const body = await api("/organizations/");
    organizations = body.results || [];
    const select = $("f-org");
    select.innerHTML = "";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "Not sure / not listed";
    select.appendChild(blank);
    organizations.forEach((org) => {
      const option = document.createElement("option");
      option.value = org.name;
      option.textContent = org.short_name || org.name;
      select.appendChild(option);
    });
  }

  async function selectJourney(id) {
    currentId = id;
    hideAll();
    $("action-feedback").hidden = true; // feedback is per-journey, not global
    const journey = await api("/journeys/" + id + "/");
    renderState(journey);
    renderTimeline(journey.timeline);
    renderJourneyList();
  }

  async function refresh() {
    const journey = await api("/journeys/" + currentId + "/");
    renderState(journey);
    renderTimeline(journey.timeline);
    await loadJourneys();
  }

  // --- actions ------------------------------------------------------------

  $("new-journey-btn").addEventListener("click", () => {
    $("nj-text").value = "";
    show("new-journey-panel");
  });
  $("nj-cancel").addEventListener("click", hideAll);

  $("nj-create").addEventListener("click", async (event) => {
    const text = $("nj-text").value.trim();
    if (!text) return;
    event.target.disabled = true;          // no double-submit (§25)
    try {
      const body = await api("/journeys/", {
        method: "POST",
        body: JSON.stringify({ description: text }),
      });
      if (body.type === "OUT_OF_SCOPE") {
        alert(body.message);
        return;
      }
      hideAll();
      await loadJourneys();
      await selectJourney(body.id);
    } finally {
      event.target.disabled = false;
    }
  });

  $("btn-what").addEventListener("click", () => {
    $("add-text").value = "";
    show("add-panel");
  });
  $("add-cancel").addEventListener("click", hideAll);
  $("review-cancel").addEventListener("click", hideAll);
  $("stuck-close").addEventListener("click", hideAll);
  $("who-close").addEventListener("click", hideAll);
  $("handoff-close").addEventListener("click", hideAll);

  $("add-interpret").addEventListener("click", async (event) => {
    const text = $("add-text").value.trim();
    if (!text) return;
    event.target.disabled = true;
    try {
      const body = await api(
        "/journeys/" + currentId + "/breadcrumbs/interpret/",
        { method: "POST", body: JSON.stringify({ text: text }) }
      );

      if (body.type === "OUT_OF_SCOPE") {
        alert(body.message);
        return;
      }

      presentDraft(body);
      show("review-panel");
    } finally {
      event.target.disabled = false;
    }
  });

  /*
   * "AI understands and reflects it back."
   *
   * The common, high-confidence case is one tap: the paraphrase is the
   * headline, "Yes, that's right" saves the AI's fields verbatim, and the full
   * field-by-field form is one click away rather than the default view. A
   * draft the system itself flagged as needing clarification skips straight
   * to the form instead -- offering a fake one-tap confirm for something it
   * already said it wasn't sure about would be dishonest.
   */
  function presentDraft(body) {
    const draft = body.draft;
    lastDraft = draft;
    lastRawText = body.raw_text;
    resetReviewPanelToCreateMode();

    $("review-paraphrase").textContent = draft.paraphrase || "";
    $("review-raw").textContent = "“" + body.raw_text + "”";
    $("review-raw-form").textContent = "“" + body.raw_text + "”";
    fillFormFields(draft);

    const notice = $("review-notice");
    const messages = [];
    if (body.needs_clarification && body.clarification_question) {
      messages.push(body.clarification_question);
    }
    if (body.ai && body.ai.degraded) {
      messages.push(
        "AI was unavailable, so this was organized without it. Please check it."
      );
    }
    notice.hidden = messages.length === 0;
    notice.textContent = messages.join(" ");

    // A confident draft gets the one-tap path; a flagged one goes straight to
    // the form, because it already told us it wasn't sure (§14 Rule 4).
    if (body.needs_clarification) {
      showReviewFormView();
    } else {
      showReviewConfirmView();
    }
  }

  function showReviewConfirmView() {
    $("review-confirm-view").hidden = false;
    $("review-form-view").hidden = true;
  }

  function showReviewFormView() {
    $("review-confirm-view").hidden = true;
    $("review-form-view").hidden = false;
  }

  function fillFormFields(draft) {
    $("f-kind").value = draft.kind;
    $("f-channel").value = draft.channel;
    $("f-org").value = draft.organization || "";
    $("f-date").value = draft.occurred_on || "";
    $("f-status").value = draft.reported_status;
    $("f-next").value = draft.suggested_next_action;
    $("f-title").value = draft.title || "";
    $("f-instruction").value = draft.instruction || "";
  }

  function draftToPayload(draft, rawText) {
    const payload = {
      kind: draft.kind,
      channel: draft.channel,
      title: draft.title || "Recorded event",
      raw_text: rawText || "",
      organization_name: draft.organization || "",
      reported_status: draft.reported_status,
      instruction: draft.instruction || "",
      suggested_next_action: draft.suggested_next_action,
      reference: draft.reference || "",
      extractor: draft.extractor || "",
      // Idempotency token, so a retry cannot duplicate the record (§25).
      request_id: "demo-" + Date.now(),
    };
    if (draft.occurred_on) payload.occurred_on = draft.occurred_on;
    return payload;
  }

  function formToPayload() {
    const payload = {
      kind: $("f-kind").value,
      channel: $("f-channel").value,
      title: $("f-title").value || "Recorded event",
      organization_name: $("f-org").value,
      reported_status: $("f-status").value,
      instruction: $("f-instruction").value,
      suggested_next_action: $("f-next").value,
    };
    if ($("f-date").value) payload.occurred_on = $("f-date").value;
    return payload;
  }

  $("review-yes").addEventListener("click", async (event) => {
    event.target.disabled = true;
    try {
      const payload = draftToPayload(lastDraft, lastRawText);
      const body = await api("/journeys/" + currentId + "/breadcrumbs/", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (body.warnings && body.warnings.length) {
        alert(body.warnings[0].message);
      }
      hideAll();
      showActionFeedback(body.change);
      await refresh();
    } finally {
      event.target.disabled = false;
    }
  });

  $("review-edit-details").addEventListener("click", showReviewFormView);
  $("review-form-cancel").addEventListener("click", hideAll);

  $("review-confirm").addEventListener("click", async (event) => {
    event.target.disabled = true;
    try {
      let body;
      if (editingBreadcrumbId) {
        const payload = formToPayload();
        body = await api("/breadcrumbs/" + editingBreadcrumbId + "/", {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
      } else {
        const payload = Object.assign(formToPayload(), {
          raw_text: lastRawText,
          reference: (lastDraft && lastDraft.reference) || "",
          extractor: (lastDraft && lastDraft.extractor) || "",
          request_id: "demo-" + Date.now(),
        });
        body = await api("/journeys/" + currentId + "/breadcrumbs/", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (body.warnings && body.warnings.length) {
          alert(body.warnings[0].message);
        }
      }
      hideAll();
      showActionFeedback(body.change);
      await refresh();
    } finally {
      event.target.disabled = false;
    }
  });

  /* Editing (or deleting) an existing timeline record -- the other half of
   * "closes the loop": the backend has always supported this (PATCH/DELETE on
   * /breadcrumbs/{id}/), but the demo UI never exposed it, so there was no way
   * to actually see a correction's effect on the journey without the API. */
  async function startEditBreadcrumb(breadcrumbId) {
    const list = await api("/journeys/" + currentId + "/breadcrumbs/");
    const record = (list.results || []).find((r) => r.id === breadcrumbId);
    if (!record) return;

    editingBreadcrumbId = breadcrumbId;
    $("review-h").textContent = "Update this record";
    $("review-confirm").textContent = "Save correction";
    $("review-note").hidden = true; // create-only affordance

    $("review-notice").hidden = true;
    $("review-raw-form").textContent = record.raw_text
      ? "“" + record.raw_text + "”"
      : "(no original wording recorded)";
    fillFormFields({
      kind: record.kind,
      channel: record.channel,
      organization: record.organization ? record.organization.name : "",
      occurred_on: (record.occurred_at || "").slice(0, 10),
      reported_status: record.reported_status,
      suggested_next_action: record.suggested_next_action,
      title: record.title,
      instruction: record.instruction,
    });

    showReviewFormView();
    show("review-panel");
  }

  async function deleteBreadcrumbRow(breadcrumbId, title) {
    if (!window.confirm('Delete "' + title + '" from your timeline?')) return;
    const body = await api("/breadcrumbs/" + breadcrumbId + "/", {
      method: "DELETE",
    });
    showActionFeedback(body.change);
    await refresh();
  }

  async function saveNote(text, button) {
    if (!text) return;
    button.disabled = true;
    try {
      const body = await api("/journeys/" + currentId + "/notes/", {
        method: "POST",
        body: JSON.stringify({ text: text, request_id: "demo-note-" + Date.now() }),
      });
      hideAll();
      showActionFeedback(body.change);
      await refresh();
    } finally {
      button.disabled = false;
    }
  }

  // The escape hatch, on both steps: nothing the citizen typed is ever lost.
  $("add-note").addEventListener("click", (event) =>
    saveNote($("add-text").value.trim(), event.target)
  );
  $("review-note").addEventListener("click", (event) =>
    saveNote(lastRawText, event.target)
  );

  $("btn-stuck").addEventListener("click", async (event) => {
    event.target.disabled = true;
    try {
      const body = await api("/journeys/" + currentId + "/stuck/");
      $("stuck-summary").textContent = body.summary || "";
      $("stuck-unresolved").textContent =
        body.unresolved_issue || "Nothing appears unresolved.";
      $("stuck-instruction").textContent =
        body.latest_instruction || "None recorded.";

      const generated = $("stuck-generated");
      generated.hidden = !(body.ai && body.ai.summary_is_generated);
      generated.textContent =
        "This wording was generated from your records. The dates, " +
        "organizations and instructions come from what you recorded.";

      const org = $("stuck-org");
      org.innerHTML = "";
      const heading = document.createElement("h2");
      heading.textContent = "Who is responsible";
      org.appendChild(heading);
      const p = document.createElement("p");
      if (body.responsible_organization) {
        p.textContent = body.responsible_organization.name;
        if (body.organization_message) {
          const note = document.createElement("p");
          note.className = "muted";
          note.textContent = body.organization_message;
          org.appendChild(p);
          org.appendChild(note);
        } else {
          org.appendChild(p);
        }
      } else {
        p.textContent = body.organization_message;
        org.appendChild(p);
      }

      const sources = $("stuck-sources");
      sources.innerHTML = "";
      (body.official_sources || []).forEach((source) => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = source.url;
        a.textContent = source.title;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        li.appendChild(a);
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = "Official";
        li.appendChild(tag);
        const checked = document.createElement("span");
        checked.className = "muted";
        checked.textContent = " Link checked " + formatDate(source.verified_at);
        li.appendChild(checked);
        sources.appendChild(li);
      });

      show("stuck-panel");
    } finally {
      event.target.disabled = false;
    }
  });

  $("btn-who").addEventListener("click", async (event) => {
    event.target.disabled = true;
    try {
      const body = await api(
        "/journeys/" + currentId + "/responsible-organization/"
      );
      const target = $("who-body");
      target.innerHTML = "";

      if (body.responsible_organization) {
        const name = document.createElement("p");
        name.style.fontSize = "1.15rem";
        name.innerHTML = "<strong></strong>";
        name.querySelector("strong").textContent =
          body.responsible_organization.name;
        target.appendChild(name);

        const tag = document.createElement("p");
        tag.innerHTML = '<span class="tag">From the curated directory</span>';
        target.appendChild(tag);

        // The honest answer: sometimes nobody needs contacting (§21).
        if (body.message) {
          const message = document.createElement("p");
          message.textContent = body.message;
          target.appendChild(message);
        }

        const link = document.createElement("p");
        const a = document.createElement("a");
        a.href = body.responsible_organization.official_url;
        a.textContent = "Open the official website";
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        link.appendChild(a);
        target.appendChild(link);
      } else {
        const message = document.createElement("p");
        message.textContent = body.message;
        target.appendChild(message);
      }
      show("who-panel");
    } finally {
      event.target.disabled = false;
    }
  });

  $("btn-handoff").addEventListener("click", async (event) => {
    event.target.disabled = true;
    try {
      const body = await api("/journeys/" + currentId + "/handoff/", {
        method: "POST",
        body: JSON.stringify({}),
      });
      $("handoff-text").textContent = body.summary || "";
      const generated = $("handoff-generated");
      generated.hidden = !(body.ai && body.ai.summary_is_generated);
      generated.textContent =
        "Wording generated from your records. Every date and instruction comes " +
        "from what you recorded.";
      $("handoff-copied").hidden = true;
      show("handoff-panel");
    } finally {
      event.target.disabled = false;
    }
  });

  $("handoff-copy").addEventListener("click", async () => {
    const text = $("handoff-text").textContent;
    try {
      await navigator.clipboard.writeText(text);
      $("handoff-copied").hidden = false;
    } catch (err) {
      // Clipboard access can be blocked; select the text so it stays copyable.
      const range = document.createRange();
      range.selectNodeContents($("handoff-text"));
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }
  });

  // --- boot ---------------------------------------------------------------

  (async function start() {
    try {
      await loadOrganizations();
      await loadJourneys();
    } catch (err) {
      $("journey-title").textContent = "Could not load";
      $("journey-goal").textContent =
        "The API did not respond. Is the server running?";
    }
  })();
})();
