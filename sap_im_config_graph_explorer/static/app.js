const state = {
  graph: { nodes: [], links: [], findings: [] },
  cy: null,
  html: { before: null, after: null },
  htmlDownloadUrls: { before: "", after: "" },
};

const HTML_COMPARISON_STORAGE_KEY = "sap-im-html-comparison-v1";
const statusEl = document.getElementById("status");
const fileInput = document.getElementById("xml-files");
const graphEl = document.getElementById("graph");
const typeFilter = document.getElementById("type-filter");
const searchInput = document.getElementById("search");
const rawXmlEl = document.getElementById("raw-xml");
const summaryEl = document.getElementById("node-summary");
const findingsEl = document.getElementById("validation-findings");

document.getElementById("graph-button").addEventListener("click", generateGraph);
document.getElementById("html-button").addEventListener("click", generateHtml);
document.getElementById("export-button").addEventListener("click", exportGraph);
searchInput.addEventListener("input", renderGraph);
typeFilter.addEventListener("change", renderGraph);

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab, .view").forEach((el) => el.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(tab.dataset.view).classList.add("active");
    if (state.cy) state.cy.resize().fit();
  });
});

loadHtmlComparison();

async function generateGraph() {
  const files = [...fileInput.files];
  if (!files.length) return setStatus("Select one or more XML files.");
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  setStatus("Generating graph...");
  const response = await fetch("/api/graph", { method: "POST", body: formData });
  const payload = await response.json();
  if (!response.ok) return setStatus(payload.error || "Graph generation failed.");
  state.graph = payload;
  populateTypeFilter(payload.nodes);
  renderFindings(payload.findings || []);
  renderGraph();
  setStatus(graphStatus(payload));
}

async function generateHtml() {
  const file = fileInput.files[0];
  if (!file) return setStatus("Select an XML file.");
  const variant = document.getElementById("variant").value;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("variant", variant);
  setStatus("Generating HTML...");
  const response = await fetch("/api/convert/html", { method: "POST", body: formData });
  const payload = await response.json();
  if (!response.ok || !payload.ok) return setStatus(payload.error || "HTML generation failed.");
  const previousAfter = state.html.after;
  const after = {
    html: payload.html,
    inputName: file.name,
    outputFile: payload.outputFile,
    variant,
  };
  const savedBaseline = previousAfter && sameHtmlSource(previousAfter, after);
  state.html.before = savedBaseline ? previousAfter : null;
  state.html.after = after;
  const persisted = saveHtmlComparison();
  renderHtmlComparison();
  document.querySelector('[data-view="after-html-view"]').click();
  if (savedBaseline) {
    setStatus(
      `Generated ${payload.outputFile}. The prior output is available under Before Change HTML.${persisted ? "" : " Browser storage could not retain the comparison after this page closes."}`
    );
  } else {
    setStatus(
      `Generated ${payload.outputFile}. Generate again with the same XML after a change to create a before-and-after comparison.${persisted ? "" : " Browser storage could not retain this baseline after this page closes."}`
    );
  }
}

function sameHtmlSource(before, after) {
  return before.inputName === after.inputName && before.variant === after.variant;
}

function isHtmlOutput(value) {
  return value
    && typeof value.html === "string"
    && typeof value.inputName === "string"
    && typeof value.outputFile === "string"
    && typeof value.variant === "string";
}

function loadHtmlComparison() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(HTML_COMPARISON_STORAGE_KEY) || "null");
    if (saved) {
      state.html.before = isHtmlOutput(saved.before) ? saved.before : null;
      state.html.after = isHtmlOutput(saved.after) ? saved.after : null;
    }
  } catch (_error) {
    state.html.before = null;
    state.html.after = null;
  }
  renderHtmlComparison();
}

function saveHtmlComparison() {
  try {
    window.localStorage.setItem(HTML_COMPARISON_STORAGE_KEY, JSON.stringify(state.html));
    return true;
  } catch (_error) {
    return false;
  }
}

function renderHtmlComparison() {
  renderHtmlOutput("before");
  renderHtmlOutput("after");
}

function renderHtmlOutput(kind) {
  const output = state.html[kind];
  const preview = document.getElementById(`${kind}-html-preview`);
  const download = document.getElementById(`${kind}-html-download`);
  const meta = document.getElementById(`${kind}-html-meta`);
  const displayName = kind === "before" ? "Before Change HTML" : "After Change HTML";

  if (!output) {
    preview.srcdoc = emptyHtmlOutputMessage(kind);
    download.hidden = true;
    meta.textContent = kind === "before"
      ? "No comparison baseline has been saved."
      : "Generate HTML to create the current output.";
    return;
  }

  preview.srcdoc = output.html;
  download.hidden = false;
  download.textContent = `Download ${displayName}`;
  download.download = comparisonOutputName(output.outputFile, kind);
  if (state.htmlDownloadUrls[kind]) {
    URL.revokeObjectURL(state.htmlDownloadUrls[kind]);
  }
  state.htmlDownloadUrls[kind] = URL.createObjectURL(
    new Blob([output.html], { type: "text/html" })
  );
  download.href = state.htmlDownloadUrls[kind];
  meta.textContent = `${output.inputName} (${output.variant})`;
}

