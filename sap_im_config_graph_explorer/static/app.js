const state = {
  graph: { nodes: [], links: [], findings: [] },
  cy: null,
  lineageCy: null,
  selectedRule: null,
  html: null,
  htmlDownloadUrl: "",
};

window.state = state;

function filterGraphElements(graph, filters) {
  const term = (filters.search || "").trim().toLowerCase();
  const effectiveDate = filters.effectiveDate || "";
  const nodes = graph.nodes.filter((node) => {
    const startDate = node.metadata?.effectiveStartDate || "";
    const endDate = node.metadata?.effectiveEndDate || "";
    const matchesSearch = !term || node.label.toLowerCase().includes(term);
    const matchesType = !filters.type || node.type === filters.type;
    const matchesSourceFile = !filters.sourceFile || node.sourceFile === filters.sourceFile;
    const matchesEffectiveDate = !effectiveDate
      || ((!startDate || startDate <= effectiveDate) && (!endDate || effectiveDate <= endDate));
    return matchesSearch && matchesType && matchesSourceFile && matchesEffectiveDate;
  });
  const nodeIds = new Set(nodes.map((node) => node.id));
  const links = graph.links.filter(
    (link) => nodeIds.has(link.source)
      && nodeIds.has(link.target)
      && (!filters.relationship || link.relationship === filters.relationship)
      && (!filters.confidence || link.confidence === filters.confidence)
  );
  if (!filters.relationship && !filters.confidence) return { nodes, links };

  const linkedNodeIds = new Set(
    links.flatMap((link) => [link.source, link.target])
  );
  return {
    nodes: nodes.filter((node) => linkedNodeIds.has(node.id)),
    links,
  };
}

window.filterGraphElements = filterGraphElements;

function selectRuleLineage(graph, ruleId, snapshotId) {
  const nodes = graph?.nodes || [];
  const links = graph?.links || [];
  const selectedRule = nodes.find(
    (node) => node.id === ruleId && node.snapshotId === snapshotId && node.type === "Rule"
  );
  if (!selectedRule) return { nodes: [], links: [], hasResolvedContainment: false };

  const nodesById = new Map(
    nodes
      .filter((node) => node.snapshotId === snapshotId)
      .filter((node) => ["Rule", "PlanComponent", "Plan"].includes(node.type))
      .map((node) => [node.id, node])
  );
  const lineageNodes = new Map([[selectedRule.id, selectedRule]]);
  const lineageLinks = new Map();
  const addLink = (link) => {
    if (link.id) lineageLinks.set(link.id, link);
  };

  const componentIds = new Set();
  links
    .filter(
      (link) => link.relationship === "belongs_to_plan_component"
        && link.source === selectedRule.id
        && nodesById.get(link.target)?.type === "PlanComponent"
    )
    .forEach((link) => {
      componentIds.add(link.target);
      lineageNodes.set(link.target, nodesById.get(link.target));
      addLink(link);
    });

  componentIds.forEach((componentId) => {
    links
      .filter(
        (link) => link.relationship === "belongs_to_plan"
          && link.source === componentId
          && nodesById.get(link.target)?.type === "Plan"
      )
      .forEach((link) => {
        lineageNodes.set(link.target, nodesById.get(link.target));
        addLink(link);
      });
  });

  const compareByCanonicalKeyAndId = (leftKey, leftId, rightKey, rightId) =>
    String(leftKey).localeCompare(String(rightKey)) || String(leftId).localeCompare(String(rightId));
  const orderNodes = (left, right) => compareByCanonicalKeyAndId(
    left.canonicalKey || left.id,
    left.id,
    right.canonicalKey || right.id,
    right.id
  );
  const linkCanonicalKey = (link) => {
    const sourceKey = nodesById.get(link.source)?.canonicalKey || link.source;
    const targetKey = nodesById.get(link.target)?.canonicalKey || link.target;
    return `${sourceKey}\u0000${link.relationship || ""}\u0000${targetKey}`;
  };
  const orderLinks = (left, right) => compareByCanonicalKeyAndId(
    linkCanonicalKey(left),
    left.id,
    linkCanonicalKey(right),
    right.id
  );
  return {
    nodes: [...lineageNodes.values()].sort(orderNodes),
    links: [...lineageLinks.values()].sort(orderLinks),
    hasResolvedContainment: lineageLinks.size > 0,
  };
}

