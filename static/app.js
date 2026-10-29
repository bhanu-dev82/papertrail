"use strict";

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 8 * 1024 * 1024;
const STAGES = ["read", "triage", "verify", "plan"];
const STAGE_LABELS = { read: "Read", triage: "Triage", verify: "Verify", plan: "Plan" };

const state = {
  file: null,
  result: null,
  timer: null,
  toastTimer: null,
  busy: false,
  previewUrl: null,
  mode: null,
};

const $ = (selector) => document.querySelector(selector);

document.addEventListener("DOMContentLoaded", init);

function init() {
  loadHealth();
  syncLabels();
  setView("empty");

  const dropzone = $("#dropzone");
  const input = $("#file-input");

  dropzone.addEventListener("click", () => {
    if (state.busy) {
      setLive("Already reading a document. Wait for it to finish.");
      return;
    }
    input.click();
  });
  dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      if (state.busy) {
        event.preventDefault();
        setLive("Already reading a document. Wait for it to finish.");
        return;
      }
      event.preventDefault();
      input.click();
    }
  });

  input.addEventListener("change", () => {
    if (input.files && input.files[0]) {
      handleFile(input.files[0]);
      input.value = "";
    }
  });

  ["dragenter", "dragover"].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragging");
    });
  });

  ["dragleave", "dragend"].forEach((name) => {
    dropzone.addEventListener(name, () => dropzone.classList.remove("is-dragging"));
  });

  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragging");
    const file = event.dataTransfer && event.dataTransfer.files
      ? event.dataTransfer.files[0]
      : null;
    if (file) handleFile(file);
  });

  $("#analyze-btn").addEventListener("click", () => {
    if (state.busy || !state.file) return;
    analyze(fileFormData());
  });

  $("#sample-btn").addEventListener("click", () => {
    if (state.busy) return;
    analyze(null);
  });

  $("#empty-sample-btn").addEventListener("click", () => {
    if (state.busy) return;
    analyze(null);
  });

  $("#error-sample-btn").addEventListener("click", () => {
    if (state.busy) return;
    analyze(null);
  });

  $("#retry-btn").addEventListener("click", () => {
    if (state.busy) return;
    if (state.mode === "sample" || !state.file) {
      analyze(null);
      return;
    }
    analyze(fileFormData());
  });

  $("#copy-btn").addEventListener("click", copyDraft);

  $("#new-doc-btn").addEventListener("click", () => {
    if (state.busy) return;
    resetApp();
  });

  $("#replace-btn").addEventListener("click", () => {
    if (state.busy) return;
    resetApp();
  });

  window.addEventListener("resize", syncLabels);
}

function syncLabels() {
  const button = $("#new-doc-btn");
  if (!button) return;
  button.textContent = window.matchMedia("(max-width: 480px)").matches
    ? "New"
    : "New document";
}

/* ---------------------------------------------------------------------- */
/* Health                                                                  */
/* ---------------------------------------------------------------------- */
async function loadHealth() {
  const pill = $("#mode-pill");
  try {
    const response = await fetch("/api/health", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("health");
    const health = await response.json();
    if (health.mock) {
      pill.textContent = "Demo data";
      pill.className = "pill pill--mock";
      pill.title = "No API keys configured. Results use canned demo data.";
    } else {
      pill.textContent = window.matchMedia("(max-width: 600px)").matches
        ? "Live"
        : "Live · Nebius Token Factory";
      pill.className = "pill pill--live";
      pill.title = `Vision ${health.models.vision} · Fast ${health.models.fast} · Reason ${health.models.reason}`;
    }
  } catch (error) {
    pill.textContent = "Offline";
    pill.className = "pill pill--error";
    pill.title = "Could not reach the backend.";
  }
}

/* ---------------------------------------------------------------------- */
/* File selection                                                          */
/* ---------------------------------------------------------------------- */
function fileFormData() {
  const formData = new FormData();
  formData.append("file", state.file);
  return formData;
}

function handleFile(file) {
  if (state.busy) return;

  const name = String(file.name || "").toLowerCase();
  if (file.type === "application/pdf" || name.endsWith(".pdf")) {
    rejectFile("That file is a PDF. Take a photo of the page or export it as a JPG, PNG or WEBP.");
    return;
  }
  if (file.type === "image/heic" || file.type === "image/heif" || name.endsWith(".heic") || name.endsWith(".heif")) {
    rejectFile("That is a HEIC photo. Export it as a JPG or PNG, then try again.");
    return;
  }
  if (!ALLOWED_TYPES.includes(file.type)) {
    rejectFile("Use a JPG, PNG or WEBP image.");
    return;
  }
  if (file.size > MAX_BYTES) {
    const mb = (file.size / 1024 / 1024).toFixed(1);
    rejectFile(`That photo is ${mb} MB. The limit is 8 MB. Try a smaller photo.`);
    return;
  }

  clearUploadError();
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);

  state.file = file;
  state.previewUrl = URL.createObjectURL(file);

  const preview = $("#preview");
  preview.src = state.previewUrl;
  preview.alt = `Preview of ${file.name}`;
  preview.hidden = false;
  $("#dropzone-prompt").hidden = true;

  const kb = Math.max(1, Math.round(file.size / 1024));
  $("#file-name").textContent = `${file.name} · ${kb} KB`;
  $("#analyze-btn").hidden = false;
  $("#analyze-btn").disabled = false;
  $("#new-doc-btn").hidden = false;
  setLive(`${file.name} is ready. Choose Analyze document.`);
}

