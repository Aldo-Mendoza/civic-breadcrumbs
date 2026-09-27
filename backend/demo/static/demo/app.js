(function () {
  "use strict";

  const API = "/api/v1";
  const $ = (id) => document.getElementById(id);
  const state = {
    journeys: [],
    organizations: [],
    current: null,
    draft: null,
    rawText: "",
    editing: null,
    activeGuideStep: null,
    csrfToken: "",
    accessToken: "",
    auth0: null,
    authMode: "guest",
  };
  let confirmResolveFn = null;

  const STATUS_LABELS = {
    ACTIVE: "Active",
    WAITING: "Waiting",
    ACTION_REQUIRED: "Action needed",
    COMPLETED: "Complete",
    ARCHIVED: "Archived",
  };
  const SOURCE_LABELS = {
    USER_REPORTED: "Recorded by you",
    OFFICIAL: "Official source",
    COMMUNITY: "Community source",
    AI_INTERPRETATION: "AI interpretation",
  };
  const KIND_LABELS = {
    INTERACTION: "Interaction",
    ACTION: "Action",
    STATUS_UPDATE: "Status update",
    DOCUMENT: "Document",
    SOURCE: "Official source",
    NOTE: "Note",
  };
  const GUIDE_STATUS_LABELS = {
    NOT_STARTED: "Not started",
    IN_PROGRESS: "In progress",
    COMPLETED: "Complete",
  };

  function escapeHTML(value) {
    const node = document.createElement("div");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
  }

  function formatDate(value) {
    if (!value) return "Date not specified";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function toast(message) {
    const el = $("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { el.hidden = true; }, 4200);
  }

  async function api(path, options) {
    const supplied = options || {};
    const headers = Object.assign({ "Content-Type": "application/json" }, supplied.headers || {});
    if (state.csrfToken) headers["X-CSRFToken"] = state.csrfToken;
    if (state.accessToken) headers.Authorization = "Bearer " + state.accessToken;
    const response = await fetch(API + path, Object.assign({ credentials: "include" }, supplied, { headers }));
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = body.error || {};
      const failure = new Error(error.message || "That request could not be completed.");
      failure.code = error.code || "REQUEST_FAILED";
      failure.body = body;
      failure.status = response.status;
      throw failure;
    }
    return body;
  }

  function openModal(id) {
    const shell = $(id);
    shell.hidden = false;
    document.body.style.overflow = "hidden";
    const focusable = shell.querySelector("button, input, textarea, select");
    if (focusable) setTimeout(() => focusable.focus(), 0);
  }

  function closeModal(id) {
    $(id).hidden = true;
    if (!document.querySelector(".modal-shell:not([hidden])")) document.body.style.overflow = "";
  }

  function confirmModal(options) {
    const opts = options || {};
    $("confirm-modal-title").textContent = opts.title || "Please confirm";
    $("confirm-modal-message").textContent = opts.message || "";
    const confirmButton = $("confirm-modal-confirm");
    confirmButton.textContent = opts.confirmLabel || "Confirm";
    confirmButton.className = opts.danger ? "button danger" : "button primary";
    $("confirm-modal-cancel").textContent = opts.cancelLabel || "Cancel";
    openModal("confirm-modal");
    return new Promise((resolve) => { confirmResolveFn = resolve; });
  }

  function resolveConfirm(result) {
    closeModal("confirm-modal");
    if (confirmResolveFn) {
      const resolve = confirmResolveFn;
      confirmResolveFn = null;
      resolve(result);
    }
  }

  function showScreen(name) {
    $("landing-screen").hidden = name !== "landing";
    $("create-screen").hidden = name !== "create";
    $("journey-screen").hidden = name !== "journey";
    $("completion-screen").hidden = name !== "completion";
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function showLanding() {
    $("landing-signin").hidden = state.authMode !== "guest";
    showScreen("landing");
  }

  function openSidebar() {
    $("sidebar").classList.add("open");
    $("sidebar").setAttribute("aria-hidden", "false");
    $("sidebar").removeAttribute("inert");
    $("sidebar-scrim").hidden = false;
    $("menu-button").setAttribute("aria-expanded", "true");
  }

  function closeSidebar() {
    $("sidebar").classList.remove("open");
    $("sidebar").setAttribute("aria-hidden", "true");
    $("sidebar").setAttribute("inert", "");
    $("sidebar-scrim").hidden = true;
    $("menu-button").setAttribute("aria-expanded", "false");
  }

  async function setupAuth() {
    const csrfResponse = await fetch(API + "/auth/csrf/", { credentials: "include" });
    state.csrfToken = (await csrfResponse.json()).csrf_token || "";
    const config = await fetch(API + "/auth/config/", { credentials: "include" }).then((r) => r.json());
    if (config.enabled && window.auth0 && typeof window.auth0.createAuth0Client === "function") {
      state.auth0 = await window.auth0.createAuth0Client({
        domain: config.domain,
        clientId: config.client_id,
        cacheLocation: "memory",
        authorizationParams: {
          audience: config.audience,
          redirect_uri: window.location.origin + window.location.pathname,
        },
      });
      if (location.search.includes("error=")) {
        const params = new URLSearchParams(location.search);
        toast(params.get("error_description") || "Sign-in with Google could not be completed.");
        history.replaceState({}, document.title, location.pathname);
      } else if (location.search.includes("code=") && location.search.includes("state=")) {
        await state.auth0.handleRedirectCallback();
        history.replaceState({}, document.title, location.pathname);
      }
      if (await state.auth0.isAuthenticated()) {
        state.accessToken = await state.auth0.getTokenSilently();
        try {
          const migrated = await api("/auth/migrate-guest/", { method: "POST", body: "{}" });
          if (migrated.status === "migrated" && migrated.migrated_count) toast("Your guest Journey is now saved to your account.");
        } catch (error) {
          if (error.code === "GUEST_MIGRATION_BLOCKED") toast(error.message);
        }
      }
    }
    const status = await api("/auth/status/");
    state.authMode = status.mode;
    state.journeyLimit = status.journey_limit;
  }

  function relativeDay(value) {
    if (!value) return "";
    const diffDays = Math.round((Date.now() - new Date(value).getTime()) / 86400000);
    if (diffDays <= 0) return "Updated today";
    if (diffDays === 1) return "Updated yesterday";
    if (diffDays < 7) return `Updated ${diffDays} days ago`;
    return "Updated " + formatDate(value);
  }

  const ACTIVE_STATUSES = ["ACTIVE", "WAITING", "ACTION_REQUIRED"];

  function renderSidebar() {
    const list = $("journey-list");
    const empty = $("sidebar-empty");
    list.innerHTML = "";
    if (empty) empty.hidden = state.journeys.length > 0;

    state.journeys.forEach((journey) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.className = state.current && state.current.id === journey.id ? "active" : "";
      const goalSnippet = journey.goal && journey.goal !== journey.title ? escapeHTML(journey.goal) : "";
      button.innerHTML = `
        <strong>${escapeHTML(journey.title)}</strong>
        ${goalSnippet ? `<span class="sidebar-goal">${goalSnippet}</span>` : ""}
        <small><span class="status-pill ${escapeHTML(journey.status)}">${escapeHTML(STATUS_LABELS[journey.status] || journey.status)}</span> ${escapeHTML(relativeDay(journey.updated_at))}</small>`;
      button.addEventListener("click", async () => { closeSidebar(); await selectJourney(journey.id); });
      li.appendChild(button);
      list.appendChild(li);
    });

    const quota = $("sidebar-quota");
    if (quota) {
      const activeCount = state.journeys.filter((journey) => ACTIVE_STATUSES.includes(journey.status)).length;
      const limit = state.journeyLimit;
      quota.textContent = limit ? `${activeCount} of ${limit} active journeys used` : "";
      quota.hidden = !limit;
    }
  }

  async function loadJourneys() {
    const body = await api("/journeys/");
    state.journeys = body.results || [];
    renderSidebar();
    return state.journeys;
  }

  async function selectJourney(id, forceJourneyScreen) {
    state.current = await api("/journeys/" + id + "/");
    renderJourney();
    renderSidebar();
    if (!forceJourneyScreen && state.current.state.status === "COMPLETED") renderCompletion();
    else showScreen("journey");
  }

  function renderJourney() {
    const journey = state.current;
    if (!journey) return;
    $("journey-title").textContent = journey.title;
    $("journey-goal").textContent = journey.goal;
    $("current-state").textContent = journey.state.current_state;
    $("next-action").textContent = journey.state.next_action || "No next action has been recorded.";
    const status = $("status-pill");
    status.className = "status-pill " + journey.state.status;
    status.textContent = STATUS_LABELS[journey.state.status] || journey.state.status;
    const count = (journey.timeline || []).length;
    $("record-count").textContent = count + (count === 1 ? " recorded event" : " recorded events");
    const source = journey.state.source || {};
    $("state-source").textContent = source.type ? (SOURCE_LABELS[source.type] || source.type) + " • derived from your confirmed timeline" : "Derived from confirmed records only";
    $("record-context").textContent = journey.title + " • " + (STATUS_LABELS[journey.state.status] || journey.state.status);
    renderGuide();

    const timeline = $("timeline-list");
    timeline.innerHTML = "";
    const rows = (journey.timeline || []).slice().reverse();
    $("empty-timeline").hidden = rows.length > 0;
    rows.forEach((row, index) => {
      const li = document.createElement("li");
      li.className = "timeline-item";
      li.tabIndex = 0;
      li.innerHTML = `
        <span class="step-orb">${rows.length - index}</span>
        <div class="timeline-copy"><strong>${escapeHTML(row.title)}</strong><p>${escapeHTML(formatDate(row.occurred_at))}${row.organization_display ? " • " + escapeHTML(row.organization_display) : ""}</p></div>
        <span class="event-status">${escapeHTML(KIND_LABELS[row.kind] || row.kind)}</span><span class="chevron">›</span>`;
      const open = () => openExistingEvent(row.id);
      li.addEventListener("click", open);
      li.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } });
      timeline.appendChild(li);
    });
  }

  function renderGuide() {
    const guide = state.current && state.current.guide;
    const list = $("guide-step-list");
    list.innerHTML = "";
    if (!guide) {
      $("guide-summary").textContent = "No suggested guide is available for this Journey yet.";
      $("guide-progress-label").textContent = "0 of 0 steps complete";
      $("guide-progress-bar").style.width = "0%";
      $("guide-clarification").hidden = true;
      return;
    }
    const steps = guide.steps || [];
    const completed = steps.filter((step) => step.status === "COMPLETED").length;
    $("guide-summary").textContent = guide.summary;
    $("guide-progress-label").textContent = `${completed} of ${steps.length} steps complete`;
    $("guide-progress-bar").style.width = steps.length ? `${Math.round((completed / steps.length) * 100)}%` : "0%";
    const clarification = $("guide-clarification");
    clarification.hidden = !guide.needs_clarification;
    clarification.textContent = guide.needs_clarification ? `One detail will improve this guide: ${guide.clarification_question}` : "";
    steps.forEach((step) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "guide-step" + (step.status === "IN_PROGRESS" ? " current" : "");
      button.innerHTML = `
        <span class="step-orb ${step.status === "COMPLETED" ? "complete" : ""}">${step.position}</span>
        <span class="guide-step-copy"><strong>${escapeHTML(step.title)}</strong><p>${escapeHTML(step.description)}</p></span>
        <span class="guide-step-status ${escapeHTML(step.status)}">${escapeHTML(GUIDE_STATUS_LABELS[step.status] || step.status)}</span>
        <span class="chevron">›</span>`;
      button.addEventListener("click", () => openGuideStep(step));
      li.appendChild(button);
      list.appendChild(li);
    });
  }

  /*
   * A link-preview style card for a curated official source: site name,
   * description, and the bare URL as its own visible line -- the same shape
   * as a normal chat-app link preview, so a citizen recognizes it as a real,
   * verifiable government page rather than inline blue text. Built entirely
   * from our own curated, human-verified fields (title/description/url); this
   * never fetches live metadata from the target site (CLAUDE.md §9.5).
   */
  function siteNameFor(url) {
    try {
      const host = new URL(url).hostname.replace(/^www\./, "");
      return host.endsWith("canada.ca") ? "Canada.ca" : host.endsWith("ontario.ca") ? "Ontario.ca" : host;
    } catch (error) {
      return "Official source";
    }
  }

  function renderSourceCard(container, source, organization) {
    if (!source) {
      container.hidden = true;
      container.innerHTML = "";
      return;
    }
    container.hidden = false;
    const siteName = (organization && (organization.short_name || organization.name)) || siteNameFor(source.url);
    const verified = source.verified_at ? `Link checked ${formatDate(source.verified_at)}` : "Curated official source";
    container.innerHTML = `
      <div class="source-preview">
        <p class="source-eyebrow">${escapeHTML(siteName)}</p>
        <strong>${escapeHTML(source.title)}</strong>
        <p>${escapeHTML(source.description || "Check the current official instructions before acting.")}</p>
        <a href="${escapeHTML(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(source.url)}</a>
        <span class="source-verified">${escapeHTML(verified)}</span>
      </div>`;
  }

  function openGuideStep(step) {
    state.activeGuideStep = step;
    $("guide-step-position").textContent = `Step ${step.position} of ${(state.current.guide.steps || []).length} • ${GUIDE_STATUS_LABELS[step.status] || step.status}`;
    $("guide-step-title").textContent = step.title;
    $("guide-step-description").textContent = step.description;
    renderSourceCard($("guide-step-source"), step.official_source, step.organization);
    $("complete-guide-step").disabled = step.status === "COMPLETED";
    $("complete-guide-step").textContent = step.status === "COMPLETED" ? "Step complete" : "Mark step complete →";
    openModal("guide-step-modal");
  }

  function renderCompletion() {
    const journey = state.current;
    $("completion-label").textContent = journey.title;
    const list = $("completion-list");
    list.innerHTML = "";
    const completedSteps = ((journey.guide && journey.guide.steps) || []).filter((step) => step.status === "COMPLETED");
    completedSteps.forEach((step) => {
      const div = document.createElement("div");
      div.className = "completion-row";
      div.innerHTML = `<span>✓</span><strong>${escapeHTML(step.title)}</strong>`;
      list.appendChild(div);
    });
    showScreen("completion");
  }

  async function refreshCurrent(message) {
    if (!state.current) return;
    await loadJourneys();
    state.current = await api("/journeys/" + state.current.id + "/");
    renderJourney();
    if (message) {
      $("action-feedback").textContent = message;
      $("action-feedback").hidden = false;
    }
    if (state.current.state.status === "COMPLETED") renderCompletion();
  }

  function startNewGoal() {
    state.current = null;
    $("goal-form").reset();
    showScreen("create");
    closeSidebar();
    setTimeout(() => $("goal-input").focus(), 0);
  }

  function resetRecordModal() {
    state.draft = null;
    state.rawText = "";
    state.editing = null;
    state.activeGuideStep = null;
    $("event-text").value = "";
    $("record-input-stage").hidden = false;
    $("record-review-stage").hidden = true;
    $("record-edit-stage").hidden = true;
    $("delete-event").hidden = true;
    $("details-heading").textContent = "Edit the event";
  }

  function openRecordModal(guideStep) {
    resetRecordModal();
    state.activeGuideStep = guideStep || null;
    if (guideStep) $("record-context").textContent = `${state.current.title} • Guide step ${guideStep.position}: ${guideStep.title}`;
    else $("record-context").textContent = state.current.title + " • " + (STATUS_LABELS[state.current.state.status] || state.current.state.status);
    openModal("record-modal");
    $("event-text").focus();
  }

  function fillDetails(data) {
    $("detail-title").value = data.title || "";
    $("detail-kind").value = data.kind || "NOTE";
    $("detail-channel").value = data.channel || "UNKNOWN";
    $("detail-org").value = data.organization || data.organization_name || "";
    $("detail-status").value = data.reported_status || "UNKNOWN";
    $("detail-date").value = data.occurred_on || (data.occurred_at ? String(data.occurred_at).slice(0, 10) : today());
    $("detail-instruction").value = data.instruction || "";
  }

  function showDraft(draft, rawText, meta) {
    state.draft = draft;
    state.rawText = rawText;
    $("draft-paraphrase").textContent = draft.paraphrase || draft.title || "Review the details before saving.";
    $("draft-original").textContent = "You said: “" + rawText + "”";
    const tags = [KIND_LABELS[draft.kind] || draft.kind, draft.channel !== "UNKNOWN" ? draft.channel.replaceAll("_", " ") : "", draft.organization || ""].filter(Boolean);
    $("draft-tags").innerHTML = tags.map((tag) => `<span>${escapeHTML(tag)}</span>`).join("");
    const notice = $("draft-notice");
    notice.hidden = !(draft.needs_clarification || (meta && meta.degraded));
    notice.textContent = draft.needs_clarification ? (draft.clarification_question || "Please review the details carefully.") : "Automatic interpretation was unavailable, so a rules-based draft was prepared.";
    $("record-input-stage").hidden = true;
    $("record-review-stage").hidden = false;
  }

  async function interpretEvent() {
    const text = $("event-text").value.trim();
    if (!text) return;
    const button = $("interpret-event");
    button.disabled = true;
    try {
      const result = await api(`/journeys/${state.current.id}/breadcrumbs/interpret/`, { method: "POST", body: JSON.stringify({ text }) });
      if (result.type === "OUT_OF_SCOPE") { toast(result.message); return; }
      showDraft(result.draft, result.raw_text, result.ai);
    } catch (error) { toast(error.message); }
    finally { button.disabled = false; }
  }

  function draftPayload() {
    const draft = state.draft;
    return {
      kind: draft.kind,
      channel: draft.channel,
      title: draft.title || "Recorded event",
      raw_text: state.rawText,
      organization_name: draft.organization || "",
      occurred_on: draft.occurred_on || today(),
      reported_status: draft.reported_status || "UNKNOWN",
      instruction: draft.instruction || "",
      suggested_next_action: draft.suggested_next_action || "NONE",
      reference: draft.reference || "",
      confidence: draft.confidence,
      extractor: draft.extractor || "",
      request_id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
      guide_step_id: state.activeGuideStep ? state.activeGuideStep.id : null,
    };
  }

  async function confirmDraft() {
    const button = $("confirm-event");
    button.disabled = true;
    try {
      const result = await api(`/journeys/${state.current.id}/breadcrumbs/`, { method: "POST", body: JSON.stringify(draftPayload()) });
      closeModal("record-modal");
      await refreshCurrent(result.change ? result.change.message : "Added to your Journey.");
    } catch (error) { toast(error.message); }
    finally { button.disabled = false; }
  }

  async function savePlainNote() {
    const text = $("event-text").value.trim();
    if (!text) return;
    const button = $("save-note");
    button.disabled = true;
    try {
      const result = await api(`/journeys/${state.current.id}/notes/`, { method: "POST", body: JSON.stringify({ text, guide_step_id: state.activeGuideStep ? state.activeGuideStep.id : null, request_id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) }) });
      closeModal("record-modal");
      await refreshCurrent(result.change ? result.change.message : "Note saved.");
    } catch (error) { toast(error.message); }
    finally { button.disabled = false; }
  }

  function openExistingEvent(id) {
    const event = (state.current.breadcrumbs || []).find((item) => item.id === id);
    if (!event) return;
    resetRecordModal();
    state.editing = event;
    fillDetails(event);
    $("record-input-stage").hidden = true;
    $("record-edit-stage").hidden = false;
    $("delete-event").hidden = false;
    $("details-heading").textContent = "Review recorded event";
    openModal("record-modal");
  }

  async function saveDetails(event) {
    event.preventDefault();
    const payload = {
      title: $("detail-title").value.trim(), kind: $("detail-kind").value,
      channel: $("detail-channel").value, organization_name: $("detail-org").value,
      reported_status: $("detail-status").value, occurred_on: $("detail-date").value,
      instruction: $("detail-instruction").value.trim(),
    };
    try {
      if (state.editing) {
        const result = await api(`/breadcrumbs/${state.editing.id}/`, { method: "PATCH", body: JSON.stringify(payload) });
        closeModal("record-modal");
        await refreshCurrent(result.change ? result.change.message : "Event updated.");
      } else {
        const full = Object.assign(draftPayload(), payload);
        const result = await api(`/journeys/${state.current.id}/breadcrumbs/`, { method: "POST", body: JSON.stringify(full) });
        closeModal("record-modal");
        await refreshCurrent(result.change ? result.change.message : "Event saved.");
      }
    } catch (error) { toast(error.message); }
  }

  async function deleteEvent() {
    if (!state.editing) return;
    const confirmed = await confirmModal({
      title: "Remove this event?",
      message: "This removes it from your Journey record. This can't be undone.",
      confirmLabel: "Remove event",
      danger: true,
    });
    if (!confirmed) return;
    try {
      const result = await api(`/breadcrumbs/${state.editing.id}/`, { method: "DELETE" });
      closeModal("record-modal");
      await refreshCurrent(result.change ? result.change.message : "Event removed.");
    } catch (error) { toast(error.message); }
  }

  async function showHelp() {
    openModal("help-modal");
    $("help-context").textContent = state.current.title + " • Your current recorded state";
    $("help-summary").innerHTML = '<div class="help-block"><p>Loading your saved context…</p></div>';
    try {
      const body = await api(`/journeys/${state.current.id}/stuck/?polish=false`);
      const org = body.responsible_organization;
      $("help-summary").innerHTML = `
        <div class="help-block"><span>Where you left off</span><p>${escapeHTML(body.summary || state.current.state.current_state)}</p></div>
        <div class="help-block"><span>Still unresolved</span><p>${escapeHTML(body.unresolved_issue || "No unresolved issue is recorded.")}</p></div>
        <div class="help-block"><span>Last recorded instruction</span><p>${escapeHTML(body.latest_instruction || "No instruction has been recorded.")}</p></div>
        <div class="help-block"><span>Responsible organization</span><p>${escapeHTML(org ? (org.short_name || org.name) : "Not enough verified information yet")}</p></div>`;
    } catch (error) { $("help-summary").innerHTML = `<div class="notice">${escapeHTML(error.message)}</div>`; }
  }

  function showInfo(title, eyebrow, html) {
    $("info-title").textContent = title;
    $("info-eyebrow").textContent = eyebrow;
    $("info-content").innerHTML = html;
    openModal("info-modal");
  }

  async function showOrganization() {
    showInfo("Finding the responsible organization…", "Verified directory", "<p>Loading…</p>");
    try {
      const body = await api(`/journeys/${state.current.id}/responsible-organization/`);
      if (!body.responsible_organization) { showInfo("We don’t have enough verified information", "Who handles this?", `<p>${escapeHTML(body.message)}</p>`); return; }
      const org = body.responsible_organization;
      const sources = (body.official_sources || []).map((source) => `<li><a href="${escapeHTML(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(source.title)}</a></li>`).join("");
      showInfo(org.short_name || org.name, "Responsible organization", `<p>${escapeHTML(body.message || body.basis || "Matched from the curated directory.")}</p><p><a href="${escapeHTML(org.official_url)}" target="_blank" rel="noopener noreferrer">Open official website ↗</a></p>${sources ? `<h3>Official sources</h3><ul class="source-list">${sources}</ul>` : ""}`);
    } catch (error) { showInfo("Could not load the directory", "Who handles this?", `<p>${escapeHTML(error.message)}</p>`); }
  }

  async function showHandoff() {
    showInfo("Preparing your handoff…", "Case summary", "<p>Building a summary from confirmed records only…</p>");
    try {
      const body = await api(`/journeys/${state.current.id}/handoff/`, { method: "POST", body: JSON.stringify({ polish: false }) });
      showInfo("Hand this to the next person", "Case summary", `<pre class="summary-text" id="handoff-summary">${escapeHTML(body.summary)}</pre><p><button class="button primary" id="copy-handoff">Copy summary</button></p>`);
      $("copy-handoff").addEventListener("click", async () => { await navigator.clipboard.writeText(body.summary); toast("Handoff copied."); });
    } catch (error) { showInfo("Could not prepare the handoff", "Case summary", `<p>${escapeHTML(error.message)}</p>`); }
  }

  async function markComplete() {
    const confirmed = await confirmModal({
      title: "Mark this Journey complete?",
      message: "This updates your personal record only — it does not claim that a government application was approved.",
      confirmLabel: "Mark complete",
    });
    if (!confirmed) return;
    try {
      const payload = {
        kind: "STATUS_UPDATE", channel: "OTHER", title: "Journey marked complete",
        raw_text: "I completed this journey.", reported_status: "RESOLVED",
        suggested_next_action: "NONE", occurred_on: today(),
        request_id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
      };
      await api(`/journeys/${state.current.id}/breadcrumbs/`, { method: "POST", body: JSON.stringify(payload) });
      await refreshCurrent();
    } catch (error) { toast(error.message); }
  }

  async function completeGuideStep() {
    const step = state.activeGuideStep;
    if (!step || step.status === "COMPLETED") return;
    const button = $("complete-guide-step");
    button.disabled = true;
    try {
      await api(`/guide-steps/${step.id}/complete/`, { method: "POST", body: "{}" });
      closeModal("guide-step-modal");
      await refreshCurrent(`Step ${step.position} was marked complete and added to your record.`);
    } catch (error) { toast(error.message); }
    finally { button.disabled = false; }
  }

  async function editJourney() {
    const title = prompt("Journey title", state.current.title);
    if (title === null) return;
    const goal = prompt("What are you trying to accomplish?", state.current.goal);
    if (goal === null) return;
    try {
      await api(`/journeys/${state.current.id}/`, { method: "PATCH", body: JSON.stringify({ title, goal }) });
      await refreshCurrent("Your goal was updated.");
    } catch (error) { toast(error.message); }
  }

  async function createJourney() {
    const button = $("confirm-create");
    button.disabled = true;
    try {
      const title = $("goal-input").value.trim();
      const situation = $("situation-input").value.trim();
      const description = `Goal: ${title}\nSituation: ${situation || "No additional details provided."}`;
      const goal = situation ? `${title}. ${situation}` : title;
      const body = await api("/journeys/", { method: "POST", body: JSON.stringify({ goal, description }) });
      closeModal("goal-confirm-modal");
      await loadJourneys();
      await selectJourney(body.id, true);
      if (state.authMode === "guest") toast("Sign in with Google from the profile button to save your Journey.");
    } catch (error) { toast(error.message); }
    finally { button.disabled = false; }
  }

  function populateOrganizationSelect() {
    $("detail-org").innerHTML = '<option value="">Not specified</option>' + state.organizations.map((org) => `<option value="${escapeHTML(org.name)}">${escapeHTML(org.short_name || org.name)}</option>`).join("");
  }

  async function showAccount() {
    if (state.authMode === "account") {
      showInfo(
        "Your Journey is saved",
        "Signed in",
        `<p>You are signed in through Auth0. Django continues to control Journey ownership and access.</p>
         <p><button class="button secondary" id="sign-out-button">Sign out</button></p>`
      );
      const signOutButton = $("sign-out-button");
      if (signOutButton) signOutButton.addEventListener("click", signOut);
      return;
    }
    openModal("account-modal");
    $("auth-login").disabled = !state.auth0;
    if (!state.auth0) $("auth-login").textContent = "Configure Auth0 to enable sign-in";
  }

  async function signOut() {
    closeModal("info-modal");
    if (!state.auth0) return;
    await state.auth0.logout({
      logoutParams: { returnTo: window.location.origin + window.location.pathname },
    });
  }

  function bindEvents() {
    $("menu-button").addEventListener("click", openSidebar);
    $("close-sidebar").addEventListener("click", closeSidebar);
    $("sidebar-scrim").addEventListener("click", closeSidebar);
    $("home-button").addEventListener("click", () => state.current ? showScreen("journey") : showLanding());
    $("landing-start").addEventListener("click", startNewGoal);
    $("landing-signin").addEventListener("click", showAccount);
    $("crumb-home").addEventListener("click", openSidebar);
    $("sidebar-new").addEventListener("click", startNewGoal);
    $("completion-new").addEventListener("click", startNewGoal);
    $("review-completed").addEventListener("click", () => showScreen("journey"));
    $("profile-button").addEventListener("click", showAccount);
    $("goal-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const goal = $("goal-input").value.trim();
      if (!goal) return;
      $("confirm-goal-text").textContent = goal;
      $("confirm-situation-text").textContent = $("situation-input").value.trim() || "No additional situation details yet.";
      openModal("goal-confirm-modal");
    });
    $("confirm-create").addEventListener("click", createJourney);
    $("add-event").addEventListener("click", () => openRecordModal());
    $("interpret-event").addEventListener("click", interpretEvent);
    $("save-note").addEventListener("click", savePlainNote);
    $("back-to-event").addEventListener("click", () => { $("record-review-stage").hidden = true; $("record-input-stage").hidden = false; });
    $("confirm-event").addEventListener("click", confirmDraft);
    $("edit-draft").addEventListener("click", () => { fillDetails(state.draft); $("record-review-stage").hidden = true; $("record-edit-stage").hidden = false; });
    $("record-edit-stage").addEventListener("submit", saveDetails);
    $("cancel-details").addEventListener("click", () => closeModal("record-modal"));
    $("delete-event").addEventListener("click", deleteEvent);
    $("stuck-button").addEventListener("click", showHelp);
    $("help-record").addEventListener("click", () => { closeModal("help-modal"); openRecordModal(); });
    $("organization-button").addEventListener("click", showOrganization);
    $("handoff-button").addEventListener("click", showHandoff);
    $("complete-button").addEventListener("click", markComplete);
    $("record-guide-step").addEventListener("click", () => { const step = state.activeGuideStep; closeModal("guide-step-modal"); openRecordModal(step); });
    $("complete-guide-step").addEventListener("click", completeGuideStep);
    $("edit-journey").addEventListener("click", editJourney);
    $("auth-login").addEventListener("click", async () => { if (state.auth0) await state.auth0.loginWithRedirect({ authorizationParams: { screen_hint: "login" } }); });
    $("confirm-modal-confirm").addEventListener("click", () => resolveConfirm(true));
    $("confirm-modal-cancel").addEventListener("click", () => resolveConfirm(false));
    $("confirm-modal-backdrop").addEventListener("click", () => resolveConfirm(false));
    $("confirm-modal-close").addEventListener("click", () => resolveConfirm(false));
    document.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", () => closeModal(el.dataset.close)));
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      const open = document.querySelector(".modal-shell:not([hidden])");
      if (open) closeModal(open.id); else closeSidebar();
    });
  }

  async function start() {
    bindEvents();
    try {
      await setupAuth();
      const orgBody = await api("/organizations/");
      state.organizations = orgBody.results || [];
      populateOrganizationSelect();
      const journeys = await loadJourneys();
      if (journeys.length) await selectJourney(journeys[0].id);
      else showLanding();
    } catch (error) {
      toast(error.message || "The app could not load. Is the server running?");
      showLanding();
    }
  }

  start();
})();