window.selectRuleLineage = selectRuleLineage;

let latestGraphRequestId = 0;
let pendingGraphGeneration = null;

const statusEl = document.getElementById("status");
const themeToggle = document.getElementById("theme-toggle");
const npFileInput = document.getElementById("np-xml-files");
const pFileInput = document.getElementById("p-xml-files");
const topologySelect = document.getElementById("topology-mode");
const graphEl = document.getElementById("graph");
const lineageGraphEl = document.getElementById("lineage-graph");
const lineageTab = document.getElementById("lineage-tab");
const lineageSummaryEl = document.getElementById("lineage-summary");
const lineageDescriptionEl = document.getElementById("lineage-description");
const lineageEmptyEl = document.getElementById("lineage-empty");
const typeFilter = document.getElementById("type-filter");
const searchInput = document.getElementById("search");
const sourceFileFilter = document.getElementById("source-file-filter");
const relationshipFilter = document.getElementById("relationship-filter");
const confidenceFilter = document.getElementById("confidence-filter");
const effectiveDateFilter = document.getElementById("effective-date-filter");
const filterResultsEl = document.getElementById("filter-results");
const activeFiltersEl = document.getElementById("active-filters");
const clearFiltersButton = document.getElementById("clear-filters");
const rawXmlEl = document.getElementById("raw-xml");
const summaryEl = document.getElementById("node-summary");
const findingsEl = document.getElementById("validation-findings");
const riskContainer = document.getElementById("migration-risk-container");
const riskReportEl = document.getElementById("migration-risk-report");

document.getElementById("graph-button").addEventListener("click", requestGraphGeneration);
document.getElementById("html-button").addEventListener("click", generateHtml);
document.getElementById("export-button").addEventListener("click", exportGraph);
themeToggle.addEventListener("click", toggleTheme);
searchInput.addEventListener("input", renderGraphAndHtmlOutput);
typeFilter.addEventListener("change", renderGraphAndHtmlOutput);
sourceFileFilter.addEventListener("change", renderGraph);
relationshipFilter.addEventListener("change", renderGraph);
confidenceFilter.addEventListener("change", renderGraph);
effectiveDateFilter.addEventListener("input", renderGraph);
clearFiltersButton.addEventListener("click", clearAllFilters);
document.getElementById("lineage-back-button").addEventListener("click", () => switchWorkspace("graph-view"));
topologySelect.addEventListener("change", () => {
  if (npFileInput.files.length || pFileInput.files.length) {
    requestGraphGeneration();
  } else {
    setStatus(`Selected ${topologyLabel(topologySelect.value)} topology.`);
  }
});

initializeTheme();

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    if (tab.dataset.view === "lineage-view" && state.selectedRule) {
      const rule = state.graph.nodes.find(
        (node) => node.id === state.selectedRule.id && node.snapshotId === state.selectedRule.snapshotId
      );
      if (rule) return openRuleLineage(rule);
    }
    switchWorkspace(tab.dataset.view);
  });
});

function switchWorkspace(viewId) {
  document.querySelectorAll(".tab, .view").forEach((el) => el.classList.remove("active"));
  document.querySelector(`.tab[data-view="${viewId}"]`).classList.add("active");
  document.getElementById(viewId).classList.add("active");
  if (viewId === "lineage-view") {
    state.lineageCy?.resize().fit();
  } else if (viewId === "graph-view") {
    state.cy?.resize();
  }
}

function requestGraphGeneration() {
  const generation = generateGraph();
  pendingGraphGeneration = generation;
  generation.then(
    () => {
      if (pendingGraphGeneration === generation) pendingGraphGeneration = null;
    },
    () => {
      if (pendingGraphGeneration === generation) pendingGraphGeneration = null;
    },
  );
  return generation;
}