function rejectFile(message) {
  clearFileState();
  showUploadError(message);
  setLive(message);
}

function clearFileState() {
  if (state.previewUrl) {
    URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = null;
  }
  state.file = null;

  const preview = $("#preview");
  preview.hidden = true;
  preview.removeAttribute("src");
  preview.alt = "";
  $("#dropzone-prompt").hidden = false;
  $("#file-name").textContent = "";
  $("#analyze-btn").hidden = true;
  $("#analyze-btn").disabled = true;
  $("#new-doc-btn").hidden = true;
}

function clearUploadError() {
  const error = $("#upload-error");
  error.hidden = true;
  error.textContent = "";
  const dropzone = $("#dropzone");
  dropzone.setAttribute("aria-describedby", "upload-help");
}

function showUploadError(message) {
  const error = $("#upload-error");
  error.textContent = message;
  error.hidden = false;
  const dropzone = $("#dropzone");
  dropzone.setAttribute("aria-describedby", "upload-help upload-error");
}

/* ---------------------------------------------------------------------- */
/* Analyze                                                                 */
/* ---------------------------------------------------------------------- */
async function analyze(formData) {
  if (state.busy) return;

  const isSample = !formData;
  state.mode = isSample ? "sample" : "file";
  clearUploadError();
  setBusy(true);
  setView("loading");
  resetPipeline();
  animatePipeline();
  $("#loading-title").focus({ preventScroll: true });
  setLive(
    isSample
      ? "Reading the sample bill. This usually takes 10 to 15 seconds."
      : "Reading your document. This usually takes 10 to 15 seconds."
  );

  try {
    const response = await fetch(isSample ? "/api/analyze-sample" : "/api/analyze", {
      method: "POST",
      body: formData || undefined,
      headers: formData ? undefined : { Accept: "application/json" },
    });

    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = {};
    }

    if (!response.ok) {
      const detail = typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status}).`;
      throw new Error(detail);
    }

    state.result = data;
    stopAnimation();
    paintTrace(data.trace || []);
    renderTraceDetails(data.trace || []);
    renderResult(data);
  } catch (error) {
    stopAnimation(true);
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

function setBusy(isBusy) {
  state.busy = isBusy;
  const analyzeButton = $("#analyze-btn");
  const sampleButton = $("#sample-btn");
  const newButton = $("#new-doc-btn");
  const dropzone = $("#dropzone");

  if (isBusy) {
    analyzeButton.setAttribute("aria-disabled", "true");
    sampleButton.setAttribute("aria-disabled", "true");
    dropzone.setAttribute("aria-disabled", "true");
    newButton.disabled = true;
    analyzeButton.disabled = !state.file;
    if (state.mode === "sample") {
      sampleButton.textContent = "Reading sample…";
    } else {
      analyzeButton.textContent = "Analyzing…";
    }
  } else {
    analyzeButton.removeAttribute("aria-disabled");
    sampleButton.removeAttribute("aria-disabled");
    dropzone.removeAttribute("aria-disabled");
    newButton.disabled = false;
    analyzeButton.disabled = !state.file;
    analyzeButton.textContent = "Analyze document";
    sampleButton.textContent = "Try sample bill";
  }
}

function showError(message) {
  const copy = friendlyError(message);
  $("#error-copy").textContent = copy;
  setView("error");
  setLive(`Could not read the document. ${copy}`);
  window.requestAnimationFrame(() => $("#error-title").focus({ preventScroll: true }));
}

function friendlyError(message) {
  const text = String(message || "");
  const lower = text.toLowerCase();
  if (lower.includes("demo limit")) {
    return "This demo has reached its analysis limit for now. Try again later, or open the sample case.";
  }
  if (lower.includes("could not read the document")) {
    return "We could not read this photo. Try again with the whole page in frame, good light and no glare.";
  }
  if (lower.includes("failed to fetch") || lower.includes("networkerror")) {
    return "The request did not finish. Check your connection and try again.";
  }
  if (lower.includes("json")) {
    return "The plan did not finish. Your photo was not stored. Try again.";
  }
  return text || "The plan did not finish. Your photo was not stored. Try again.";
}

/* ---------------------------------------------------------------------- */
/* Views                                                                   */
/* ---------------------------------------------------------------------- */
function setView(view) {
  const views = {
    empty: "#case-empty",
    loading: "#case-loading",
    error: "#case-error",
    result: "#results",
  };

  Object.entries(views).forEach(([name, selector]) => {
    const element = $(selector);
    if (element) element.hidden = name !== view;
  });

  $("#rail-intake").hidden = view === "result";
  $("#rail-doc").hidden = view !== "result";
  $("#new-doc-btn").hidden = view === "empty";
  document.body.classList.toggle("has-result", view === "result");
}

function resetApp() {
  if (state.busy) return;

  clearFileState();
  clearUploadError();
  state.result = null;
  state.mode = null;

  $("#facts-body").textContent = "";
  $("#trace-list").textContent = "";
  $("#plan-steps").textContent = "";
  $("#sources").textContent = "";
  $("#draft-text").textContent = "";
  $("#draft-box").hidden = true;
  $("#plan-warning").hidden = true;
  $("#doc-thumb").removeAttribute("src");
  $("#doc-thumb").alt = "";

  setView("empty");
  document.title = "PaperTrail — What does this document want?";
  setLive("New document. Choose a photo or open the sample.");

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.scrollTo({ top: 0, behavior: reduced ? "auto" : "smooth" });
  window.requestAnimationFrame(() => $("#dropzone").focus({ preventScroll: true }));
}

/* ---------------------------------------------------------------------- */
/* Pipeline animation                                                      */
/* ---------------------------------------------------------------------- */
function rowFor(stage) {
  return document.querySelector(`.pipeline__row[data-stage="${stage}"]`);
}

function resetPipeline() {
  STAGES.forEach((stage) => {
    const row = rowFor(stage);
    if (!row) return;
    row.classList.remove("is-running", "is-done", "is-error", "is-degraded");
    row.querySelector('[data-role="status"]').textContent = "waiting";
    row.querySelector('[data-role="status"]').removeAttribute("title");
    row.querySelector('[data-role="dot"]').textContent = "";
  });
}

function animatePipeline() {
  stopAnimation();
  let index = 0;
  const tick = () => {
    if (index >= STAGES.length) return;
    const row = rowFor(STAGES[index]);
    if (row) {
      row.classList.add("is-running");
      row.querySelector('[data-role="status"]').textContent = "running";
      row.querySelector('[data-role="dot"]').textContent = "";
      setLive(`Step ${index + 1} of ${STAGES.length}: ${STAGE_LABELS[STAGES[index]]} running.`);
    }
    index += 1;
  };
  tick();
  state.timer = window.setInterval(tick, 1500);
}

function stopAnimation(failed) {
  if (state.timer) {
    window.clearInterval(state.timer);
    state.timer = null;
  }
  if (!failed) return;
  STAGES.forEach((stage) => {
    const row = rowFor(stage);
    if (!row || !row.classList.contains("is-running")) return;
    row.classList.remove("is-running");
    row.classList.add("is-error");
    row.querySelector('[data-role="dot"]').textContent = "";
    row.querySelector('[data-role="status"]').textContent = "failed";
  });
}

function paintTrace(trace) {
  const byStage = {};
  trace.forEach((entry) => {
    if (entry && entry.stage) byStage[entry.stage] = entry;
  });

  STAGES.forEach((stage) => {
    const entry = byStage[stage];
    if (!entry) return;
    const row = rowFor(stage);
    if (!row) return;

    row.classList.remove("is-running", "is-error");
    row.classList.add("is-done");
    if (entry.degraded) row.classList.add("is-degraded");

    const status = row.querySelector('[data-role="status"]');
    let statusText = "";
    if (entry.provider === "mock") {
      statusText = "Demo data";
    } else {
      statusText = `${(Number(entry.latency_ms || 0) / 1000).toFixed(1)} s`;
    }
    if (entry.degraded) statusText += " · degraded";
    status.textContent = statusText;
    status.title = [
      entry.model,
      `${entry.prompt_tokens || 0} to ${entry.completion_tokens || 0} tokens`,
      entry.note,
    ].filter(Boolean).join(" · ");
    row.querySelector('[data-role="dot"]').textContent = "";
  });
}

function renderTraceDetails(trace) {
  const list = $("#trace-list");
  list.textContent = "";

  trace.forEach((entry) => {
    const item = document.createElement("li");
    const stage = document.createElement("span");
    stage.className = "trace__stage";
    stage.textContent = STAGE_LABELS[entry.stage] || entry.stage;

    const meta = document.createElement("span");
    meta.className = "trace__meta";
    const parts = [entry.model];
    if (entry.provider === "mock") {
      parts.push("demo data");
    } else {
      parts.push(`${entry.latency_ms} ms`);
      parts.push(`${entry.prompt_tokens} to ${entry.completion_tokens} tokens`);
    }
    if (entry.degraded) parts.push("degraded");
    if (entry.note) parts.push(entry.note);
    meta.textContent = parts.filter(Boolean).join(" · ");

    item.append(stage, meta);
    list.appendChild(item);
  });
}

/* ---------------------------------------------------------------------- */
/* Result rendering                                                        */
/* ---------------------------------------------------------------------- */
function renderResult(data) {
  const extraction = data.extraction || {};
  const triage = data.triage || {};
  const plan = data.plan || {};
  const sources = Array.isArray(data.sources) ? data.sources : [];
  const due = findDue(extraction, plan);

  const urgency = String(triage.urgency || "medium").toLowerCase();
  const badge = $("#urgency-badge");
  badge.className = `badge badge--${urgency}`;
  badge.textContent = urgency.charAt(0).toUpperCase() + urgency.slice(1);

  const category = String(triage.category || "other");
  $("#category-chip").textContent = category.charAt(0).toUpperCase() + category.slice(1);
  $("#headline").textContent = plan.headline || "Your plan";
  $("#summary").textContent = triage.summary || "No summary was produced.";
  $("#result-meta").textContent = [
    extraction.issuer,
    extraction.document_type,
    extraction.recipient_name,
  ].filter(Boolean).join(" · ");
  $("#risk").textContent = plan.risk_if_ignored || "No consequence was read from this page.";
  $("#disclaimer").textContent = plan.disclaimer
    || "This is not legal or financial advice. Verify the details with the issuer.";

  $("#due-date").textContent = due ? formatDate(due) : "No date found";
  $("#due-relative").textContent = due ? relativeDue(due) : "Check the whole page.";
  $("#ics-link").hidden = !due;
  $("#amount").textContent = (extraction.amounts && extraction.amounts[0]) || "Not found";
  $("#issuer").textContent = shortIssuer(extraction.issuer) || "Not found";
  $("#doc-type").textContent = extraction.document_type || "";

  renderFacts(extraction);
  renderSteps(plan, data.id, sources);
  renderDraft(plan.draft_message || "", extraction.issuer || "");
  renderSources(sources);
  renderPlanWarning(sources);
  renderDocRail(extraction, due);
  renderTraceDetails(data.trace || []);

  $("#ics-link").href = `/api/results/${encodeURIComponent(data.id)}/calendar.ics`;
  $("#md-link").href = `/api/results/${encodeURIComponent(data.id)}/plan.md`;

  setView("result");
  document.title = `${plan.headline || "Your plan"} · PaperTrail`;

  const steps = Array.isArray(plan.steps) ? plan.steps : [];
  setLive(
    `Your plan is ready. ${plan.headline || ""} ${steps.length} steps and ${sources.length} sources.`
  );

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const mobile = window.matchMedia("(max-width: 900px)").matches;

  window.requestAnimationFrame(() => {
    const results = $("#results");
    const rect = results.getBoundingClientRect();
    if (mobile || rect.top < 0 || rect.top > window.innerHeight * 0.7) {
      results.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    }
    $("#headline").focus({ preventScroll: true });
  });
}

function renderFacts(extraction) {
  const body = $("#facts-body");
  body.textContent = "";

  const rows = [
    ["Type", extraction.document_type],
    ["Issuer", extraction.issuer],
    ["Recipient", extraction.recipient_name],
    ["References", (extraction.reference_numbers || []).join(", ")],
    ["Amounts", (extraction.amounts || []).join(", ")],
  ];

  rows.forEach(([label, value]) => {
    body.appendChild(factRow(label, value || "Not found"));
  });

  const dates = Array.isArray(extraction.key_dates) ? extraction.key_dates : [];
  const datesCell = document.createElement("div");
  if (!dates.length) {
    datesCell.textContent = "Not found";
  } else {
    dates.forEach((item) => {
      const line = document.createElement("div");
      line.className = item.is_deadline ? "fact-date fact-date--deadline" : "fact-date";
      const dateText = `${item.label || "Date"}: ${item.date ? formatDate(item.date) : "Year missing"}`;
      line.textContent = item.is_deadline ? `${dateText} — deadline` : dateText;
      datesCell.appendChild(line);
    });
  }
  body.appendChild(factRow("Key dates", datesCell));
}

function factRow(label, content) {
  const row = document.createElement("tr");
  const heading = document.createElement("th");
  heading.scope = "row";
  heading.textContent = label;
  const cell = document.createElement("td");
  if (typeof content === "string") {
    cell.textContent = content;
  } else {
    cell.appendChild(content);
  }
  row.append(heading, cell);
  return row;
}

function renderSteps(plan, resultId, sources) {
  const list = $("#plan-steps");
  list.textContent = "";

  const steps = Array.isArray(plan.steps) ? plan.steps : [];
  const mockUrls = new Set(
    (sources || []).filter((source) => source.mock).map((source) => source.url)
  );

  $("#plan-count").textContent = steps.length
    ? `${steps.length} step${steps.length === 1 ? "" : "s"}`
    : "";

  if (!steps.length) {
    const item = document.createElement("li");
    item.className = "muted";
    item.textContent = "No steps were produced. Use the source list to act.";
    list.appendChild(item);
    return;
  }

  steps.forEach((step, index) => {
    const item = document.createElement("li");
    item.className = "step";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "step__check";
    checkbox.id = `step-${resultId}-${index}`;

    const body = document.createElement("div");
    body.className = "step__body";

    const number = document.createElement("span");
    number.className = "step__number";
    number.textContent = `Step ${index + 1}`;

    const action = document.createElement("label");
    action.className = "step__action";
    action.htmlFor = checkbox.id;
    action.textContent = humanizeDates(step.action || "");
    if (!step.action) {
      checkbox.setAttribute("aria-label", `Mark step ${index + 1} as done`);
    }

    const meta = document.createElement("div");
    meta.className = "step__meta";

    if (step.due_date) {
      const due = document.createElement("span");
      due.className = "due-chip";
      due.appendChild(icon("calendar"));
      due.appendChild(document.createTextNode(formatDate(step.due_date)));
      meta.appendChild(due);
    }

    const tier = sourceTier(step.source_url, mockUrls);
    if (tier) {
      const link = document.createElement("a");
      link.className = `source-link source-link--${tier.key}`;
      link.href = safeUrl(step.source_url);
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.title = `Opens ${tier.host} in a new tab`;
      link.appendChild(icon("external"));
      link.appendChild(document.createTextNode(`${tier.label} · ${tier.host}`));
      meta.appendChild(link);
    } else {
      const unverified = document.createElement("span");
      unverified.className = "unverified";
      unverified.textContent = "General advice · no source";
      unverified.title = "No page supported this step. Confirm with the issuer before acting.";
      meta.appendChild(unverified);
    }

    body.append(number, action, meta);
    item.append(checkbox, body);
    list.appendChild(item);
  });
}

function renderDraft(draft, issuer) {
  const box = $("#draft-box");
  const text = String(draft || "").trim();
  if (!text) {
    box.hidden = true;
    $("#draft-text").textContent = "";
    return;
  }
  box.hidden = false;
  box.open = false;
  $("#draft-label").textContent = issuer
    ? `Reply to ${shortIssuer(issuer)}`
    : "Reply to the issuer";
  $("#draft-text").textContent = text;
  $("#copy-label").textContent = "Copy reply";
}

function renderSources(sources) {
  const list = $("#sources");
  list.textContent = "";

  $("#source-count").textContent = sources.length
    ? `${sources.length} source${sources.length === 1 ? "" : "s"}`
    : "none";

  if (!sources.length) {
    const item = document.createElement("li");
    item.className = "muted";
    item.textContent = "No official page was found. Confirm the steps with the issuer before you act.";
    list.appendChild(item);
    return;
  }

  sources.forEach((source, index) => {
    const item = document.createElement("li");
    item.className = "source";

    const sourceIndex = document.createElement("span");
    sourceIndex.className = "source__index";
    sourceIndex.textContent = `[${index + 1}]`;

    const body = document.createElement("div");
    body.className = "source__body";

    const titleRow = document.createElement("div");
    titleRow.className = "source__title";

    const url = safeUrl(source.url);
    if (url) {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = source.title || source.url;
      link.setAttribute("aria-label", `${source.title || source.url} (opens in a new tab)`);
      titleRow.appendChild(link);
    } else {
      const label = document.createElement("span");
      label.textContent = source.title || source.url || "Source";
      titleRow.appendChild(label);
    }

    if (source.mock) {
      const tag = document.createElement("span");
      tag.className = "mock-tag";
      tag.textContent = "Demo page";
      titleRow.appendChild(tag);
    }

    body.appendChild(titleRow);

    if (url) {
      try {
        const domain = document.createElement("p");
        domain.className = "source__domain";
        domain.textContent = new URL(url).hostname.replace(/^www\./, "");
        body.appendChild(domain);
      } catch (error) {
        // keep the source readable even if the URL is unusual
      }
    }

    if (source.snippet) {
      const snippet = document.createElement("p");
      snippet.className = "source__snippet";
      snippet.textContent = cleanSnippet(source.snippet);
      body.appendChild(snippet);
    }

    item.append(sourceIndex, body);
    list.appendChild(item);
  });
}

function renderPlanWarning(sources) {
  const warning = $("#plan-warning");
  const hasMock = sources.some((source) => source.mock);
  const hasOfficial = sources.some((source) => isOfficialHost(hostname(source.url)));

  let message = "";
  if (hasMock) {
    message = "Demo pages. These links are placeholders, not live guidance.";
  } else if (sources.length && !hasOfficial) {
    message = "No official page found. These steps are general advice. Confirm with the issuer before you act.";
  } else if (!sources.length) {
    message = "No sources were returned. These steps are general advice.";
  }

  warning.textContent = message;
  warning.hidden = !message;
}

function renderDocRail(extraction, due) {
  const isSample = state.mode === "sample" || !state.file;
  const thumb = $("#doc-thumb");
  thumb.src = isSample ? "/sample-bill.png" : state.previewUrl;
  thumb.alt = isSample
    ? "Sample BESCOM electricity bill"
    : `Preview of ${state.file.name}`;

  $("#doc-name").textContent = isSample ? "Sample BESCOM bill" : state.file.name;
  $("#doc-meta").textContent = [extraction.document_type, extraction.recipient_name]
    .filter(Boolean)
    .join(" · ");
  $("#doc-issuer").textContent = extraction.issuer || "Not found";
  $("#doc-due").textContent = due ? formatDate(due) : "No date";
  $("#doc-amount").textContent = (extraction.amounts && extraction.amounts[0]) || "Not found";
  $("#new-doc-btn").hidden = false;
}

/* ---------------------------------------------------------------------- */
/* Source tiers and dates                                                  */
/* ---------------------------------------------------------------------- */
function hostname(url) {
  try {
    return (new URL(url).hostname || "").toLowerCase();
  } catch (error) {
    return "";
  }
}

function isOfficialHost(host) {
  return host.endsWith(".gov")
    || host.endsWith(".gov.in")
    || host.endsWith(".nic.in")
    || host.endsWith(".co.in");
}

function sourceTier(url, mockUrls) {
  if (!url) return null;
  if (mockUrls && mockUrls.has(url)) {
    return { key: "demo", label: "Demo page", host: hostname(url).replace(/^www\./, "") || "placeholder" };
  }
  const host = hostname(url);
  if (!host) return null;
  const displayHost = host.replace(/^www\./, "");
  if (host.endsWith(".gov") || host.endsWith(".gov.in") || host.endsWith(".nic.in")) {
    return { key: "official", label: "Official page", host: displayHost };
  }
  if (host.endsWith(".co.in")) {
    return { key: "issuer", label: "Issuer page", host: displayHost };
  }
  return { key: "third", label: "Source page", host: displayHost };
}

function shortIssuer(value) {
  const text = String(value || "").trim();
  const match = text.match(/\(([^)]{1,24})\)/);
  if (match && !/sample|copy|duplicate/i.test(match[1])) {
    return match[1];
  }
  return text;
}

function findDue(extraction, plan) {
  const keyDates = (extraction.key_dates || [])
    .filter((item) => item.is_deadline && validDate(item.date))
    .map((item) => item.date)
    .sort();
  if (keyDates.length) return keyDates[0];

  const stepDates = (plan.steps || [])
    .filter((step) => validDate(step.due_date))
    .map((step) => step.due_date)
    .sort();
  return stepDates[0] || "";
}

function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ""))) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime());
}

function formatDate(value) {
  if (!value) return "";
  if (!validDate(value)) return String(value);
  const date = new Date(`${value}T00:00:00Z`);
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function humanizeDates(text) {
  return String(text || "").replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (match) => formatDate(match));
}

function relativeDue(value) {
  if (!validDate(value)) return "Check the whole page.";
  const now = new Date();
  const [year, month, day] = value.split("-").map(Number);
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const target = Date.UTC(year, month - 1, day);
  const days = Math.round((target - today) / 86400000);
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  if (days > 1) return `Due in ${days} days`;
  if (days === -1) return "Overdue by 1 day";
  return `Overdue by ${Math.abs(days)} days`;
}

function cleanSnippet(text) {
  return String(text || "")
    .replace(/[#*_`>]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/* ---------------------------------------------------------------------- */