function comparisonOutputName(outputFile, kind) {
  const dot = outputFile.lastIndexOf(".");
  const stem = dot > 0 ? outputFile.slice(0, dot) : outputFile;
  return `${stem}-${kind}-change.html`;
}

function emptyHtmlOutputMessage(kind) {
  const message = kind === "before"
    ? "No before-change HTML is available yet. Generate HTML once to establish a baseline, then generate the same XML again after an update."
    : "Generate HTML to create the after-change output.";
  return `<p style="font-family:Arial,Helvetica,sans-serif;margin:24px;color:#4c5a67">${message}</p>`;
}

function renderGraph() {
  if (state.cy) state.cy.destroy();
  const term = searchInput.value.trim().toLowerCase();
  const type = typeFilter.value;
  const nodes = state.graph.nodes.filter((node) => {
    const matchesSearch = !term || node.label.toLowerCase().includes(term);
    const matchesType = !type || node.type === type;
    return matchesSearch && matchesType;
  });
  const nodeIds = new Set(nodes.map((node) => node.id));
  const links = state.graph.links.filter((link) => nodeIds.has(link.source) && nodeIds.has(link.target));
  const elements = [
    ...nodes.map((node) => ({ data: { ...node, displayColor: colorForType(node.type) } })),
    ...links.map((link, index) => ({ data: { ...link, id: `edge-${index}` } })),
  ];
  state.cy = cytoscape({
    container: graphEl,
    elements,
    wheelSensitivity: 0.18,
    style: [
      {
        selector: "node",
        style: {
          "background-color": "data(displayColor)",
          "border-color": "#ffffff",
          "border-width": 2,
          color: "#1c2630",
          label: "data(label)",
          "font-size": 11,
          height: 30,
          "text-background-color": "#ffffff",
          "text-background-opacity": 0.86,
          "text-background-padding": 3,
          "text-margin-y": -8,
          "text-valign": "bottom",
          width: 30,
        },
      },
      {
        selector: "edge",
        style: {
          "curve-style": "bezier",
          "line-color": "#8fa1b2",
          "target-arrow-color": "#8fa1b2",
          "target-arrow-shape": "triangle",
          width: 1.4,
        },
      },
      {
        selector: "edge:selected",
        style: {
          color: "#1c2630",
          label: "data(relationship)",
          "font-size": 10,
          "line-color": "#1b5e7a",
          "target-arrow-color": "#1b5e7a",
          width: 3,
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-color": "#1c2630",
          "border-width": 4,
        },
      },
    ],
    layout: { name: "cose", animate: false, fit: true, padding: 36 },
  });
  state.cy.on("tap", "node", (event) => showNodeDetails(event.target.data()));
  state.cy.on("tap", "edge", (event) => showEdgeDetails(event.target.data()));
}

function populateTypeFilter(nodes) {
  const selected = typeFilter.value;
  const types = [...new Set(nodes.map((node) => node.type))].sort();
  typeFilter.innerHTML = '<option value="">All types</option>';
  types.forEach((type) => {
    const option = document.createElement("option");
    option.value = type;
    option.textContent = type;
    typeFilter.appendChild(option);
  });
  typeFilter.value = types.includes(selected) ? selected : "";
}

function renderFindings(findings) {
  if (!findings.length) {
    findingsEl.innerHTML = '<p class="empty-findings">No validation findings.</p>';
    return;
  }

  const errorCount = findings.filter((finding) => finding.severity === "error").length;
  const warningCount = findings.filter((finding) => finding.severity === "warning").length;
  const summary = `${errorCount} error${errorCount === 1 ? "" : "s"}, ${warningCount} warning${warningCount === 1 ? "" : "s"}`;
  const items = findings.map((finding) => `
    <li class="finding ${escapeHtml(finding.severity || "warning")}">
      <strong class="finding-title">${escapeHtml(finding.code || "validation finding")}</strong>
      <p class="finding-message">${escapeHtml(finding.message || "No message supplied.")}</p>
    </li>
  `).join("");

  findingsEl.innerHTML = `<p class="findings-summary">${escapeHtml(summary)}</p><ul class="findings-list">${items}</ul>`;
}