async function generateGraph() {
  const npFiles = [...npFileInput.files];
  const pFiles = [...pFileInput.files];
  if (!npFiles.length && !pFiles.length) return setStatus("Select one or more XML files.");

  const requestId = ++latestGraphRequestId;
  const topologyMode = topologySelect.value;

  const formData = new FormData();
  npFiles.forEach((file) => formData.append("np_files", file));
  pFiles.forEach((file) => formData.append("p_files", file));
  formData.append("topology_mode", topologyMode);

  setStatus("Generating graph...");
  const response = await fetch("/api/graph", { method: "POST", body: formData });
  const payload = await response.json();
  if (requestId !== latestGraphRequestId) return;
  if (!response.ok) return setStatus(payload.error || "Graph generation failed.");

  state.graph = payload;
  clearSelectedRule();
  destroyLineageRenderer();
  populateFilterControls(payload);
  renderFindings(payload.findings || []);
  renderRiskReport(payload.migrationRisk);
  renderGraph();
  setStatus(graphStatus(payload));
}

async function generateHtml() {
  const file = npFileInput.files[0] || pFileInput.files[0];
  if (!file) return setStatus("Select an XML file.");
  const variant = document.getElementById("variant").value;
  setStatus("Generating HTML...");
  try {
    state.html = await convertHtml(file, variant);
  } catch (error) {
    return setStatus(error.message || "HTML generation failed.");
  }
  renderFindings(state.html.findings || []);
  renderHtmlOutput();
  document.querySelector('[data-view="html-output-view"]').click();
  setStatus(`Generated ${state.html.outputFile}.`);
}

async function convertHtml(file, variant) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("variant", variant);
  formData.append("theme", currentTheme());
  const response = await fetch("/api/convert/html", { method: "POST", body: formData });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || `Unable to generate HTML for ${file.name}.`);
  }
  return {
    originalHtml: payload.html,
    inputName: file.name,
    outputFile: payload.outputFile,
    variant,
    findings: payload.findings || [],
  };
}

function renderHtmlOutput() {
  const output = state.html;
  const preview = document.getElementById("html-output-preview");
  const download = document.getElementById("html-output-download");
  const meta = document.getElementById("html-output-meta");
  preview.onload = () => enableHtmlPreviewAnchors(preview);

  if (!output) {
    preview.srcdoc = emptyHtmlOutputMessage();
    download.hidden = true;
    meta.textContent = "Select an XML file and generate HTML.";
    return;
  }

  const html = applyThemeToHtml(
    filterGeneratedHtml(output.originalHtml, {
      search: searchInput.value,
      type: typeFilter.value,
    }),
    currentTheme()
  );
  preview.srcdoc = html;
  download.hidden = false;
  download.textContent = "Download HTML";
  download.download = output.outputFile;
  if (state.htmlDownloadUrl) {
    URL.revokeObjectURL(state.htmlDownloadUrl);
  }
  state.htmlDownloadUrl = URL.createObjectURL(
    new Blob([html], { type: "text/html" })
  );
  download.href = state.htmlDownloadUrl;
  meta.textContent = `${output.inputName} (${output.variant})`;
}

function filterGeneratedHtml(originalHtml, filters) {
  const term = (filters.search || "").trim().toLowerCase();
  const objectType = filters.type || "";
  if (!term && !objectType) return originalHtml;

  const documentForOutput = new DOMParser().parseFromString(originalHtml, "text/html");
  const matches = (element) => {
    const label = element.getAttribute("data-object-label") || "";
    return (!term || label.toLowerCase().includes(term))
      && (!objectType || element.getAttribute("data-object-type") === objectType);
  };

  documentForOutput.querySelectorAll("section[data-object-type][data-object-label]").forEach((section) => {
    if (!matches(section)) section.remove();
  });
  documentForOutput.querySelectorAll("[data-object-entry][data-object-type][data-object-label]").forEach((entry) => {
    if (!matches(entry)) entry.remove();
  });

  const doctype = originalHtml.match(/^\s*(<!doctype[^>]*>)/i)?.[1] || "";
  return `${doctype}${doctype ? "\n" : ""}${documentForOutput.documentElement.outerHTML}`;
}