/* Utilities                                                               */
/* ---------------------------------------------------------------------- */
function icon(name, className = "icon") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.appendChild(use);
  return svg;
}

function safeUrl(value) {
  if (!value) return "";
  try {
    const url = new URL(String(value), window.location.origin);
    if (url.protocol === "http:" || url.protocol === "https:") return url.href;
  } catch (error) {
    return "";
  }
  return "";
}

function setLive(message) {
  const element = $("#live-status");
  if (!element) return;
  element.textContent = "";
  window.requestAnimationFrame(() => {
    element.textContent = message;
  });
}

async function copyDraft() {
  const text = $("#draft-text").textContent;
  if (!text) return;

  let copied = false;
  try {
    await navigator.clipboard.writeText(text);
    copied = true;
  } catch (error) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      copied = document.execCommand("copy");
    } catch (fallbackError) {
      copied = false;
    }
    area.remove();
  }

  const label = $("#copy-label");
  if (copied) {
    label.textContent = "Copied";
    setLive("Reply copied to the clipboard.");
    window.setTimeout(() => {
      label.textContent = "Copy reply";
    }, 1600);
  } else {
    toast("Copy failed. Select the reply text and copy it manually.");
  }
}

function toast(message) {
  const element = $("#toast");
  element.hidden = true;
  element.textContent = "";
  window.requestAnimationFrame(() => {
    element.hidden = false;
    element.textContent = message;
  });
  if (state.toastTimer) window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => {
    element.hidden = true;
  }, 6000);
}