function graphStatus(payload) {
  const findings = payload.findings || [];
  if (!findings.length) return `${payload.nodes.length} nodes, ${payload.links.length} links, no findings`;
  const errorCount = findings.filter((finding) => finding.severity === "error").length;
  const warningCount = findings.filter((finding) => finding.severity === "warning").length;
  return `${payload.nodes.length} nodes, ${payload.links.length} links, ${errorCount} error${errorCount === 1 ? "" : "s"}, ${warningCount} warning${warningCount === 1 ? "" : "s"}`;
}

function showNodeDetails(node) {
  const hierarchy = hierarchyFor(node);
  summaryEl.innerHTML = `
    <dt>Name</dt><dd>${escapeHtml(node.label)}</dd>
    <dt>Type</dt><dd>${escapeHtml(node.type)}</dd>
    <dt>Associated plans</dt><dd>${escapeHtml(hierarchy.plans.join(", ") || "None")}</dd>
    <dt>Associated plan components</dt><dd>${escapeHtml(hierarchy.components.join(", ") || "None")}</dd>
    <dt>Associated rules</dt><dd>${escapeHtml(hierarchy.rules.join(", ") || "None")}</dd>
    <dt>Source file</dt><dd>${escapeHtml(node.sourceFile)}</dd>
    <dt>XML path</dt><dd>${escapeHtml(node.xmlPath)}</dd>
    <dt>Metadata</dt><dd>${escapeHtml(JSON.stringify(node.metadata, null, 2))}</dd>
  `;
  rawXmlEl.textContent = node.rawXml || "";
}

function hierarchyFor(node) {
  const nodesById = new Map(state.graph.nodes.map((item) => [item.id, item]));
  const links = state.graph.links;
  const componentIds = new Set();
  const planIds = new Set();
  const ruleIds = new Set();

  if (node.type === "Rule") {
    ruleIds.add(node.id);
    links
      .filter((link) => link.relationship === "belongs_to_plan_component" && link.source === node.id)
      .forEach((link) => componentIds.add(link.target));
  } else if (node.type === "PlanComponent") {
    componentIds.add(node.id);
  } else if (node.type === "Plan") {
    planIds.add(node.id);
    links
      .filter((link) => link.relationship === "belongs_to_plan" && link.target === node.id)
      .forEach((link) => componentIds.add(link.source));
  }

  componentIds.forEach((componentId) => {
    links
      .filter((link) => link.relationship === "belongs_to_plan" && link.source === componentId)
      .forEach((link) => planIds.add(link.target));
    links
      .filter((link) => link.relationship === "belongs_to_plan_component" && link.target === componentId)
      .forEach((link) => ruleIds.add(link.source));
  });

  return {
    plans: labelsForIds(planIds, nodesById),
    components: labelsForIds(componentIds, nodesById),
    rules: labelsForIds(ruleIds, nodesById),
  };
}

function labelsForIds(ids, nodesById) {
  return [...ids]
    .map((id) => nodesById.get(id)?.label)
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right));
}

function showEdgeDetails(edge) {
  summaryEl.innerHTML = `
    <dt>Relationship</dt><dd>${escapeHtml(edge.relationship)}</dd>
    <dt>Confidence</dt><dd>${escapeHtml(edge.confidence)}</dd>
    <dt>Source</dt><dd>${escapeHtml(edge.source)}</dd>
    <dt>Target</dt><dd>${escapeHtml(edge.target)}</dd>
  `;
  rawXmlEl.textContent = JSON.stringify(edge.metadata || {}, null, 2);
}

async function exportGraph() {
  const response = await fetch("/api/export/graph-json", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.graph),
  });
  if (!response.ok) return setStatus("JSON export failed.");
  const blob = await response.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "sap-im-config-graph.json";
  link.click();
  URL.revokeObjectURL(link.href);
  setStatus("Exported graph JSON");
}

function setStatus(message) {
  statusEl.textContent = message;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function colorForType(type) {
  return {
    FixedValue: "#8a5a14",
    Formula: "#5f4aa0",
    LookupTable: "#28724f",
    Quota: "#8a3f23",
    RateTable: "#00695c",
    Territory: "#6a5b22",
    Variable: "#795548",
    Rule: "#ad1457",
    Plan: "#1b5e7a",
    PlanComponent: "#455a64",
    EventType: "#c2185b",
    CreditType: "#2e7d32",
    EarningCode: "#1565c0",
    EarningGroup: "#3949ab",
    BusinessUnit: "#00838f",
    ProcessingUnit: "#9e5d00",
    Calendar: "#616161",
  }[type] || "#52616f";
}