function enableHtmlPreviewAnchors(preview) {
  const previewDocument = preview.contentDocument;
  if (!previewDocument) return;
  previewDocument.addEventListener("click", (event) => {
    const link = event.target.closest?.("a[href]");
    const href = link?.getAttribute("href");
    if (!href?.startsWith("#")) return;

    event.preventDefault();
    const anchor = href.slice(1);
    const target = [...previewDocument.querySelectorAll("[name], [id]")].find(
      (element) => element.getAttribute("name") === anchor || element.id === anchor
    );
    target?.scrollIntoView({ block: "start" });
  });
}

function emptyHtmlOutputMessage() {
  const message = "Select an XML file and generate HTML.";
  return `<p style="font-family:Inter,Segoe UI,Arial,Helvetica,sans-serif;margin:24px;color:#333333">${message}</p>`;
}

function initializeTheme() {
  const savedTheme = localStorage.getItem("sap-im-config-explorer-theme");
  applyTheme(savedTheme === "dark" ? "dark" : "light", false);
}

function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}

function applyTheme(theme, persist = true) {
  document.documentElement.dataset.theme = theme;
  themeToggle.setAttribute("aria-pressed", String(theme === "dark"));
  themeToggle.textContent = theme === "dark" ? "Light mode" : "Dark mode";
  if (persist) localStorage.setItem("sap-im-config-explorer-theme", theme);
  if (state.html) {
    renderHtmlOutput();
  }
  if (state.graph.nodes.length) renderGraph();
}

function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function applyThemeToHtml(html, theme) {
  return html.replace(/<html(?:\s+data-theme="(?:light|dark)")?>/i, `<html data-theme="${theme}">`);
}

function renderGraphAndHtmlOutput() {
  renderGraph();
  if (state.html) renderHtmlOutput();
}

function renderGraph() {
  if (state.cy) state.cy.destroy();
  const graphTheme = graphThemeColors();
  const { nodes, links } = filterGraphElements(state.graph, {
    search: searchInput.value,
    type: typeFilter.value,
    sourceFile: sourceFileFilter.value,
    relationship: relationshipFilter.value,
    confidence: confidenceFilter.value,
    effectiveDate: effectiveDateFilter.value,
  });
  renderFilterSummary(nodes.length, links.length);
  const elements = [
    ...nodes.map((node, index) => ({
      data: { ...node, displayColor: colorForType(node.type) },
      position: initialGraphPosition(index, nodes.length),
    })),
    ...links.map((link, index) => ({
      data: { ...link, id: link.id || `edge-${index}` },
    })),
  ];
  state.cy = cytoscape({
    container: graphEl,
    elements,
    style: cytoscapeStyles(graphTheme),
    layout: {
      name: "cose",
      animate: false,
      componentSpacing: 48,
      fit: true,
      idealEdgeLength: 88,
      nodeOverlap: 16,
      padding: 24,
      randomize: false,
    },
  });
  state.cy.on("tap", "node", (event) => {
    const node = event.target;
    highlightDependencies(node);
    showNodeDetails(node.data());
  });
  state.cy.on("tap", (event) => {
    if (event.target === state.cy || event.target.length === 0) {
      clearHighlighting();
      clearSelectedRule();
      summaryEl.innerHTML = "<dt>Selection</dt><dd>Select a graph item</dd>";
      rawXmlEl.textContent = "";
    }
  });
  state.cy.on("tap", "edge", (event) => showEdgeDetails(event.target.data()));
}

function cytoscapeStyles(graphTheme) {
  return [
      {
        selector: "node",
        style: {
          "background-color": "data(displayColor)",
          "border-color": graphTheme.border,
          "border-width": 2,
          color: graphTheme.text,
          label: "data(label)",
          "font-size": 11,
          height: 48,
          "text-background-color": graphTheme.labelBackground,
          "text-background-opacity": 0.92,
          "text-background-padding": 3,
          "text-halign": "center",
          "text-max-width": 96,
          "text-valign": "center",
          "text-wrap": "wrap",
          width: 112,
        },
      },
      {
        selector: "edge",
        style: {
          "curve-style": "bezier",
          "line-color": graphTheme.edge,
          "target-arrow-color": graphTheme.edge,
          "target-arrow-shape": "triangle",
          width: 1.4,
        },
      },
      {
        selector: "edge:selected",
        style: {
          color: graphTheme.text,
          label: "data(relationship)",
          "font-size": 10,
          "line-color": graphTheme.accent,
          "target-arrow-color": graphTheme.accent,
          width: 3,
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-color": graphTheme.accent,
          "border-width": 4,
        },
      },
      {
        selector: "node.dimmed",
        style: {
          opacity: 0.1,
          "text-opacity": 0.1,
          "text-background-opacity": 0.05,
        },
      },
      {
        selector: "edge.dimmed",
        style: {
          opacity: 0.1,
          "line-opacity": 0.1,
        },
      },
  ];
}

