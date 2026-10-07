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

  // ---------------------------------------------------------------------
  // i18n. window.I18N (demo/static/demo/i18n.js) holds locale-keyed string
  // dictionaries; this is the small runtime that applies them. The active
  // locale is also mirrored to the backend (see syncLocaleWithBackend) so
  // AI-generated content and server-side error messages match it too.
  // ---------------------------------------------------------------------
  const LOCALE_STORAGE_KEY = "brdcrmbs_locale";
  let currentLocale = (function () {
    try {
      const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
      return stored === "fr" ? "fr" : "en";
    } catch (error) {
      return "en";
    }
  })();

  function t(key, vars) {
    const dict = (window.I18N && window.I18N[currentLocale]) || {};
    const fallback = (window.I18N && window.I18N.en) || {};
    let str = Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : fallback[key];
    if (str == null) return key;
    if (vars) {
      Object.keys(vars).forEach((name) => {
        str = str.replaceAll("{" + name + "}", vars[name]);
      });
    }
    return str;
  }

  function plural(count, oneKey, otherKey) {
    // CLDR "one" category: French treats both 0 and 1 as singular; English
    // treats only 1 as singular. Every call site here only ever hits this
    // with n >= 0, so that's the full rule we need.
    const isOne = currentLocale === "fr" ? count === 0 || count === 1 : count === 1;
    return t(isOne ? oneKey : otherKey, { n: count });
  }

  function enumLabel(category, code) {
    if (!code) return code;
    const key = "enum." + category + "." + code;
    const label = t(key);
    return label === key ? code : label;
  }

  function applyI18nToDOM(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.getAttribute("data-i18n")); });
    scope.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.getAttribute("data-i18n-html")); });
    scope.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.getAttribute("data-i18n-placeholder")); });
    scope.querySelectorAll("[data-i18n-aria-label]").forEach((el) => { el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria-label"))); });
    scope.querySelectorAll("[data-i18n-alt]").forEach((el) => { el.alt = t(el.getAttribute("data-i18n-alt")); });
    scope.querySelectorAll("[data-i18n-content]").forEach((el) => { el.setAttribute("content", t(el.getAttribute("data-i18n-content"))); });
  }

  function updateLangToggle() {
    const toggle = $("lang-toggle");
    if (toggle) toggle.textContent = currentLocale === "en" ? "FR" : "EN";
  }

  function optionsHTML(category, codes) {
    return codes.map((code) => `<option value="${code}">${escapeHTML(enumLabel(category, code))}</option>`).join("");
  }

  function populateEnumSelects() {
    const kindSelect = $("detail-kind");
    const kindValue = kindSelect.value;
    kindSelect.innerHTML = optionsHTML("kind", ["INTERACTION", "ACTION", "STATUS_UPDATE", "DOCUMENT", "SOURCE", "NOTE"]);
    if (kindValue) kindSelect.value = kindValue;

    const channelSelect = $("detail-channel");
    const channelValue = channelSelect.value;
    channelSelect.innerHTML = optionsHTML("channel", ["UNKNOWN", "PHONE", "EMAIL", "IN_PERSON", "WEB", "LETTER", "UPLOAD", "OTHER"]);
    if (channelValue) channelSelect.value = channelValue;

    const statusSelect = $("detail-status");
    const statusValue = statusSelect.value;
    statusSelect.innerHTML = optionsHTML("reported_status", [
      "UNKNOWN", "SUBMITTED", "RECEIVED", "PROCESSING", "UNDER_REVIEW",
      "INCOMPLETE", "ADDITIONAL_INFO_REQUIRED", "APPROVED", "REFUSED", "RESOLVED",
    ]);
    if (statusValue) statusSelect.value = statusValue;
  }

  function applyLocaleToUI() {
    document.documentElement.lang = currentLocale;
    applyI18nToDOM();
    updateLangToggle();
    populateEnumSelects();
    populateOrganizationSelect();
    renderSidebar();
    if (state.current) renderJourney();
  }

  async function syncLocaleWithBackend() {
    try {
      await api("/i18n/set-language/", { method: "POST", body: JSON.stringify({ language: currentLocale }) });
    } catch (error) {
      // Non-fatal: the UI is already in the right language locally, and the
      // next successful request will carry the cookie once connectivity or
      // CSRF state recovers.
    }
  }

  async function setLocale(locale) {
    currentLocale = locale === "fr" ? "fr" : "en";
    try { localStorage.setItem(LOCALE_STORAGE_KEY, currentLocale); } catch (error) { /* private browsing, etc. */ }
    applyLocaleToUI();
    await syncLocaleWithBackend();
  }

  function escapeHTML(value) {
    const node = document.createElement("div");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
  }

  function formatDate(value) {
    if (!value) return t("common.date_unspecified");
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString(currentLocale === "fr" ? "fr-CA" : "en-CA", { year: "numeric", month: "short", day: "numeric" });
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
      const failure = new Error(error.message || t("toast.request_failed"));
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
    $("confirm-modal-title").textContent = opts.title || t("modal.confirm.default_title");
    $("confirm-modal-message").textContent = opts.message || "";
    const confirmButton = $("confirm-modal-confirm");
    confirmButton.textContent = opts.confirmLabel || t("common.confirm");
    confirmButton.className = opts.danger ? "button danger" : "button primary";
    $("confirm-modal-cancel").textContent = opts.cancelLabel || t("common.cancel");
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
    const landing = name === "landing";
    $("landing-screen").hidden = !landing;
    $("create-screen").hidden = name !== "create";
    $("journey-screen").hidden = name !== "journey";
    $("completion-screen").hidden = name !== "completion";
    $("landing-nav").hidden = !landing;
    $("landing-nav-start").hidden = !landing;
    $("landing-nav-signin").hidden = !landing || state.authMode !== "guest";
    $("menu-button").hidden = landing;
    $("profile-button").hidden = landing;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function showLanding() {
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
        toast(params.get("error_description") || t("toast.signin_failed"));
        history.replaceState({}, document.title, location.pathname);
      } else if (location.search.includes("code=") && location.search.includes("state=")) {
        await state.auth0.handleRedirectCallback();
        history.replaceState({}, document.title, location.pathname);
      }
      if (await state.auth0.isAuthenticated()) {
        state.accessToken = await state.auth0.getTokenSilently();
        try {
          const migrated = await api("/auth/migrate-guest/", { method: "POST", body: "{}" });
          if (migrated.status === "migrated" && migrated.migrated_count) toast(t("toast.guest_migrated"));
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
    if (diffDays <= 0) return t("date.updated_today");
    if (diffDays === 1) return t("date.updated_yesterday");
    if (diffDays < 7) return t("date.updated_days_ago", { n: diffDays });
    return t("date.updated_on", { date: formatDate(value) });
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
        <small><span class="status-pill ${escapeHTML(journey.status)}">${escapeHTML(enumLabel("status", journey.status))}</span> ${escapeHTML(relativeDay(journey.updated_at))}</small>`;
      button.addEventListener("click", async () => { closeSidebar(); await selectJourney(journey.id); });
      li.appendChild(button);
      list.appendChild(li);
    });

    const quota = $("sidebar-quota");
    if (quota) {
      const activeCount = state.journeys.filter((journey) => ACTIVE_STATUSES.includes(journey.status)).length;
      const limit = state.journeyLimit;
      quota.textContent = limit ? t("sidebar.quota", { count: activeCount, limit }) : "";
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
    // Switch screens before the detail rendering below, and unconditionally --
    // otherwise an exception thrown while rendering one journey's details
    // (e.g. an unexpected data shape) leaves whatever screen was visible
    // before this call (such as the new-goal form) stuck on screen with no
    // indication anything went wrong, until a manual refresh.
    if (!forceJourneyScreen && state.current.state.status === "COMPLETED") renderCompletion();
    else showScreen("journey");
    try {
      renderJourney();
      renderSidebar();
    } catch (error) {
      console.error(error);
    }
  }

  function renderJourney() {
    const journey = state.current;
    if (!journey) return;
    $("journey-title").textContent = journey.title;
    $("journey-goal").textContent = journey.goal;
    $("current-state").textContent = journey.state.current_state;
    $("next-action").textContent = journey.state.next_action || t("journey.no_next_action");
    const status = $("status-pill");
    status.className = "status-pill " + journey.state.status;
    status.textContent = enumLabel("status", journey.state.status);
    const count = (journey.timeline || []).length;
    $("record-count").textContent = plural(count, "journey.recorded_events_one", "journey.recorded_events_other");
    const source = journey.state.source || {};
    $("state-source").textContent = source.type
      ? t("journey.state_source_known", { source: enumLabel("source", source.type) })
      : t("journey.state_source_unknown");
    $("record-context").textContent = t("journey.record_context", { title: journey.title, status: enumLabel("status", journey.state.status) });
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
        <span class="event-status">${escapeHTML(enumLabel("kind", row.kind))}</span><span class="chevron">›</span>`;
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
      $("guide-summary").textContent = t("journey.no_guide");
      $("guide-progress-label").textContent = t("journey.steps_complete", { completed: 0, total: 0 });
      $("guide-progress-bar").style.width = "0%";
      $("guide-clarification").hidden = true;
      $("guide-engine").textContent = t("journey.no_generator");
      return;
    }
    const steps = guide.steps || [];
    const completed = steps.filter((step) => step.status === "COMPLETED").length;
    $("guide-summary").textContent = guide.summary;
    const usedGemini = guide.generated_by === "gemini";
    $("guide-engine").textContent = usedGemini
      ? t("journey.engine_gemini")
      : t("journey.engine_fallback");
    $("guide-engine").title = usedGemini
      ? t("journey.engine_gemini_title")
      : t("journey.engine_fallback_title");
    $("guide-progress-label").textContent = t("journey.steps_complete", { completed, total: steps.length });
    $("guide-progress-bar").style.width = steps.length ? `${Math.round((completed / steps.length) * 100)}%` : "0%";
    const clarification = $("guide-clarification");
    clarification.hidden = !guide.needs_clarification;
    clarification.textContent = guide.needs_clarification ? t("journey.clarification_prefix", { question: guide.clarification_question }) : "";
    steps.forEach((step) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "guide-step" + (step.status === "IN_PROGRESS" ? " current" : "");
      button.innerHTML = `
        <span class="step-orb ${step.status === "COMPLETED" ? "complete" : ""}">${step.position}</span>
        <span class="guide-step-copy"><strong>${escapeHTML(step.title)}</strong><p>${escapeHTML(step.description)}</p></span>
        <span class="guide-step-status ${escapeHTML(step.status)}">${escapeHTML(enumLabel("guide_status", step.status))}</span>
        <span class="chevron">›</span>`;
      button.addEventListener("click", () => openGuideStep(step));
      li.appendChild(button);
      list.appendChild(li);
    });
  }

  /*
   * A section-level preview: agency, precise heading, supporting excerpt, and
   * a deep link. The server snapshots these values with the guide step so a
   * later page refresh cannot rewrite what the citizen originally saw.
   * The bare URL remains its own visible line -- the same shape
   * as a normal chat-app link preview, so a citizen recognizes it as a real,
   * verifiable government page rather than inline blue text. Built entirely
   * from server-validated fields; the browser never fetches or searches for
   * source metadata itself.
   */
  function siteNameFor(url) {
    try {
      const host = new URL(url).hostname.replace(/^www\./, "");
      return host.endsWith("canada.ca") ? "Canada.ca" : host.endsWith("ontario.ca") ? "Ontario.ca" : host;
    } catch (error) {
      return t("source.default_name");
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
    const verified = source.verified_at ? t("date.link_checked", { date: formatDate(source.verified_at) }) : t("date.curated_source");
    const freshnessWarning = source.current_status && source.current_status !== "VERIFIED"
      ? `<p class="source-warning">${escapeHTML(t("source.changed_warning"))}</p>`
      : "";
    container.innerHTML = `
      <div class="source-preview">
        <p class="source-eyebrow">${escapeHTML(siteName)} • ${escapeHTML(source.title)}</p>
        <strong>${escapeHTML(source.section_heading || source.title)}</strong>
        ${freshnessWarning}
        <p>${escapeHTML(source.description || t("source.check_current"))}</p>
        <a href="${escapeHTML(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(source.url)}</a>
        <span class="source-verified">${escapeHTML(verified)}</span>
      </div>`;
  }

  function openGuideStep(step) {
    state.activeGuideStep = step;
    $("guide-step-position").textContent = t("journey.step_position", {
      position: step.position,
      total: (state.current.guide.steps || []).length,
      status: enumLabel("guide_status", step.status),
    });
    $("guide-step-title").textContent = step.title;
    $("guide-step-description").textContent = step.description;
    renderSourceCard($("guide-step-source"), step.official_source, step.organization);
    $("complete-guide-step").disabled = step.status === "COMPLETED";
    $("complete-guide-step").textContent = step.status === "COMPLETED" ? t("journey.step_complete_label") : t("journey.mark_step_complete");
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
      div.innerHTML = `<span aria-hidden="true">✓</span><strong>${escapeHTML(step.title)}</strong>`;
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
    $("details-heading").textContent = t("modal.record.edit_title");
  }

  function openRecordModal(guideStep) {
    resetRecordModal();
    state.activeGuideStep = guideStep || null;
    if (guideStep) {
      $("record-context").textContent = t("journey.record_context_step", {
        title: state.current.title, position: guideStep.position, step: guideStep.title,
      });
    } else {
      $("record-context").textContent = t("journey.record_context", {
        title: state.current.title, status: enumLabel("status", state.current.state.status),
      });
    }
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
    $("draft-paraphrase").textContent = draft.paraphrase || draft.title || t("modal.record.review_placeholder");
    $("draft-original").textContent = t("modal.record.you_said", { text: rawText });
    const tags = [enumLabel("kind", draft.kind), draft.channel && draft.channel !== "UNKNOWN" ? enumLabel("channel", draft.channel) : "", draft.organization || ""].filter(Boolean);
    $("draft-tags").innerHTML = tags.map((tag) => `<span>${escapeHTML(tag)}</span>`).join("");
    const usedGemini = meta && meta.extractor === "gemini";
    $("draft-engine").textContent = usedGemini
      ? "Interpretation source: Gemini AI"
      : "Interpretation source: rules-based fallback (no Gemini output used)";
    const notice = $("draft-notice");
    notice.hidden = !(draft.needs_clarification || (meta && meta.degraded));
    notice.textContent = draft.needs_clarification ? (draft.clarification_question || t("modal.record.review_carefully")) : t("modal.record.degraded_notice");
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
      title: draft.title || t("journey.default_event_title"),
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
      await refreshCurrent(result.change ? result.change.message : t("toast.added_to_journey"));
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
      await refreshCurrent(result.change ? result.change.message : t("toast.note_saved"));
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
    $("details-heading").textContent = t("modal.record.review_recorded_title");
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
        await refreshCurrent(result.change ? result.change.message : t("toast.event_updated"));
      } else {
        const full = Object.assign(draftPayload(), payload);
        const result = await api(`/journeys/${state.current.id}/breadcrumbs/`, { method: "POST", body: JSON.stringify(full) });
        closeModal("record-modal");
        await refreshCurrent(result.change ? result.change.message : t("toast.event_saved"));
      }
    } catch (error) { toast(error.message); }
  }

  async function deleteEvent() {
    if (!state.editing) return;
    const confirmed = await confirmModal({
      title: t("confirm.remove_event_title"),
      message: t("confirm.remove_event_message"),
      confirmLabel: t("confirm.remove_event_cta"),
      danger: true,
    });
    if (!confirmed) return;
    try {
      const result = await api(`/breadcrumbs/${state.editing.id}/`, { method: "DELETE" });
      closeModal("record-modal");
      await refreshCurrent(result.change ? result.change.message : t("toast.event_removed"));
    } catch (error) { toast(error.message); }
  }

  async function showHelp() {
    openModal("help-modal");
    $("help-context").textContent = t("modal.help.context", { title: state.current.title });
    $("help-summary").innerHTML = `<div class="help-block"><p>${escapeHTML(t("modal.help.loading"))}</p></div>`;
    try {
      const body = await api(`/journeys/${state.current.id}/stuck/?polish=false`);
      const org = body.responsible_organization;
      $("help-summary").innerHTML = `
        <div class="help-block"><span>${escapeHTML(t("modal.help.section_left_off"))}</span><p>${escapeHTML(body.summary || state.current.state.current_state)}</p></div>
        <div class="help-block"><span>${escapeHTML(t("modal.help.section_unresolved"))}</span><p>${escapeHTML(body.unresolved_issue || t("modal.help.no_unresolved"))}</p></div>
        <div class="help-block"><span>${escapeHTML(t("modal.help.section_instruction"))}</span><p>${escapeHTML(body.latest_instruction || t("modal.help.no_instruction"))}</p></div>
        <div class="help-block"><span>${escapeHTML(t("modal.help.section_org"))}</span><p>${escapeHTML(org ? (org.short_name || org.name) : t("modal.help.org_unknown"))}</p></div>`;
    } catch (error) { $("help-summary").innerHTML = `<div class="notice">${escapeHTML(error.message)}</div>`; }
  }

  function showInfo(title, eyebrow, html) {
    $("info-title").textContent = title;
    $("info-eyebrow").textContent = eyebrow;
    $("info-content").innerHTML = html;
    openModal("info-modal");
  }

  async function showOrganization() {
    showInfo(t("modal.org.loading_title"), t("modal.org.loading_eyebrow"), `<p>${escapeHTML(t("common.loading"))}</p>`);
    try {
      const body = await api(`/journeys/${state.current.id}/responsible-organization/`);
      if (!body.responsible_organization) { showInfo(t("modal.org.unknown_title"), t("journey.org_button"), `<p>${escapeHTML(body.message)}</p>`); return; }
      const org = body.responsible_organization;
      const sources = (body.official_sources || []).map((source) => `<li><a href="${escapeHTML(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(source.title)}</a></li>`).join("");
      showInfo(
        org.short_name || org.name,
        t("modal.help.section_org"),
        `<p>${escapeHTML(body.message || body.basis || t("modal.org.matched_basis"))}</p><p><a href="${escapeHTML(org.official_url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(t("modal.org.open_site"))}</a></p>${sources ? `<h3>${escapeHTML(t("modal.org.sources_heading"))}</h3><ul class="source-list">${sources}</ul>` : ""}`
      );
    } catch (error) { showInfo(t("modal.org.error_title"), t("journey.org_button"), `<p>${escapeHTML(error.message)}</p>`); }
  }

  async function showHandoff() {
    showInfo(t("modal.handoff.loading_title"), t("modal.handoff.eyebrow"), `<p>${escapeHTML(t("modal.handoff.loading_body"))}</p>`);
    try {
      const body = await api(`/journeys/${state.current.id}/handoff/`, { method: "POST", body: JSON.stringify({ polish: false }) });
      showInfo(
        t("modal.handoff.result_title"),
        t("modal.handoff.eyebrow"),
        `<pre class="summary-text" id="handoff-summary">${escapeHTML(body.summary)}</pre><p><button class="button primary" id="copy-handoff">${escapeHTML(t("modal.handoff.copy_button"))}</button></p>`
      );
      $("copy-handoff").addEventListener("click", async () => { await navigator.clipboard.writeText(body.summary); toast(t("toast.handoff_copied")); });
    } catch (error) { showInfo(t("modal.handoff.error_title"), t("modal.handoff.eyebrow"), `<p>${escapeHTML(error.message)}</p>`); }
  }

  async function markComplete() {
    const confirmed = await confirmModal({
      title: t("confirm.complete_title"),
      message: t("confirm.complete_message"),
      confirmLabel: t("confirm.complete_cta"),
    });
    if (!confirmed) return;
    try {
      const payload = {
        kind: "STATUS_UPDATE", channel: "OTHER", title: t("journey.marked_complete_title"),
        raw_text: t("journey.marked_complete_raw"), reported_status: "RESOLVED",
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
      await refreshCurrent(t("toast.step_completed", { n: step.position }));
    } catch (error) { toast(error.message); }
    finally { button.disabled = false; }
  }

  function editJourney() {
    if (!state.current) return;
    $("edit-goal-name").value = state.current.title || "";
    $("edit-goal-description").value = state.current.goal || "";
    openModal("edit-goal-modal");
    setTimeout(() => $("edit-goal-name").focus(), 0);
  }

  async function saveJourneyEdits(event) {
    event.preventDefault();
    if (!state.current) return;
    const title = $("edit-goal-name").value.trim();
    const goal = $("edit-goal-description").value.trim();
    if (!title || !goal) return;
    const button = $("save-goal");
    button.disabled = true;
    try {
      await api(`/journeys/${state.current.id}/`, { method: "PATCH", body: JSON.stringify({ title, goal }) });
      closeModal("edit-goal-modal");
      await refreshCurrent(t("toast.goal_updated"));
    } catch (error) { toast(error.message); }
    finally { button.disabled = false; }
  }

  async function createJourney() {
    const button = $("confirm-create");
    button.disabled = true;
    try {
      const title = $("goal-input").value.trim();
      const situation = $("situation-input").value.trim();
      const description = t("create.ai_context", { title, situation: situation || t("create.no_situation_details") });
      const goal = situation ? `${title}. ${situation}` : title;
      const body = await api("/journeys/", { method: "POST", body: JSON.stringify({ goal, description }) });
      if (body.type === "OUT_OF_SCOPE") {
        closeModal("goal-confirm-modal");
        toast(body.message || "That goal is outside this public-service Journey tool.");
        $("goal-input").focus();
        return;
      }
      closeModal("goal-confirm-modal");
      await loadJourneys();
      await selectJourney(body.id, true);
      if (state.authMode === "guest") toast(t("toast.guest_reminder"));
    } catch (error) { toast(error.message); }
    finally { button.disabled = false; }
  }

  function populateOrganizationSelect() {
    $("detail-org").innerHTML = `<option value="">${escapeHTML(t("modal.record.field_org_unspecified"))}</option>` + state.organizations.map((org) => `<option value="${escapeHTML(org.name)}">${escapeHTML(org.short_name || org.name)}</option>`).join("");
  }

  async function showAccount() {
    if (state.authMode === "account") {
      showInfo(
        t("modal.account.signed_in_title"),
        t("modal.account.signed_in_eyebrow"),
        `<p>${escapeHTML(t("modal.account.signed_in_body"))}</p>
         <p><button class="button secondary" id="sign-out-button">${escapeHTML(t("modal.account.sign_out"))}</button></p>`
      );
      const signOutButton = $("sign-out-button");
      if (signOutButton) signOutButton.addEventListener("click", signOut);
      return;
    }
    openModal("account-modal");
    $("auth-login").disabled = !state.auth0;
    if (!state.auth0) $("auth-login").textContent = t("modal.account.disabled_cta");
  }

  async function signOut() {
    closeModal("info-modal");
    if (!state.auth0) return;
    state.accessToken = null;
    state.current = null;
    showLanding();
    await state.auth0.logout({
      logoutParams: { returnTo: window.location.origin + window.location.pathname },
    });
  }

  window.addEventListener("pageshow", (event) => {
    if (event.persisted) window.location.reload();
  });

  function bindEvents() {
    $("menu-button").addEventListener("click", openSidebar);
    $("close-sidebar").addEventListener("click", closeSidebar);
    $("sidebar-scrim").addEventListener("click", closeSidebar);
    $("home-button").addEventListener("click", () => state.current ? showScreen("journey") : showLanding());
    $("landing-start").addEventListener("click", startNewGoal);
    $("landing-nav-start").addEventListener("click", startNewGoal);
    $("landing-nav-signin").addEventListener("click", showAccount);
    $("landing-closing-cta").addEventListener("click", startNewGoal);
    $("lang-toggle").addEventListener("click", () => setLocale(currentLocale === "en" ? "fr" : "en"));
    $("crumb-home").addEventListener("click", openSidebar);
    $("sidebar-new").addEventListener("click", startNewGoal);
    $("completion-new").addEventListener("click", startNewGoal);
    $("review-completed").addEventListener("click", () => showScreen("journey"));
    $("profile-button").addEventListener("click", showAccount);
    $("goal-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const goal = $("goal-input").value.trim();
      if (!goal) return;
      const situation = $("situation-input").value.trim();
      const button = $("goal-review");
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      try {
        const body = await api("/journeys/preview/", {
          method: "POST",
          body: JSON.stringify({ goal, description: situation }),
        });
        if (body.type === "OUT_OF_SCOPE") {
          toast(body.message || t("toast.request_failed"));
          return;
        }
        $("confirm-goal-text").textContent = body.summary || goal;
        $("confirm-situation-text").textContent = body.ai && body.ai.extractor === "gemini"
          ? t("modal.confirm_goal.gemini_summary")
          : t("modal.confirm_goal.fallback_summary");
        openModal("goal-confirm-modal");
      } catch (error) {
        toast(error.message);
      } finally {
        button.disabled = false;
        button.removeAttribute("aria-busy");
      }
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
    $("edit-goal-form").addEventListener("submit", saveJourneyEdits);
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
    document.documentElement.lang = currentLocale;
    applyI18nToDOM();
    updateLangToggle();
    bindEvents();
    try {
      const csrfResponse = await fetch(API + "/auth/csrf/", { credentials: "include" });
      state.csrfToken = (await csrfResponse.json()).csrf_token || "";
      await syncLocaleWithBackend();
      await setupAuth();
      const orgBody = await api("/organizations/");
      state.organizations = orgBody.results || [];
      populateEnumSelects();
      populateOrganizationSelect();
      const journeys = await loadJourneys();
      if (journeys.length) await selectJourney(journeys[0].id);
      else showLanding();
    } catch (error) {
      toast(error.message || t("error.app_load_failed"));
      showLanding();
    }
  }

  start();
})();
