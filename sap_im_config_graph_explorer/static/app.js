const state = {
  graph: { nodes: [], links: [] },
  cy: null,
  html: "",
  htmlName: "sap-im-plan.html",
};

const statusEl = document.getElementById("status");
const fileInput = document.getElementById("xml-files");
const graphEl = document.getElementById("graph");
const typeFilter = document.getElementById("type-filter");
const searchInput = document.getElementById("search");
const rawXmlEl = document.getElementById("raw-xml");
const summaryEl = document.getElementById("node-summary");

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
  renderGraph();
  setStatus(`${payload.nodes.length} nodes, ${payload.links.length} links`);
}

async function generateHtml() {
  const file = fileInput.files[0];
  if (!file) return setStatus("Select an XML file.");
  const formData = new FormData();
  formData.append("file", file);
  formData.append("variant", document.getElementById("variant").value);
  setStatus("Generating HTML...");
  const response = await fetch("/api/convert/html", { method: "POST", body: formData });
  const payload = await response.json();
  if (!response.ok || !payload.ok) return setStatus(payload.error || "HTML generation failed.");
  state.html = payload.html;
  state.htmlName = payload.outputFile;
  document.getElementById("html-preview").srcdoc = payload.html;
  const download = document.getElementById("html-download");
  download.href = URL.createObjectURL(new Blob([payload.html], { type: "text/html" }));
  download.download = payload.outputFile;
  document.querySelector('[data-view="html-view"]').click();
  setStatus(`Generated ${payload.outputFile}`);
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

function showNodeDetails(node) {
  summaryEl.innerHTML = `
    <dt>Name</dt><dd>${escapeHtml(node.label)}</dd>
    <dt>Type</dt><dd>${escapeHtml(node.type)}</dd>
    <dt>Source file</dt><dd>${escapeHtml(node.sourceFile)}</dd>
    <dt>XML path</dt><dd>${escapeHtml(node.xmlPath)}</dd>
    <dt>Metadata</dt><dd>${escapeHtml(JSON.stringify(node.metadata, null, 2))}</dd>
  `;
  rawXmlEl.textContent = node.rawXml || "";
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