function initialGraphPosition(index, nodeCount) {
  const columns = Math.max(1, Math.ceil(Math.sqrt(nodeCount)));
  return {
    x: (index % columns) * 140,
    y: Math.floor(index / columns) * 80,
  };
}

function highlightDependencies(node) {
  const cy = state.cy;
  const neighborhood = node.successors().union(node.predecessors()).union(node);
  cy.elements().addClass("dimmed");
  neighborhood.removeClass("dimmed");
}

function clearHighlighting() {
  if (state.cy) {
    state.cy.elements().removeClass("dimmed");
  }
}

function populateFilterControls(graph) {
  populateSelect(
    typeFilter,
    graph.nodes.map((node) => node.type),
    "All types"
  );
  populateSelect(
    sourceFileFilter,
    graph.nodes.map((node) => node.sourceFile),
    "All source files",
    "source-file-filter-control"
  );
  populateSelect(
    relationshipFilter,
    graph.links.map((link) => link.relationship),
    "All relationships",
    "relationship-filter-control"
  );
  populateSelect(
    confidenceFilter,
    graph.links.map((link) => link.confidence),
    "All confidence levels",
    "confidence-filter-control"
  );

  const hasEffectiveDates = graph.nodes.some(
    (node) => node.metadata?.effectiveStartDate || node.metadata?.effectiveEndDate
  );
  effectiveDateFilter.disabled = !hasEffectiveDates;
  document.getElementById("effective-date-filter-control").hidden = !hasEffectiveDates;
  if (!hasEffectiveDates) effectiveDateFilter.value = "";
}

function populateSelect(select, sourceValues, allLabel, controlId = "") {
  const selected = select.value;
  const values = [...new Set(sourceValues.filter(Boolean))].sort();
  select.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = allLabel;
  select.appendChild(allOption);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  select.value = values.includes(selected) ? selected : "";
  select.disabled = values.length === 0;
  if (controlId) document.getElementById(controlId).hidden = values.length === 0;
}

function renderFilterSummary(visibleNodeCount, visibleLinkCount) {
  filterResultsEl.textContent = `Showing ${visibleNodeCount} of ${state.graph.nodes.length} nodes and ${visibleLinkCount} of ${state.graph.links.length} links`;
  const activeFilters = [
    ["Search", searchInput.value.trim()],
    ["Object type", typeFilter.value],
    ["Source file", sourceFileFilter.value],
    ["Relationship", relationshipFilter.value],
    ["Confidence", confidenceFilter.value],
    ["Effective on", effectiveDateFilter.value],
  ].filter(([, value]) => value);
  activeFiltersEl.textContent = activeFilters.length
    ? `Active filters: ${activeFilters.map(([label, value]) => `${label}: ${value}`).join("; ")}`
    : "Active filters: None";
  clearFiltersButton.disabled = activeFilters.length === 0;
}

function clearAllFilters() {
  searchInput.value = "";
  typeFilter.value = "";
  sourceFileFilter.value = "";
  relationshipFilter.value = "";
  confidenceFilter.value = "";
  effectiveDateFilter.value = "";
  renderGraphAndHtmlOutput();
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

function renderRiskReport(risk) {
  if (!risk) {
    riskContainer.hidden = true;
    riskReportEl.innerHTML = "";
    return;
  }

  riskContainer.hidden = false;
  const severity = risk.score >= 70 ? "high" : risk.score >= 30 ? "medium" : "low";
  const factors = (risk.factors || []).map((f) => `
    <li class="risk-factor ${escapeHtml(f.severity)}">
      <strong>${escapeHtml(f.code)}</strong> (Weight: ${f.weight}): ${escapeHtml(f.message)}
    </li>
  `).join("");

  riskReportEl.innerHTML = `
    <div class="risk-score-box">
      <span class="risk-score-value ${severity}">${Math.round(risk.score)}</span>
      <span class="risk-score-label">${severity.toUpperCase()} RISK</span>
    </div>
    <ul class="risk-factors-list">${factors}</ul>
  `;
}

function graphStatus(payload) {
  const findings = payload.findings || [];
  const prefix = `${topologyLabel(payload.topologyMode)} topology: `;
  if (!findings.length) return `${prefix}${payload.nodes.length} nodes, ${payload.links.length} links, no findings`;
  const errorCount = findings.filter((finding) => finding.severity === "error").length;
  const warningCount = findings.filter((finding) => finding.severity === "warning").length;
  return `${prefix}${payload.nodes.length} nodes, ${payload.links.length} links, ${errorCount} error${errorCount === 1 ? "" : "s"}, ${warningCount} warning${warningCount === 1 ? "" : "s"}`;
}

function topologyLabel(topologyMode) {
  return topologyMode === "full" ? "Full" : "Core";
}

function showNodeDetails(node) {
  if (node.type === "Rule") {
    state.selectedRule = { id: node.id, snapshotId: node.snapshotId };
    lineageTab.disabled = false;
  } else {
    clearSelectedRule();
  }
  const hierarchy = hierarchyFor(node);
  const riskFactor = state.graph.migrationRisk?.factors?.find((f) => f.nodeIds?.includes(node.id));
  const riskHtml = riskFactor ? `<dt>Migration risk</dt><dd class="risk-factor ${riskFactor.severity}"><strong>${riskFactor.code}</strong>: ${riskFactor.message}</dd>` : "";

  summaryEl.innerHTML = `
    <dt>Name</dt><dd>${escapeHtml(node.label)}</dd>
    ${riskHtml}
    <dt>Type</dt><dd>${escapeHtml(node.type)}</dd>
    ${node.type === "Rule" ? '<dt>Lineage</dt><dd><button id="open-lineage-button" type="button">Open lineage</button></dd>' : ""}
    <dt>Associated plans</dt><dd>${escapeHtml(hierarchy.plans.join(", ") || "None")}</dd>
    <dt>Associated plan components</dt><dd>${escapeHtml(hierarchy.components.join(", ") || "None")}</dd>
    <dt>Associated rules</dt><dd>${escapeHtml(hierarchy.rules.join(", ") || "None")}</dd>
    <dt>Source file</dt><dd>${escapeHtml(node.sourceFile)}</dd>
    <dt>XML path</dt><dd>${escapeHtml(node.xmlPath)}</dd>
    <dt>Metadata</dt><dd>${escapeHtml(JSON.stringify(node.metadata, null, 2))}</dd>
  `;
  rawXmlEl.textContent = node.rawXml || "";
  document.getElementById("open-lineage-button")?.addEventListener("click", () => openRuleLineage(node));
}

function clearSelectedRule() {
  state.selectedRule = null;
  lineageTab.disabled = true;
}

function openRuleLineage(rule) {
  const lineage = selectRuleLineage(state.graph, rule.id, rule.snapshotId);
  renderLineage(rule, lineage);
  switchWorkspace("lineage-view");
}

function renderLineage(rule, lineage) {
  destroyLineageRenderer();
  const componentCount = lineage.nodes.filter((node) => node.type === "PlanComponent").length;
  const planCount = lineage.nodes.filter((node) => node.type === "Plan").length;
  lineageSummaryEl.textContent = `${rule.label}: ${componentCount} plan component${componentCount === 1 ? "" : "s"} and ${planCount} plan${planCount === 1 ? "" : "s"}.`;
  renderLineageDescription(rule, lineage);

  if (!lineage.hasResolvedContainment) {
    lineageGraphEl.hidden = true;
    lineageEmptyEl.hidden = false;
    lineageEmptyEl.textContent = `No resolved containment path for ${rule.label}.`;
    return;
  }

  lineageEmptyEl.hidden = true;
  lineageEmptyEl.textContent = "";
  lineageGraphEl.hidden = false;
  const graphTheme = graphThemeColors();
  state.lineageCy = cytoscape({
    container: lineageGraphEl,
    elements: [
      ...lineage.nodes.map((node, index) => ({
        data: { ...node, displayColor: colorForType(node.type) },
        position: initialGraphPosition(index, lineage.nodes.length),
      })),
      ...lineage.links.map((link, index) => ({ data: { ...link, id: link.id || `lineage-edge-${index}` } })),
    ],
    style: cytoscapeStyles(graphTheme),
    layout: {
      name: "breadthfirst",
      animate: false,
      directed: true,
      fit: true,
      padding: 24,
      spacingFactor: 1.2,
    },
  });
}

function renderLineageDescription(rule, lineage) {
  const labelsById = new Map(lineage.nodes.map((node) => [node.id, node.label]));
  const componentLabels = lineage.nodes
    .filter((node) => node.type === "PlanComponent")
    .map((node) => node.label);
  const planLabels = lineage.nodes
    .filter((node) => node.type === "Plan")
    .map((node) => node.label);
  const relationshipDescriptions = lineage.links.map((link) => {
    const sourceLabel = labelsById.get(link.source) || link.source;
    const targetLabel = labelsById.get(link.target) || link.target;
    return `${sourceLabel} ${link.relationship.replaceAll("_", " ")} ${targetLabel}`;
  });
  const entries = [
    `Selected Rule: ${rule.label}`,
    `Plan Components: ${componentLabels.join(", ") || "None"}`,
    `Plans: ${planLabels.join(", ") || "None"}`,
    `Resolved containment relationships: ${relationshipDescriptions.join("; ") || "None"}`,
  ];
  lineageDescriptionEl.replaceChildren(...entries.map((text) => {
    const item = document.createElement("li");
    item.textContent = text;
    return item;
  }));
}

function destroyLineageRenderer() {
  if (state.lineageCy) state.lineageCy.destroy();
  state.lineageCy = null;
  lineageGraphEl.replaceChildren();
  lineageGraphEl.hidden = true;
  lineageEmptyEl.hidden = true;
  lineageEmptyEl.textContent = "";
  lineageSummaryEl.textContent = "Select a Rule to view its resolved containment lineage.";
  lineageDescriptionEl.replaceChildren();
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
  clearSelectedRule();
  summaryEl.innerHTML = `
    <dt>Relationship</dt><dd>${escapeHtml(edge.relationship)}</dd>
    <dt>Confidence</dt><dd>${escapeHtml(edge.confidence)}</dd>
    <dt>Source</dt><dd>${escapeHtml(edge.source)}</dd>
    <dt>Target</dt><dd>${escapeHtml(edge.target)}</dd>
  `;
  rawXmlEl.textContent = JSON.stringify(edge.metadata || {}, null, 2);
}

async function exportGraph() {
  while (pendingGraphGeneration) await pendingGraphGeneration;
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
  setStatus(`Exported ${topologyLabel(state.graph.topologyMode)} topology graph JSON`);
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
    FixedValue: "#81c784",
    Formula: "#2e7d32",
    LookupTable: "#81c784",
    Quota: "#ffa000",
    RateTable: "#2e7d32",
    Territory: "#81c784",
    Variable: "#ffa000",
    Rule: "#2e7d32",
    Plan: "#2e7d32",
    PlanComponent: "#81c784",
    EventType: "#ffa000",
    CreditType: "#2e7d32",
    EarningCode: "#81c784",
    EarningGroup: "#2e7d32",
    BusinessUnit: "#81c784",
    ProcessingUnit: "#ffa000",
    Calendar: "#2e7d32",
  }[type] || "#81c784";
}

function graphThemeColors() {
  const styles = getComputedStyle(document.documentElement);
  const color = (name) => styles.getPropertyValue(name).trim();
  return {
    accent: color("--forest-green"),
    border: color("--light-green"),
    edge: color("--graph-edge"),
    labelBackground: color("--graph-label-background"),
    text: color("--graph-label-text"),
  };
}
