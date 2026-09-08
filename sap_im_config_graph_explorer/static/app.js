const WAIVERS_STORAGE_KEY = "sap-im-config-explorer-waivers";

function isWaiverExpired(waiver) {
  if (!waiver || !waiver.expiresAt) return false;
  const expiryDate = new Date(waiver.expiresAt);
  if (isNaN(expiryDate.getTime())) return false;
  // If date only (YYYY-MM-DD), count expiry at end of that day
  if (/^\d{4}-\d{2}-\d{2}$/.test(waiver.expiresAt)) {
    expiryDate.setHours(23, 59, 59, 999);
  }
  return Date.now() > expiryDate.getTime();
}

function loadWaivers() {
  try {
    const raw = localStorage.getItem(WAIVERS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return {};
    }
    const validated = {};
    for (const [findingId, waiver] of Object.entries(parsed)) {
      if (
        waiver &&
        typeof waiver === "object" &&
        typeof waiver.findingId === "string" &&
        waiver.findingId &&
        typeof waiver.reason === "string" &&
        waiver.reason.trim() &&
        typeof waiver.reviewer === "string" &&
        waiver.reviewer.trim()
      ) {
        validated[findingId] = {
          findingId: waiver.findingId,
          reason: waiver.reason.trim(),
          reviewer: waiver.reviewer.trim(),
          createdAt: typeof waiver.createdAt === "string" ? waiver.createdAt : new Date().toISOString(),
          expiresAt: typeof waiver.expiresAt === "string" && waiver.expiresAt ? waiver.expiresAt : null,
        };
      }
    }
    return validated;
  } catch (err) {
    console.warn("Failed to load waivers from localStorage:", err);
    return {};
  }
}

function saveWaivers(waivers) {
  try {
    localStorage.setItem(WAIVERS_STORAGE_KEY, JSON.stringify(waivers));
  } catch (err) {
    console.warn("Failed to save waivers to localStorage:", err);
  }
}

const state = {
  graph: { nodes: [], links: [], findings: [] },
  cy: null,
  lineageCy: null,
  selectedRule: null,
  selectedNode: null,
  html: null,
  htmlDownloadUrl: "",
  sessions: [], // List of saved sessions
  nodePositions: {}, // Map of node id -> { x, y } for position preservation
  activeLayout: "cose", // Active layout choice
  graph3DInstance: null,
  highlightedIds: null,
  aiStatus: null,
  comparisonResult: null,
  compareActiveCategory: "all",
  waivers: loadWaivers(),
  findingFilters: {
    severity: "",
    code: "",
    snapshot: "",
    waiver: "all",
    search: "",
  },
  selectedFindingId: null,
  editingWaiverFindingId: null,
  pipelineCy: null,
  pipelineFlow: null,
  selectedPipelinePlan: "",
  selectedPipelineOrderStatus: "",
};

window.state = state;

// Monkey-patch Cytoscape prototype fit to handle undefined/null/empty collections safely
if (typeof cytoscape !== "undefined" && cytoscape.prototype) {
  const originalFit = cytoscape.prototype.fit;
  cytoscape.prototype.fit = function(eles, padding) {
    let targetEles = eles;
    let targetPadding = padding;
    if (targetEles === undefined || targetEles === null) {
      targetEles = this.elements();
    } else if (typeof targetEles === "number") {
      targetPadding = targetEles;
      targetEles = this.elements();
    }
    if (!targetEles || targetEles.length === 0) {
      return this;
    }
    return originalFit.call(this, targetEles, targetPadding);
  };
}

function isValidIsoDateString(str) {
  if (typeof str !== "string") return false;
  const trimmed = str.trim();
  if (!trimmed) return false;
  const datePart = trimmed.split("T")[0].split(" ")[0];
  if (!/^\d{4}-\d{2}-\d{2}$/.test(datePart)) return false;
  const [y, m, d] = datePart.split("-").map(Number);
  if (m < 1 || m > 12 || d < 1 || d > 31) return false;
  const date = new Date(datePart + "T00:00:00Z");
  return !isNaN(date.getTime()) && date.toISOString().startsWith(datePart);
}

function computeTemporalStatus(node, asOfDate) {
  const metadata = node && node.metadata ? node.metadata : {};
  const rawStart = (metadata.effectiveStartDate || "").trim();
  const rawEnd = (metadata.effectiveEndDate || "").trim();
  const rawAsOf = (asOfDate || "").trim();

  if (!rawStart && !rawEnd) {
    return {
      status: "undated",
      label: "Undated",
      range: "None",
      explanation: "Object does not define effective dates in configuration source.",
    };
  }

  const validStart = !rawStart || isValidIsoDateString(rawStart);
  const validEnd = !rawEnd || isValidIsoDateString(rawEnd);

  if (!validStart || !validEnd) {
    const badDate = !validStart ? rawStart : rawEnd;
    return {
      status: "unknown",
      label: "Unknown / Invalid",
      range: `${rawStart || "None"} to ${rawEnd || "None"}`,
      explanation: `Unsupported or invalid effective date format: '${badDate}'.`,
    };
  }

  if (rawStart && rawEnd && rawStart > rawEnd) {
    return {
      status: "unknown",
      label: "Unknown / Invalid",
      range: `${rawStart} to ${rawEnd}`,
      explanation: `Invalid date range: start date (${rawStart}) is after end date (${rawEnd}).`,
    };
  }

  const rangeStr = `${rawStart || "Beginning"} to ${rawEnd || "Indefinite"}`;

  if (!rawAsOf) {
    return {
      status: "active",
      label: "Dated",
      range: rangeStr,
      explanation: `Effective from ${rangeStr}.`,
    };
  }

  if (!isValidIsoDateString(rawAsOf)) {
    return {
      status: "unknown",
      label: "Unknown / Invalid",
      range: rangeStr,
      explanation: `Unsupported or invalid as-of date filter: '${rawAsOf}'.`,
    };
  }

  if (rawStart && rawAsOf < rawStart) {
    return {
      status: "future",
      label: "Future",
      range: rangeStr,
      explanation: `Effective starting ${rawStart} (future relative to selected as-of date ${rawAsOf}).`,
    };
  }

  if (rawEnd && rawAsOf > rawEnd) {
    return {
      status: "expired",
      label: "Expired",
      range: rangeStr,
      explanation: `Expired on ${rawEnd} (prior to selected as-of date ${rawAsOf}).`,
    };
  }

  return {
    status: "active",
    label: "Active",
    range: rangeStr,
    explanation: `Active on ${rawAsOf} (effective ${rangeStr}).`,
  };
}

window.computeTemporalStatus = computeTemporalStatus;

function filterGraphElements(graph, filters) {
  const term = (filters.search || "").trim().toLowerCase();
  const effectiveDate = (filters.effectiveDate || "").trim();
  const nodes = graph.nodes.filter((node) => {
    const matchesSearch = !term || node.label.toLowerCase().includes(term);
    const matchesType = !filters.type || node.type === filters.type;
    const matchesSourceFile = !filters.sourceFile || node.sourceFile === filters.sourceFile;
    let matchesEffectiveDate = true;
    if (effectiveDate) {
      const temporal = computeTemporalStatus(node, effectiveDate);
      matchesEffectiveDate = (temporal.status === "active" || temporal.status === "undated");
    }
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
const sessionNameInput = document.getElementById("session-name-input");
const saveSessionButton = document.getElementById("save-session-button");
const sessionMessageBox = document.getElementById("session-message-box");
const sessionExplanation = document.getElementById("session-explanation");
const requiredFilesList = document.getElementById("required-files-list");
const savedSessionsList = document.getElementById("saved-sessions-list");
const themeToggle = document.getElementById("theme-toggle");
const npFileInput = document.getElementById("np-xml-files");
const pFileInput = document.getElementById("p-xml-files");
const graphJsonInput = document.getElementById("graph-json-file");
const topologySelect = document.getElementById("topology-mode");
const workspaceOriginEl = document.getElementById("workspace-origin");
const graphEl = document.getElementById("graph");
const lineageGraphEl = document.getElementById("lineage-graph");
const lineageTab = document.getElementById("lineage-tab");
const lineageSummaryEl = document.getElementById("lineage-summary");
const lineageDescriptionEl = document.getElementById("lineage-description");
const lineageEmptyEl = document.getElementById("lineage-empty");
const pipelineTab = document.getElementById("pipeline-tab");
const pipelinePlanFilter = document.getElementById("pipeline-plan-filter");
const pipelineOrderFilter = document.getElementById("pipeline-order-filter");
const pipelineRelayoutButton = document.getElementById("pipeline-relayout-button");
const pipelineFitButton = document.getElementById("pipeline-fit-button");
const pipelineSummaryText = document.getElementById("pipeline-summary-text");
const pipelineSummaryMetrics = document.getElementById("pipeline-summary-metrics");
const pipelineEmptyEl = document.getElementById("pipeline-empty");
const pipelineGraphEl = document.getElementById("pipeline-graph");
const pipelineEvidencePanel = document.getElementById("pipeline-evidence-panel");
const pipelineEvidenceTitle = document.getElementById("pipeline-evidence-title");
const pipelineEvidenceBody = document.getElementById("pipeline-evidence-body");
const pipelineEvidenceClose = document.getElementById("pipeline-evidence-close");
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
const findingsSeverityFilter = document.getElementById("findings-severity-filter");
const findingsCodeFilter = document.getElementById("findings-code-filter");
const findingsSnapshotFilter = document.getElementById("findings-snapshot-filter");
const findingsWaiverFilter = document.getElementById("findings-waiver-filter");
const findingsSearchInput = document.getElementById("findings-search");
const findingsCounterEl = document.getElementById("findings-counter");
const findingsClearFiltersBtn = document.getElementById("findings-clear-filters");
const riskContainer = document.getElementById("migration-risk-container");
const riskReportEl = document.getElementById("migration-risk-report");
const visualizationModeSelect = document.getElementById("visualization-mode");

const layoutSelect = document.getElementById("layout-select");
const relayoutButton = document.getElementById("relayout-button");
const fitButton = document.getElementById("fit-button");
const resetViewButton = document.getElementById("reset-view-button");
const exportPngButton = document.getElementById("export-png-button");
const exportSvgButton = document.getElementById("export-svg-button");
const sidebarExportPngButton = document.getElementById("sidebar-export-png-button");
const sidebarExportSvgButton = document.getElementById("sidebar-export-svg-button");

const aiSummaryContainer = document.getElementById("ai-summary-container");
const aiSummaryStatus = document.getElementById("ai-summary-status");
const aiSummaryLabel = document.getElementById("ai-summary-label");
const aiSummaryContent = document.getElementById("ai-summary-content");
const generateSummaryButton = document.getElementById("generate-summary-button");

document.getElementById("graph-button").addEventListener("click", requestGraphGeneration);
document.getElementById("html-button").addEventListener("click", generateHtml);
generateSummaryButton.addEventListener("click", handleGenerateSummaryClick);
document.getElementById("export-button").addEventListener("click", () => exportGraph("json"));
document.getElementById("export-csv-button").addEventListener("click", () => exportGraph("csv"));
document.getElementById("export-markdown-button").addEventListener("click", () => exportGraph("markdown"));
document.getElementById("export-graphml-button").addEventListener("click", () => exportGraph("graphml"));
graphJsonInput.addEventListener("change", requestGraphImport);
document.getElementById("export-neo4j-button").addEventListener("click", () => exportGraph("neo4j"));
if (sidebarExportPngButton) sidebarExportPngButton.addEventListener("click", exportGraphAsPng);
if (sidebarExportSvgButton) sidebarExportSvgButton.addEventListener("click", exportGraphAsSvg);
if (layoutSelect) {
  layoutSelect.addEventListener("change", () => {
    state.activeLayout = layoutSelect.value;
    triggerRelayout();
  });
}
if (relayoutButton) relayoutButton.addEventListener("click", triggerRelayout);
if (fitButton) fitButton.addEventListener("click", fitGraph);
if (resetViewButton) resetViewButton.addEventListener("click", resetGraphView);
if (exportPngButton) exportPngButton.addEventListener("click", exportGraphAsPng);
if (exportSvgButton) exportSvgButton.addEventListener("click", exportGraphAsSvg);
themeToggle.addEventListener("click", toggleTheme);
searchInput.addEventListener("input", renderGraphAndHtmlOutput);
typeFilter.addEventListener("change", renderGraphAndHtmlOutput);
sourceFileFilter.addEventListener("change", renderGraph);
relationshipFilter.addEventListener("change", renderGraph);
confidenceFilter.addEventListener("change", renderGraph);
effectiveDateFilter.addEventListener("input", () => {
  renderGraph();
  if (state.selectedNode) showNodeDetails(state.selectedNode);
});
clearFiltersButton.addEventListener("click", clearAllFilters);

if (pipelinePlanFilter) {
  pipelinePlanFilter.addEventListener("change", () => {
    state.selectedPipelinePlan = pipelinePlanFilter.value;
    renderPipelineFlow();
  });
}
if (pipelineOrderFilter) {
  pipelineOrderFilter.addEventListener("change", () => {
    state.selectedPipelineOrderStatus = pipelineOrderFilter.value;
    renderPipelineFlow();
  });
}
if (pipelineRelayoutButton) {
  pipelineRelayoutButton.addEventListener("click", () => {
    if (state.pipelineCy) {
      state.pipelineCy.layout({
        name: "breadthfirst",
        directed: true,
        animate: false,
        fit: true,
        padding: 36,
        spacingFactor: 1.4,
      }).run();
    }
  });
}
if (pipelineFitButton) {
  pipelineFitButton.addEventListener("click", () => {
    state.pipelineCy?.fit(undefined, 36);
  });
}
if (pipelineEvidenceClose) {
  pipelineEvidenceClose.addEventListener("click", () => {
    if (pipelineEvidencePanel) pipelineEvidencePanel.hidden = true;
  });
}

if (findingsSeverityFilter) {
  findingsSeverityFilter.addEventListener("change", (e) => {
    state.findingFilters.severity = e.target.value;
    renderFindings();
  });
}
if (findingsCodeFilter) {
  findingsCodeFilter.addEventListener("change", (e) => {
    state.findingFilters.code = e.target.value;
    renderFindings();
  });
}
if (findingsSnapshotFilter) {
  findingsSnapshotFilter.addEventListener("change", (e) => {
    state.findingFilters.snapshot = e.target.value;
    renderFindings();
  });
}
if (findingsWaiverFilter) {
  findingsWaiverFilter.addEventListener("change", (e) => {
    state.findingFilters.waiver = e.target.value;
    renderFindings();
  });
}
if (findingsSearchInput) {
  findingsSearchInput.addEventListener("input", (e) => {
    state.findingFilters.search = e.target.value;
    renderFindings();
  });
}
if (findingsClearFiltersBtn) {
  findingsClearFiltersBtn.addEventListener("click", () => {
    state.findingFilters = { severity: "", code: "", snapshot: "", waiver: "all", search: "" };
    if (findingsSeverityFilter) findingsSeverityFilter.value = "";
    if (findingsCodeFilter) findingsCodeFilter.value = "";
    if (findingsSnapshotFilter) findingsSnapshotFilter.value = "";
    if (findingsWaiverFilter) findingsWaiverFilter.value = "all";
    if (findingsSearchInput) findingsSearchInput.value = "";
    renderFindings();
  });
}

function navigateToHtmlSectionForNode(node) {
  if (!state.html) {
    setStatus("HTML representation unavailable: No HTML generated yet.");
    return;
  }
  const htmlInputFiles = state.html.inputFiles || (state.html.inputName ? [state.html.inputName] : []);
  if (node.sourceFile && htmlInputFiles.length > 0 && !htmlInputFiles.includes(node.sourceFile)) {
    setStatus(`HTML representation unavailable: Node is in file '${node.sourceFile}', but HTML was generated for '${htmlInputFiles.join(", ")}'.`);
    return;
  }

  const anchors = getHtmlAnchorsForNode(node);
  const directCandidates = [];
  if (node.id) directCandidates.push(node.id);
  if (node.sourceId) directCandidates.push(node.sourceId, safeAnchorPart(node.sourceId));
  if (node.xmlPath) directCandidates.push(node.xmlPath, safeAnchorPart(node.xmlPath));
  const allCandidates = [...directCandidates, ...anchors];

  if (allCandidates.length === 0) {
    setStatus(`HTML representation unavailable for ${node.type}: ${node.label}`);
    return;
  }

  switchWorkspace("html-output-view");
  const preview = document.getElementById("html-output-preview");
  const doc = preview.contentDocument || preview.contentWindow.document;
  if (doc) {
    let element = null;
    for (const cand of allCandidates) {
      element = doc.getElementById(cand) || doc.getElementsByName(cand)[0];
      if (element) break;
      const decoded = decodeURIComponent(cand);
      element = doc.getElementById(decoded) || doc.getElementsByName(decoded)[0];
      if (element) break;
    }
    if (element) {
      element.scrollIntoView({ block: "start", behavior: "smooth" });
      setStatus(`Navigated to HTML section for ${node.label}`);
    } else {
      const fallbackAnchor = anchors[0] || node.id;
      setStatus(`HTML representation unavailable: Anchor '${fallbackAnchor}' not found in preview.`);
    }
  }
}

function selectFinding(finding) {
  state.selectedFindingId = finding.id;
  const findingElements = findingsEl.querySelectorAll(".finding");
  findingElements.forEach((el) => {
    if (el.dataset.findingId === finding.id) {
      el.classList.add("selected");
    } else {
      el.classList.remove("selected");
    }
  });

  if (!finding.nodeIds || finding.nodeIds.length === 0) return;

  const matchingNodes = [];
  finding.nodeIds.forEach((id) => {
    let node = state.graph.nodes.find((n) => n.id === id);
    if (!node && state.graph.nodes.length > 0) {
      const parts = id.split("-");
      const digest = parts.length > 1 ? parts[1] : "";
      if (digest) {
        node = state.graph.nodes.find((n) => n.id.endsWith(digest));
      }
    }
    if (node) matchingNodes.push(node);
  });

  if (state.cy) {
    state.cy.elements().unselect();
    const nodeSelectors = finding.nodeIds.map((id) => `#${CSS.escape(id)}`).join(",");
    let cyNodes = state.cy.nodes(nodeSelectors);
    if (cyNodes.length === 0 && matchingNodes.length > 0) {
      const resolvedSelectors = matchingNodes.map((n) => `#${CSS.escape(n.id)}`).join(",");
      cyNodes = state.cy.nodes(resolvedSelectors);
    }
    if (cyNodes.length > 0) {
      cyNodes.select();
      state.highlightedIds = new Set(cyNodes.map((n) => n.id()));
      state.cy.animate({
        center: { eles: cyNodes },
        zoom: Math.max(state.cy.zoom(), 1.0),
        duration: 400,
      });
    }
  }

  if (matchingNodes.length > 0) {
    showNodeDetails(matchingNodes[0]);
  }
}

findingsEl.addEventListener("click", (event) => {
  const findingItem = event.target.closest(".finding");
  if (findingItem) {
    const findingId = findingItem.dataset.findingId;
    const finding = (state.graph.findings || []).find((f) => f.id === findingId);
    if (finding && state.selectedFindingId !== findingId) {
      selectFinding(finding);
    }
  }

  const nodeBtn = event.target.closest(".finding-action-btn");
  if (nodeBtn) {
    const nodeId = nodeBtn.dataset.nodeId;
    let node = state.graph.nodes.find((n) => n.id === nodeId);
    if (!node && state.graph.nodes.length > 0) {
      const parts = nodeId.split("-");
      const digest = parts.length > 1 ? parts[1] : "";
      if (digest) {
        node = state.graph.nodes.find((n) => n.id.endsWith(digest));
      }
    }
    if (!node) return;

    if (nodeBtn.classList.contains("go-to-node")) {
      selectAndFocusNode(node);
      switchWorkspace("graph-view");
    } else if (nodeBtn.classList.contains("view-xml")) {
      selectAndFocusNode(node);
    } else if (nodeBtn.classList.contains("view-html")) {
      selectAndFocusNode(node);
      navigateToHtmlSectionForNode(node);
    }
    return;
  }

  const waiveBtn = event.target.closest(".waive-finding-btn");
  if (waiveBtn) {
    state.editingWaiverFindingId = waiveBtn.dataset.findingId;
    renderFindings();
    return;
  }

  const editWaiverBtn = event.target.closest(".edit-waiver-btn");
  if (editWaiverBtn) {
    state.editingWaiverFindingId = editWaiverBtn.dataset.findingId;
    renderFindings();
    return;
  }

  const cancelBtn = event.target.closest(".cancel-waiver-btn");
  if (cancelBtn) {
    state.editingWaiverFindingId = null;
    renderFindings();
    return;
  }

  const saveBtn = event.target.closest(".save-waiver-btn");
  if (saveBtn) {
    const findingId = saveBtn.dataset.findingId;
    const form = saveBtn.closest(".waiver-form");
    if (!form) return;
    const reviewerInput = form.querySelector(".waiver-input-reviewer");
    const reasonInput = form.querySelector(".waiver-input-reason");
    const expiryInput = form.querySelector(".waiver-input-expiry");
    const errEl = form.querySelector(".waiver-form-error");

    const reviewer = reviewerInput ? reviewerInput.value.trim() : "";
    const reason = reasonInput ? reasonInput.value.trim() : "";
    const expiry = expiryInput ? expiryInput.value.trim() : "";

    if (!reviewer || !reason) {
      if (errEl) {
        errEl.textContent = "Reviewer and reason are required.";
        errEl.style.display = "block";
      }
      return;
    }

    const existing = state.waivers[findingId];
    state.waivers[findingId] = {
      findingId,
      reviewer,
      reason,
      createdAt: existing?.createdAt || new Date().toISOString(),
      expiresAt: expiry || null,
    };
    saveWaivers(state.waivers);
    state.editingWaiverFindingId = null;
    renderFindings();
    setStatus(`Saved waiver for finding ${findingId}.`);
    return;
  }

  const revokeBtn = event.target.closest(".revoke-waiver-btn");
  if (revokeBtn) {
    const findingId = revokeBtn.dataset.findingId;
    delete state.waivers[findingId];
    saveWaivers(state.waivers);
    if (state.editingWaiverFindingId === findingId) {
      state.editingWaiverFindingId = null;
    }
    renderFindings();
    setStatus(`Revoked waiver for finding ${findingId}.`);
    return;
  }
});

findingsEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    if (event.target.tagName === "BUTTON" || event.target.tagName === "INPUT" || event.target.tagName === "SELECT") return;
    const findingItem = event.target.closest(".finding");
    if (findingItem) {
      event.preventDefault();
      const findingId = findingItem.dataset.findingId;
      const finding = (state.graph.findings || []).find((f) => f.id === findingId);
      if (finding) {
        selectFinding(finding);
        announceA11y(`Selected finding ${finding.code}, severity ${finding.severity}`);
      }
    }
  }
});

document.getElementById("lineage-back-button").addEventListener("click", () => switchWorkspace("graph-view"));
topologySelect.addEventListener("change", () => {
  if (npFileInput.files.length || pFileInput.files.length) {
    requestGraphGeneration();
  } else {
    setStatus(`Selected ${topologyLabel(topologySelect.value)} topology.`);
  }
});
saveSessionButton.addEventListener("click", handleSaveSession);

visualizationModeSelect.addEventListener("change", () => {
  if (state.graph.nodes.length > 0) {
    renderGraph();
  } else {
    setStatus(`Selected ${visualizationModeSelect.value.toUpperCase()} visualization mode.`);
  }
});

initializeTheme();
loadSessionsFromStorage();
fetchAiStatus();

function announceA11y(message) {
  const el = document.getElementById("a11y-announcements");
  if (!el || !message) return;
  el.textContent = "";
  setTimeout(() => {
    el.textContent = message;
  }, 40);
}

function initializeTabs() {
  const tabsContainer = document.querySelector(".tabs");
  if (!tabsContainer) return;

  tabsContainer.querySelectorAll(".tab").forEach((tab) => {
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

  tabsContainer.addEventListener("keydown", (e) => {
    const tabs = Array.from(tabsContainer.querySelectorAll(".tab:not([disabled])"));
    if (!tabs.length) return;
    const currentIndex = tabs.findIndex((t) => t.classList.contains("active"));

    let targetTab = null;
    if (e.key === "ArrowRight") {
      e.preventDefault();
      targetTab = tabs[(currentIndex + 1) % tabs.length];
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      targetTab = tabs[(currentIndex - 1 + tabs.length) % tabs.length];
    } else if (e.key === "Home") {
      e.preventDefault();
      targetTab = tabs[0];
    } else if (e.key === "End") {
      e.preventDefault();
      targetTab = tabs[tabs.length - 1];
    }

    if (targetTab) {
      targetTab.focus();
      targetTab.click();
    }
  });
}
initializeTabs();

function switchWorkspace(viewId) {
  const tabs = document.querySelectorAll(".tab");
  tabs.forEach((el) => {
    const isActive = el.dataset.view === viewId;
    el.classList.toggle("active", isActive);
    el.setAttribute("aria-selected", isActive ? "true" : "false");
    el.setAttribute("tabindex", isActive ? "0" : "-1");
  });

  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  const targetView = document.getElementById(viewId);
  if (targetView) {
    targetView.classList.add("active");
  }

  const activeTab = document.querySelector(`.tab[data-view="${viewId}"]`);
  if (activeTab) {
    announceA11y(`Switched to ${activeTab.textContent.trim()} view`);
  }

  if (viewId === "lineage-view") {
    state.lineageCy?.resize().fit();
  } else if (viewId === "graph-view") {
    state.cy?.resize();
    if (state.graph3DInstance && visualizationModeSelect?.value === "3d") {
      const container = document.getElementById("graph-3d");
      const rect = container.getBoundingClientRect();
      state.graph3DInstance.width(rect.width || 800).height(rect.height || 600);
    }
  } else if (viewId === "ai-docs-view") {
    if (typeof updateAiDocsPanel === "function") {
      updateAiDocsPanel();
    }
  } else if (viewId === "pipeline-view") {
    if (!state.pipelineFlow) {
      renderPipelineFlow();
    } else {
      state.pipelineCy?.resize().fit(undefined, 36);
    }
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

  loadGraphWorkspace(payload);
  setStatus(graphStatus(payload));
}

function requestGraphImport() {
  importGraphJson().catch((error) => {
    const detail = error instanceof Error && error.message
      ? error.message
      : "Unexpected local Graph JSON import error.";
    setStatus(`Graph JSON import failed: ${detail}`);
  });
}

async function importGraphJson() {
  const file = graphJsonInput.files[0];
  if (!file) return;
  const requestId = ++latestGraphRequestId;
  const formData = new FormData();
  formData.append("file", file);
  setStatus(`Importing ${file.name}...`);
  try {
    const response = await fetch("/api/import/graph-json", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (requestId !== latestGraphRequestId) return;
    if (!response.ok) {
      return setStatus(`Graph JSON import failed: ${payload.error || "Invalid Graph JSON file."}`);
    }
    loadGraphWorkspace(payload);
    switchWorkspace("graph-view");
    setStatus(`Imported ${payload.provenance.fileName}. ${graphStatus(payload)}`);
  } finally {
    graphJsonInput.value = "";
  }
}

function loadGraphWorkspace(payload) {
  state.graph = payload;
  state.waivers = loadWaivers();
  if (payload.waivers && Array.isArray(payload.waivers)) {
    payload.waivers.forEach((w) => {
      if (w && w.findingId && w.reason && w.reviewer) {
        state.waivers[w.findingId] = {
          findingId: w.findingId,
          reason: w.reason,
          reviewer: w.reviewer,
          createdAt: w.createdAt || new Date().toISOString(),
          expiresAt: w.expiresAt || null,
        };
      }
    });
    saveWaivers(state.waivers);
  }
  state.nodePositions = {};
  if (layoutSelect) layoutSelect.value = state.activeLayout || "cose";
  topologySelect.value = payload.topologyMode;
  clearSelectedRule();
  destroyLineageRenderer();
  if (pipelineTab) pipelineTab.disabled = false;
  populatePipelinePlanFilter(payload);
  state.pipelineFlow = null;
  destroyPipelineRenderer();
  resetDetails();
  populateFilterControls(payload);
  if (effectiveDateFilter && payload.asOfDate) {
    effectiveDateFilter.value = payload.asOfDate;
  }
  renderFindings(payload.findings || []);
  renderRiskReport(payload.migrationRisk);
  renderWorkspaceOrigin(payload.provenance);
  renderGraph();
  if (typeof updateAiDocsPanel === "function") {
    updateAiDocsPanel();
  }
  setStatus(graphStatus(payload));
}

function renderWorkspaceOrigin(provenance) {
  const imported = provenance?.origin === "imported";
  workspaceOriginEl.dataset.origin = imported ? "imported" : "xml";
  workspaceOriginEl.textContent = imported
    ? `Imported JSON: ${provenance.fileName}`
    : "Generated from selected XML";
}

function resetDetails() {
  summaryEl.innerHTML = "<dt>Selection</dt><dd>Select a graph item</dd>";
  rawXmlEl.textContent = "";
  hideAiSummary();
}

async function generateHtml() {
  const file = npFileInput.files[0] || pFileInput.files[0];
  const files = [...npFileInput.files, ...pFileInput.files];
  if (!file) return setStatus("Select an XML file.");
  const variant = document.getElementById("variant").value;
  setStatus("Generating HTML...");
  try {
    state.html = await convertHtml(files.length > 1 ? files : file, variant);
  } catch (error) {
    return setStatus(error.message || "HTML generation failed.");
  }
  renderFindings(state.html.findings || []);
  renderHtmlOutput();
  document.querySelector('[data-view="html-output-view"]').click();
  setStatus(`Generated ${state.html.outputFile}.`);
}

async function convertHtml(fileOrFiles, variant) {
  const files = Array.isArray(fileOrFiles) ? fileOrFiles : [fileOrFiles];
  const formData = new FormData();
  if (files.length === 1) {
    formData.append("file", files[0]);
  } else {
    for (const f of files) {
      formData.append("files", f);
    }
  }
  formData.append("variant", variant);
  formData.append("theme", currentTheme());
  const snapshotId = (npFileInput.files.length > 0 && pFileInput.files.length === 0) ? "non_production" : (pFileInput.files.length > 0 && npFileInput.files.length === 0 ? "production" : "configuration");
  formData.append("snapshot_id", snapshotId);
  const response = await fetch("/api/convert/html", { method: "POST", body: formData });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || `Unable to generate HTML for ${files.map((f) => f.name).join(", ")}.`);
  }
  return {
    originalHtml: payload.html,
    inputName: files[0].name,
    inputFiles: payload.inputFiles || files.map((f) => f.name),
    outputFile: payload.outputFile,
    variant,
    findings: payload.findings || [],
  };
}

window.sapImExplorer_navigateToGraphNode = (type, label, instanceId = null) => {
  if (!state.graph || !state.graph.nodes) {
    setStatus("Graph representation unavailable: No graph generated yet.");
    return;
  }

  let node = null;
  if (instanceId) {
    node = state.graph.nodes.find((n) => n.id === instanceId);
  }
  if (!node) {
    const sourceFiles = state.html ? (state.html.inputFiles || [state.html.inputName]) : [];
    node = state.graph.nodes.find(
      (n) => n.type === type && n.label === label && (sourceFiles.length === 0 || sourceFiles.includes(n.sourceFile))
    );
  }
  if (!node) {
    node = state.graph.nodes.find((n) => n.type === type && n.label === label);
  }

  if (!node) {
    setStatus(`Graph representation unavailable for ${type}: ${label}`);
    return;
  }

  selectAndFocusNode(node);
  switchWorkspace("graph-view");
  setStatus(`Navigated to graph node for ${label}`);
};

function enhanceHtmlPreviewForGraphNavigation(preview) {
  const doc = preview.contentDocument || preview.contentWindow.document;
  if (!doc) return;

  const style = doc.createElement("style");
  style.textContent = `
    .view-in-graph-link {
      color: var(--forest-green, #2e7d32);
      font-size: 12px;
      font-weight: 600;
      margin-left: 12px;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
      vertical-align: middle;
    }
    .view-in-graph-link:hover {
      color: var(--light-green, #81c784);
      text-decoration: underline;
    }
    .view-in-graph-entry-link {
      color: var(--forest-green, #2e7d32);
      font-size: 11px;
      font-weight: 600;
      margin-left: 6px;
      cursor: pointer;
      text-decoration: none;
    }
    .view-in-graph-entry-link:hover {
      color: var(--light-green, #81c784);
      text-decoration: underline;
    }
  `;
  doc.head.appendChild(style);

  doc.querySelectorAll("section[data-object-type][data-object-label]").forEach((section) => {
    const type = section.getAttribute("data-object-type");
    const label = section.getAttribute("data-object-label");
    const heading = section.querySelector("h1, h2, h3");
    if (heading && !heading.querySelector(".view-in-graph-link")) {
      const link = doc.createElement("a");
      link.className = "view-in-graph-link";
      link.textContent = "[View in Graph]";
      link.href = "#";
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const instanceAnchor = section.querySelector("a[name^='node-']");
        const instanceId = instanceAnchor ? instanceAnchor.getAttribute("name") : null;
        const targetWindow = window.parent.sapImExplorer_navigateToGraphNode ? window.parent : window;
        targetWindow.sapImExplorer_navigateToGraphNode(type, label, instanceId);
      });
      heading.appendChild(link);
    }
  });

  doc.querySelectorAll("span[data-object-entry='true'][data-object-type][data-object-label]").forEach((entry) => {
    if (entry.querySelector(".view-in-graph-entry-link")) return;
    const type = entry.getAttribute("data-object-type");
    const label = entry.getAttribute("data-object-label");
    const link = doc.createElement("a");
    link.className = "view-in-graph-entry-link";
    link.textContent = "[Graph]";
    link.href = "#";
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const targetWindow = window.parent.sapImExplorer_navigateToGraphNode ? window.parent : window;
      targetWindow.sapImExplorer_navigateToGraphNode(type, label);
    });
    entry.appendChild(link);
  });
}

function renderHtmlOutput() {
  const output = state.html;
  const preview = document.getElementById("html-output-preview");
  const download = document.getElementById("html-output-download");
  const meta = document.getElementById("html-output-meta");
  preview.onload = () => {
    enableHtmlPreviewAnchors(preview);
    enhanceHtmlPreviewForGraphNavigation(preview);
  };

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
    const rawAnchor = href.slice(1);
    const candidates = [rawAnchor, decodeURIComponent(rawAnchor)];
    const target = [...previewDocument.querySelectorAll("[name], [id]")].find(
      (element) => candidates.includes(element.getAttribute("name")) || candidates.includes(element.id)
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
  if (state.pipelineCy) {
    state.pipelineCy.style(pipelineCytoscapeStyles(graphThemeColors()));
  }
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

function getLayoutConfig(name) {
  switch (name) {
    case "breadthfirst":
      return {
        name: "breadthfirst",
        directed: true,
        padding: 32,
        spacingFactor: 1.25,
        animate: false,
      };
    case "circle":
      return { name: "circle", padding: 32, animate: false };
    case "concentric":
      return {
        name: "concentric",
        padding: 32,
        minNodeSpacing: 40,
        animate: false,
      };
    case "grid":
      return { name: "grid", padding: 32, animate: false };
    case "cose":
    default:
      return {
        name: "cose",
        animate: false,
        componentSpacing: 48,
        fit: true,
        idealEdgeLength: 88,
        nodeOverlap: 16,
        padding: 24,
        randomize: false,
      };
  }
}

function triggerRelayout() {
  if (!state.cy || state.cy.nodes().length === 0) return;
  state.nodePositions = {};
  const layout = state.cy.layout(getLayoutConfig(state.activeLayout));
  layout.on("layoutstop", () => {
    if (!state.cy) return;
    state.cy.nodes().forEach((n) => {
      state.nodePositions[n.id()] = { ...n.position() };
    });
  });
  layout.run();
  if (typeof state.cy.fit === "function") {
    state.cy.fit(state.cy.elements(), 48);
  }
  const layoutLabel = layoutSelect ? layoutSelect.options[layoutSelect.selectedIndex].text : state.activeLayout;
  setStatus(`Applied ${layoutLabel} layout.`);
}

function fitGraph() {
  if (state.cy && state.cy.elements().length > 0) {
    state.cy.fit(state.cy.elements(), 48);
    setStatus("Fitted graph to viewport.");
  }
}

function resetGraphView() {
  if (!state.cy || state.cy.elements().length === 0) return;
  state.nodePositions = {};
  state.activeLayout = "cose";
  if (layoutSelect) layoutSelect.value = "cose";
  const layout = state.cy.layout(getLayoutConfig("cose"));
  layout.on("layoutstop", () => {
    if (!state.cy) return;
    state.cy.nodes().forEach((n) => {
      state.nodePositions[n.id()] = { ...n.position() };
    });
    if (typeof state.cy.fit === "function") {
      state.cy.fit(state.cy.elements(), 48);
    }
  });
  layout.run();
  setStatus("Reset graph layout and view.");
}

function isWebGLSupported() {
  try {
    const canvas = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")));
  } catch (e) {
    return false;
  }
}

async function load3DLibrary() {
  if (typeof ForceGraph3D !== "undefined") {
    return;
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "/static/vendor/3d-force-graph.min.js";
    script.onload = resolve;
    script.onerror = () => {
      reject(new Error("Failed to load 3D rendering dependency."));
    };
    document.body.appendChild(script);
  });
}

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function getHighlightedElements(nodeId) {
  if (!state.cy) return new Set();
  const cyNode = state.cy.getElementById(nodeId);
  if (!cyNode || cyNode.length === 0) return new Set();
  const neighborhood = cyNode.successors().union(cyNode.predecessors()).union(cyNode);
  return new Set(neighborhood.map((el) => el.id()));
}

async function render3DGraph(nodes, links) {
  document.getElementById("graph").hidden = true;
  document.getElementById("graph-3d").hidden = false;

  if (!isWebGLSupported()) {
    setStatus("3D rendering is unsupported on this browser/device.");
    visualizationModeSelect.value = "2d";
    document.getElementById("graph").hidden = false;
    document.getElementById("graph-3d").hidden = true;
    return;
  }

  try {
    await load3DLibrary();
  } catch (error) {
    setStatus(error.message);
    visualizationModeSelect.value = "2d";
    document.getElementById("graph").hidden = false;
    document.getElementById("graph-3d").hidden = true;
    return;
  }

  const nodesClone = nodes.map((n) => ({ ...n }));
  const linksClone = links.map((l) => ({ ...l }));

  const container = document.getElementById("graph-3d");
  const rect = container.getBoundingClientRect();

  if (!state.graph3DInstance) {
    state.highlightedIds = null;
    state.graph3DInstance = ForceGraph3D()(container)
      .nodeColor((node) => {
        const baseColor = colorForType(node.type);
        if (state.highlightedIds) {
          return state.highlightedIds.has(node.id) ? hexToRgba(baseColor, 1.0) : hexToRgba(baseColor, 0.1);
        }
        return hexToRgba(baseColor, 1.0);
      })
      .nodeLabel((node) => node.label)
      .linkLabel((link) => link.relationship)
      .linkColor((link) => {
        const baseColor = "#708174";
        if (state.highlightedIds) {
          const sourceId = typeof link.source === "object" ? link.source.id : link.source;
          const targetId = typeof link.target === "object" ? link.target.id : link.target;
          return state.highlightedIds.has(sourceId) && state.highlightedIds.has(targetId)
            ? hexToRgba(baseColor, 1.0)
            : hexToRgba(baseColor, 0.1);
        }
        return hexToRgba(baseColor, 1.0);
      })
      .onNodeClick((node) => {
        state.highlightedIds = getHighlightedElements(node.id);
        state.graph3DInstance.nodeColor(state.graph3DInstance.nodeColor());
        state.graph3DInstance.linkColor(state.graph3DInstance.linkColor());
        showNodeDetails(node);
      })
      .onBackgroundClick(() => {
        state.highlightedIds = null;
        state.graph3DInstance.nodeColor(state.graph3DInstance.nodeColor());
        state.graph3DInstance.linkColor(state.graph3DInstance.linkColor());
        clearSelectedRule();
        summaryEl.innerHTML = "<dt>Selection</dt><dd>Select a graph item</dd>";
        rawXmlEl.textContent = "";
      })
      .onLinkClick((link) => {
        showEdgeDetails(link);
      });
  }

  state.graph3DInstance.backgroundColor(currentTheme() === "dark" ? "#333333" : "#ffffff");
  state.graph3DInstance.width(rect.width || 800).height(rect.height || 600);
  state.graph3DInstance.graphData({ nodes: nodesClone, links: linksClone });
}

function renderAccessibleGraphTree(nodes, links) {
  const countEl = document.getElementById("accessible-tree-count");
  const listEl = document.getElementById("accessible-node-list");
  if (!listEl) return;

  const nodeCount = nodes ? nodes.length : 0;
  if (countEl) {
    countEl.textContent = `${nodeCount} node${nodeCount === 1 ? "" : "s"}`;
  }

  if (!nodes || nodes.length === 0) {
    listEl.innerHTML = '<li class="accessible-empty-state" role="option">No nodes match current filters.</li>';
    return;
  }

  const linkCountByNodeId = {};
  (links || []).forEach((l) => {
    const s = typeof l.source === "object" ? l.source.id : l.source;
    const t = typeof l.target === "object" ? l.target.id : l.target;
    linkCountByNodeId[s] = (linkCountByNodeId[s] || 0) + 1;
    linkCountByNodeId[t] = (linkCountByNodeId[t] || 0) + 1;
  });

  const findingsByNodeId = {};
  (state.graph.findings || []).forEach((f) => {
    (f.nodeIds || []).forEach((nid) => {
      findingsByNodeId[nid] = findingsByNodeId[nid] || [];
      findingsByNodeId[nid].push(f);
    });
  });

  const sortedNodes = [...nodes].sort((a, b) => {
    const typeCompare = (a.type || "").localeCompare(b.type || "");
    if (typeCompare !== 0) return typeCompare;
    return (a.label || a.name || a.id || "").localeCompare(b.label || b.name || b.id || "");
  });

  const shapePrefixes = {
    Plan: "[PLAN]",
    PlanComponent: "[COMP]",
    Rule: "[RULE]",
    Formula: "[FORM]",
    MDLookupTable: "[TABL]",
    Territory: "[TERR]",
    Position: "[POSN]",
    Title: "[TITL]",
    FixedValue: "[VALU]",
  };

  listEl.innerHTML = sortedNodes
    .map((node, index) => {
      const isSelected = state.selectedNode && state.selectedNode.id === node.id;
      const shape = shapePrefixes[node.type] || `[${(node.type || "NODE").slice(0, 4).toUpperCase()}]`;
      const nodeLinks = linkCountByNodeId[node.id] || 0;
      const nodeFindings = findingsByNodeId[node.id] || [];
      const errorCount = nodeFindings.filter((f) => f.severity === "error").length;
      const warnCount = nodeFindings.filter((f) => f.severity === "warning").length;

      let findingBadge = "";
      if (errorCount > 0) {
        findingBadge = `<span class="accessible-node-badge" style="color: var(--alert-red);" title="${errorCount} error(s)">▲ [! ${errorCount}]</span>`;
      } else if (warnCount > 0) {
        findingBadge = `<span class="accessible-node-badge" style="color: var(--warning-amber);" title="${warnCount} warning(s)">◆ [? ${warnCount}]</span>`;
      }

      const effectiveText = node.effectiveStartDate
        ? ` (${node.effectiveStartDate.slice(0, 10)}${node.effectiveEndDate ? " to " + node.effectiveEndDate.slice(0, 10) : ""})`
        : "";

      return `
        <li class="accessible-node-item"
            role="option"
            id="a11y-node-${escapeHtml(node.id)}"
            data-node-id="${escapeHtml(node.id)}"
            aria-selected="${isSelected ? "true" : "false"}"
            tabindex="${index === 0 ? "0" : "-1"}">
          <div class="accessible-node-info">
            <span class="accessible-node-shape" aria-hidden="true">${shape}</span>
            <span class="accessible-node-label"><strong>${escapeHtml(node.label || node.name || node.id)}</strong>${escapeHtml(effectiveText)}</span>
          </div>
          <div class="accessible-node-meta">
            ${findingBadge}
            <span class="accessible-node-badge" title="Connection count">[Links: ${nodeLinks}]</span>
          </div>
        </li>
      `;
    })
    .join("");
}

function initializeAccessibleTree() {
  const toggleBtn = document.getElementById("toggle-accessible-tree");
  const treeContainer = document.getElementById("accessible-graph-tree");
  const listEl = document.getElementById("accessible-node-list");

  if (toggleBtn && treeContainer) {
    toggleBtn.addEventListener("click", () => {
      const willShow = treeContainer.hidden;
      treeContainer.hidden = !willShow;
      toggleBtn.setAttribute("aria-expanded", String(willShow));
      if (willShow) {
        const first = listEl?.querySelector(".accessible-node-item[tabindex='0']") || listEl?.querySelector(".accessible-node-item");
        if (first) first.focus();
        announceA11y("Accessible Graph Tree opened");
      } else {
        announceA11y("Accessible Graph Tree closed");
      }
    });
  }

  if (listEl) {
    listEl.addEventListener("click", (e) => {
      const item = e.target.closest(".accessible-node-item");
      if (!item) return;
      const nodeId = item.dataset.nodeId;
      const node = state.graph.nodes.find((n) => n.id === nodeId);
      if (node) selectAndFocusNode(node);
    });

    listEl.addEventListener("keydown", (e) => {
      const items = Array.from(listEl.querySelectorAll(".accessible-node-item"));
      if (!items.length) return;
      const currentIndex = items.findIndex((item) => item === document.activeElement || item.getAttribute("aria-selected") === "true");

      let nextIndex = -1;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        nextIndex = currentIndex >= 0 && currentIndex < items.length - 1 ? currentIndex + 1 : 0;
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        nextIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1;
      } else if (e.key === "Home") {
        e.preventDefault();
        nextIndex = 0;
      } else if (e.key === "End") {
        e.preventDefault();
        nextIndex = items.length - 1;
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        const currentItem = (document.activeElement && document.activeElement.closest(".accessible-node-item")) || items[Math.max(0, currentIndex)];
        if (currentItem) {
          const nodeId = currentItem.dataset.nodeId;
          const node = state.graph.nodes.find((n) => n.id === nodeId);
          if (node) selectAndFocusNode(node);
        }
        return;
      }

      if (nextIndex >= 0) {
        items.forEach((item) => (item.tabIndex = -1));
        items[nextIndex].tabIndex = 0;
        items[nextIndex].focus();
      }
    });
  }
}
initializeAccessibleTree();

function renderGraph() {
  if (state.cy) {
    state.cy.nodes().forEach((n) => {
      state.nodePositions[n.id()] = { ...n.position() };
    });
    state.cy.destroy();
  }
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
  renderAccessibleGraphTree(nodes, links);
  const elements = [
    ...nodes.map((node, index) => {
      const saved = state.nodePositions[node.id];
      return {
        data: { ...node, displayColor: colorForType(node.type) },
        position: saved ? { ...saved } : initialGraphPosition(index, nodes.length),
      };
    }),
    ...links.map((link, index) => ({
      data: { ...link, id: link.id || `edge-${index}` },
    })),
  ];

  const hasSavedPositions = nodes.length > 0 && nodes.some((node) => Boolean(state.nodePositions[node.id]));
  const layoutConfig = hasSavedPositions
    ? { name: "preset", fit: false }
    : getLayoutConfig(state.activeLayout);

  state.cy = cytoscape({
    container: graphEl,
    elements,
    style: cytoscapeStyles(graphTheme),
    layout: layoutConfig,
  });

  state.cy.on("dragfree", "node", (event) => {
    const node = event.target;
    state.nodePositions[node.id()] = { ...node.position() };
  });

  state.cy.on("layoutstop", () => {
    if (!state.cy) return;
    state.cy.nodes().forEach((n) => {
      state.nodePositions[n.id()] = { ...n.position() };
    });
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
      hideAiSummary();
    }
  });
  state.cy.on("tap", "edge", (event) => showEdgeDetails(event.target.data()));

  const visualizationMode = visualizationModeSelect?.value || "2d";
  if (visualizationMode === "3d") {
    render3DGraph(nodes, links);
  } else {
    document.getElementById("graph-3d").hidden = true;
    document.getElementById("graph").hidden = false;
  }
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
  announceA11y(filterResultsEl.textContent);
}

function clearAllFilters() {
  searchInput.value = "";
  typeFilter.value = "";
  sourceFileFilter.value = "";
  relationshipFilter.value = "";
  confidenceFilter.value = "";
  effectiveDateFilter.value = "";
  renderGraphAndHtmlOutput();
  announceA11y("All filters cleared. Showing all nodes.");
  if (state.selectedNode) showNodeDetails(state.selectedNode);
}

function getFilteredFindings(findings) {
  if (!findings) return [];
  const filters = state.findingFilters;
  const term = (filters.search || "").trim().toLowerCase();

  return findings.filter((finding) => {
    if (filters.severity && finding.severity !== filters.severity) {
      return false;
    }
    if (filters.code && finding.code !== filters.code) {
      return false;
    }
    if (filters.snapshot && finding.snapshotId !== filters.snapshot) {
      return false;
    }

    const waiver = state.waivers[finding.id];
    const isWaived = Boolean(waiver);
    const isExpired = isWaiverExpired(waiver);
    const hasActiveWaiver = isWaived && !isExpired;

    if (filters.waiver === "waived") {
      if (!isWaived) return false;
    } else if (filters.waiver === "unwaived") {
      if (hasActiveWaiver) return false;
    }

    if (term) {
      const codeMatch = (finding.code || "").toLowerCase().includes(term);
      const msgMatch = (finding.message || "").toLowerCase().includes(term);
      const snapMatch = (finding.snapshotId || "").toLowerCase().includes(term);
      let nodeMatch = false;
      if (finding.nodeIds && finding.nodeIds.length > 0) {
        nodeMatch = finding.nodeIds.some((id) => {
          if (id.toLowerCase().includes(term)) return true;
          let node = state.graph.nodes?.find((n) => n.id === id);
          if (!node && state.graph.nodes && state.graph.nodes.length > 0) {
            const parts = id.split("-");
            const digest = parts.length > 1 ? parts[1] : "";
            if (digest) {
              node = state.graph.nodes.find((n) => n.id.endsWith(digest));
            }
          }
          if (node) {
            if (node.label && node.label.toLowerCase().includes(term)) return true;
            if (node.type && node.type.toLowerCase().includes(term)) return true;
            if (node.sourceFile && node.sourceFile.toLowerCase().includes(term)) return true;
          }
          return false;
        });
      }
      if (!codeMatch && !msgMatch && !snapMatch && !nodeMatch) {
        return false;
      }
    }

    return true;
  });
}

function renderFindings(findings) {
  if (findings === undefined) {
    findings = state.graph.findings || [];
  } else {
    state.graph.findings = findings;
  }
  state.graph.waivers = Object.values(state.waivers);

  if (findingsCodeFilter) {
    const currentCode = state.findingFilters.code;
    const codes = Array.from(new Set(findings.map((f) => f.code).filter(Boolean))).sort();
    findingsCodeFilter.innerHTML = '<option value="">All codes</option>' +
      codes.map((c) => `<option value="${escapeHtml(c)}"${c === currentCode ? " selected" : ""}>${escapeHtml(c)}</option>`).join("");
    if (codes.includes(currentCode)) {
      findingsCodeFilter.value = currentCode;
    } else {
      state.findingFilters.code = "";
      findingsCodeFilter.value = "";
    }
  }

  if (findingsSnapshotFilter) {
    const currentSnap = state.findingFilters.snapshot;
    const snaps = Array.from(new Set(findings.map((f) => f.snapshotId).filter(Boolean))).sort();
    findingsSnapshotFilter.innerHTML = '<option value="">All snapshots</option>' +
      snaps.map((s) => `<option value="${escapeHtml(s)}"${s === currentSnap ? " selected" : ""}>${escapeHtml(s)}</option>`).join("");
    if (snaps.includes(currentSnap)) {
      findingsSnapshotFilter.value = currentSnap;
    } else {
      state.findingFilters.snapshot = "";
      findingsSnapshotFilter.value = "";
    }
  }

  const filtered = getFilteredFindings(findings);
  const waivedCount = findings.filter((f) => state.waivers[f.id]).length;

  if (findingsCounterEl) {
    findingsCounterEl.textContent = `Showing ${filtered.length} of ${findings.length} findings (${waivedCount} waived)`;
  }

  if (!findings.length) {
    findingsEl.innerHTML = '<p class="empty-findings">No validation findings.</p>';
    return;
  }

  const errorCount = findings.filter((finding) => finding.severity === "error").length;
  const warningCount = findings.filter((finding) => finding.severity === "warning").length;
  const summary = `${errorCount} error${errorCount === 1 ? "" : "s"}, ${warningCount} warning${warningCount === 1 ? "" : "s"}`;

  if (!filtered.length) {
    findingsEl.innerHTML = `<p class="findings-summary">${escapeHtml(summary)}</p><p class="empty-findings">No findings match the current filters. <button type="button" id="findings-inline-reset" class="secondary" style="padding: 2px 6px; font-size: 11px; margin-left: 6px;">Clear filters</button></p>`;
    const inlineReset = document.getElementById("findings-inline-reset");
    if (inlineReset) {
      inlineReset.addEventListener("click", () => {
        if (findingsClearFiltersBtn) findingsClearFiltersBtn.click();
      });
    }
    return;
  }

  const items = filtered.map((finding) => {
    const waiver = state.waivers[finding.id];
    const isExpired = isWaiverExpired(waiver);
    const isEditing = state.editingWaiverFindingId === finding.id;
    const isSelected = state.selectedFindingId === finding.id;

    let waiverBadgeHtml = '';
    if (waiver) {
      if (isExpired) {
        waiverBadgeHtml = `<span class="badge badge-waiver-expired" title="Waiver expired on ${escapeHtml(waiver.expiresAt || "")}">[EXPIRED WAIVER]</span>`;
      } else {
        waiverBadgeHtml = `<span class="badge badge-waived" title="Waived by ${escapeHtml(waiver.reviewer)}">[WAIVED]</span>`;
      }
    }

    let waiverContentHtml = '';
    if (isEditing) {
      waiverContentHtml = `
        <div class="waiver-form" data-finding-id="${escapeHtml(finding.id)}">
          <div style="font-weight: 600; font-size: 11px; margin-bottom: 2px;">${waiver ? "Edit Waiver" : "Waive Finding"}</div>
          <label>
            <span>Reviewer *</span>
            <input type="text" class="waiver-input-reviewer" placeholder="e.g. auditor@company.com" value="${escapeHtml(waiver ? waiver.reviewer : "")}" required>
          </label>
          <label>
            <span>Reason *</span>
            <input type="text" class="waiver-input-reason" placeholder="e.g. Legacy accepted risk" value="${escapeHtml(waiver ? waiver.reason : "")}" required>
          </label>
          <label>
            <span>Expiry Date (optional)</span>
            <input type="date" class="waiver-input-expiry" value="${escapeHtml(waiver && waiver.expiresAt ? waiver.expiresAt.split('T')[0] : "")}">
          </label>
          <div class="waiver-form-error" style="display: none;"></div>
          <div class="waiver-form-buttons">
            <button type="button" class="primary save-waiver-btn" data-finding-id="${escapeHtml(finding.id)}" style="padding: 3px 8px; font-size: 11px;">Save Waiver</button>
            <button type="button" class="secondary cancel-waiver-btn" data-finding-id="${escapeHtml(finding.id)}" style="padding: 3px 8px; font-size: 11px;">Cancel</button>
          </div>
        </div>
      `;
    } else if (waiver) {
      waiverContentHtml = `
        <div class="waiver-box">
          <div class="waiver-meta-row">
            <span><strong>Reviewer:</strong> ${escapeHtml(waiver.reviewer)}</span>
            ${waiver.expiresAt ? `<span><strong>Expires:</strong> ${escapeHtml(waiver.expiresAt.split('T')[0])}</span>` : "<span><strong>Expires:</strong> Never</span>"}
            ${isExpired ? `<span style="color: var(--alert-red); font-weight: bold;">(EXPIRED)</span>` : ""}
          </div>
          <div class="waiver-reason"><strong>Reason:</strong> ${escapeHtml(waiver.reason)}</div>
          <div class="waiver-actions-row">
            <button type="button" class="secondary edit-waiver-btn" data-finding-id="${escapeHtml(finding.id)}" style="padding: 2px 6px; font-size: 11px;">Edit Waiver</button>
            <button type="button" class="secondary danger revoke-waiver-btn" data-finding-id="${escapeHtml(finding.id)}" style="padding: 2px 6px; font-size: 11px;">Revoke Waiver</button>
          </div>
        </div>
      `;
    } else {
      waiverContentHtml = `
        <div style="margin-top: 6px;">
          <button type="button" class="secondary waive-finding-btn" data-finding-id="${escapeHtml(finding.id)}" style="padding: 2px 6px; font-size: 11px;">Waive Finding</button>
        </div>
      `;
    }

    let actionButtons = '';
    if (finding.nodeIds && finding.nodeIds.length > 0) {
      const linksHtml = finding.nodeIds.map((nodeId) => {
        let node = state.graph.nodes.find((n) => n.id === nodeId);
        if (!node && state.graph.nodes.length > 0) {
          const parts = nodeId.split("-");
          const digest = parts.length > 1 ? parts[1] : "";
          if (digest) {
            node = state.graph.nodes.find((n) => n.id.endsWith(digest));
          }
        }
        if (!node) return '';
        return `
          <div class="finding-node-links" style="margin-top: 6px; padding-top: 4px; border-top: 1px dashed var(--border);">
            <div style="font-size: 11px; font-weight: bold; color: var(--text);">${escapeHtml(node.label)} (${escapeHtml(node.type)}):</div>
            <div class="button-row" style="margin-top: 4px; display: flex; gap: 4px;">
              <button class="finding-action-btn go-to-node" data-node-id="${escapeHtml(node.id)}" type="button" style="padding: 2px 6px; font-size: 11px; cursor: pointer;">Go to Node</button>
              <button class="finding-action-btn view-xml" data-node-id="${escapeHtml(node.id)}" type="button" style="padding: 2px 6px; font-size: 11px; cursor: pointer;">View XML</button>
              <button class="finding-action-btn view-html" data-node-id="${escapeHtml(node.id)}" type="button" style="padding: 2px 6px; font-size: 11px; cursor: pointer;">View HTML</button>
            </div>
          </div>
        `;
      }).join('');
      if (linksHtml) {
        actionButtons = `<div class="finding-actions" style="margin-top: 6px;">${linksHtml}</div>`;
      }
    }

    const stateClass = waiver ? (isExpired ? "waiver-expired" : "waived") : "";
    const selectedClass = isSelected ? "selected" : "";

    return `
      <li class="finding ${escapeHtml(finding.severity || "warning")} ${stateClass} ${selectedClass}" data-finding-id="${escapeHtml(finding.id)}" tabindex="0" role="article" aria-label="Finding ${escapeHtml(finding.code || "")}, severity ${escapeHtml(finding.severity || "warning")}">
        <div class="finding-header">
          <div class="finding-badges">
            <span class="badge badge-severity-${escapeHtml(finding.severity || "warning")}">${escapeHtml(finding.severity || "warning")}</span>
            <span class="badge badge-snapshot">${escapeHtml(finding.snapshotId || "")}</span>
            ${waiverBadgeHtml}
          </div>
          <strong class="finding-title">${escapeHtml(finding.code || "validation finding")}</strong>
        </div>
        <p class="finding-message">${escapeHtml(finding.message || "No message supplied.")}</p>
        ${waiverContentHtml}
        ${actionButtons}
      </li>
    `;
  }).join("");

  findingsEl.innerHTML = `<p class="findings-summary">${escapeHtml(summary)}</p><ul class="findings-list">${items}</ul>`;
}

function renderRiskReport(risk) {
  if (!risk) {
    riskContainer.hidden = true;
    riskReportEl.replaceChildren();
    return;
  }

  riskContainer.hidden = false;
  const severity = risk.score >= 70 ? "high" : risk.score >= 30 ? "medium" : "low";

  const scoreBoxEl = document.createElement("div");
  scoreBoxEl.className = "risk-score-box";

  const scoreValueEl = document.createElement("span");
  scoreValueEl.className = `risk-score-value ${severity}`;
  scoreValueEl.textContent = String(Math.round(risk.score));

  const scoreLabelEl = document.createElement("span");
  scoreLabelEl.className = "risk-score-label";
  scoreLabelEl.textContent = `${severity.toUpperCase()} RISK`;

  scoreBoxEl.append(scoreValueEl, scoreLabelEl);

  const factorsListEl = document.createElement("ul");
  factorsListEl.className = "risk-factors-list";

  (risk.factors || []).forEach((f) => {
    const factorLi = document.createElement("li");
    factorLi.className = "risk-factor";
    if (f.severity) {
      factorLi.classList.add(f.severity);
    }

    const codeStrong = document.createElement("strong");
    codeStrong.textContent = String(f.code ?? "");

    factorLi.append(
      codeStrong,
      ` (Weight: ${f.weight ?? ""}): `,
      String(f.message ?? "")
    );

    factorsListEl.appendChild(factorLi);
  });

  riskReportEl.replaceChildren(scoreBoxEl, factorsListEl);
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

function safeAnchorPart(str) {
  if (!str) return "";
  return encodeURIComponent(str).replace(/%20/g, " ");
}

function getHtmlAnchorsForNode(node) {
  let anchors = [];
  if (!state.graph || !state.graph.nodes) return [];
  const nodesById = new Map(state.graph.nodes.map((item) => [item.id, item]));
  const links = state.graph.links || [];

  if (node.type === "Plan") {
    anchors = [`${safeAnchorPart(node.label)}-plan`];
  } else if (node.type === "PlanComponent") {
    const planLinks = links.filter(
      (link) => link.relationship === "belongs_to_plan" && link.source === node.id
    );
    if (planLinks.length > 0) {
      anchors = planLinks.map((link) => {
        const plan = nodesById.get(link.target);
        const planLabel = plan ? plan.label : "";
        return `${safeAnchorPart(node.label)}-plan-${safeAnchorPart(planLabel)}`;
      });
    } else {
      anchors = [`${safeAnchorPart(node.label)}-comp`];
    }
  } else if (node.type === "Rule") {
    const componentLinks = links.filter(
      (link) => link.relationship === "belongs_to_plan_component" && link.source === node.id
    );
    componentLinks.forEach((cLink) => {
      const comp = nodesById.get(cLink.target);
      if (comp) {
        const planLinks = links.filter(
          (link) => link.relationship === "belongs_to_plan" && link.source === comp.id
        );
        if (planLinks.length > 0) {
          planLinks.forEach((pLink) => {
            const plan = nodesById.get(pLink.target);
            if (plan) {
              anchors.push(`${safeAnchorPart(node.label)}-rule-${safeAnchorPart(comp.label)}-${safeAnchorPart(plan.label)}`);
            }
          });
        }
      }
    });
    if (anchors.length === 0) {
      anchors = [`${safeAnchorPart(node.label)}-rule`];
    }
  } else if (["Formula", "Variable", "LookupTable", "FixedValue", "Quota", "Territory"].includes(node.type)) {
    const suffix = {
      Formula: "-formula",
      Variable: "-var",
      LookupTable: "-mdlt",
      FixedValue: "-fv",
      Quota: "-quota",
      Territory: "-terr",
    }[node.type];
    anchors = [`${safeAnchorPart(node.label)}${suffix}`];
  }
  return anchors.sort((a, b) => a.localeCompare(b));
}

function selectAndFocusNode(node) {
  if (!node) return;

  // Sync accessible graph tree selection
  const listItems = document.querySelectorAll("#accessible-node-list .accessible-node-item");
  listItems.forEach((li) => {
    const isThisNode = li.dataset.nodeId === node.id;
    li.setAttribute("aria-selected", isThisNode ? "true" : "false");
    li.tabIndex = isThisNode ? 0 : -1;
    if (isThisNode) {
      li.scrollIntoView({ block: "nearest" });
    }
  });

  announceA11y(`Selected ${node.type}: ${node.label || node.name || node.id}`);

  if (!state.cy) {
    showNodeDetails(node);
    return;
  }
  const cyNode = state.cy.getElementById(node.id);
  if (cyNode && cyNode.length > 0) {
    state.cy.elements().unselect();
    cyNode.select();
    highlightDependencies(cyNode);
    showNodeDetails(node);
    state.cy.animate({
      center: { eles: cyNode },
      zoom: Math.max(state.cy.zoom(), 1.2),
      duration: 500,
    });
  } else {
    showNodeDetails(node);
  }
}

function showNodeDetails(node) {
  if (node.type === "Rule") {
    state.selectedRule = { id: node.id, snapshotId: node.snapshotId };
    lineageTab.disabled = false;
  } else {
    state.selectedRule = null;
    lineageTab.disabled = true;
  }
  state.selectedNode = node;
  if (typeof updateAiSummaryPanel === "function") {
    updateAiSummaryPanel();
  }
  const hierarchy = hierarchyFor(node);
  const riskFactors = (state.graph.migrationRisk?.factors || []).filter((f) => f.nodeIds?.includes(node.id));
  const riskHtml = riskFactors.length > 0
    ? `<dt>Migration risk (${riskFactors.length})</dt>` +
      riskFactors
        .map(
          (rf) =>
            `<dd class="risk-factor ${escapeHtml(rf.severity || "")}"><strong>${escapeHtml(rf.code || "")}</strong> (Weight: ${escapeHtml(String(rf.weight ?? ""))}): ${escapeHtml(rf.message || "")}</dd>`
        )
        .join("")
    : "";

  // Get HTML anchors and generate HTML links
  let htmlLinksHtml = "";
  const htmlInputFiles = state.html ? (state.html.inputFiles || (state.html.inputName ? [state.html.inputName] : [])) : [];
  if (!state.html) {
    htmlLinksHtml = '<span style="color: var(--muted-text); font-style: italic;">Unavailable (HTML not generated)</span>';
  } else if (node.sourceFile && htmlInputFiles.length > 0 && !htmlInputFiles.includes(node.sourceFile)) {
    htmlLinksHtml = `<span style="color: var(--muted-text); font-style: italic;" title="This node belongs to '${escapeHtml(node.sourceFile)}', but HTML is generated for '${escapeHtml(htmlInputFiles.join(", "))}'">Unavailable (File mismatch)</span>`;
  } else {
    const anchors = getHtmlAnchorsForNode(node);
    if (anchors.length === 0) {
      htmlLinksHtml = '<span style="color: var(--muted-text); font-style: italic;">Unavailable (No HTML section)</span>';
    } else {
      htmlLinksHtml = anchors.map((anchor) => {
        let label = "View in HTML";
        if (node.type === "Rule" || node.type === "PlanComponent") {
          const parts = anchor.split("-");
          if (node.type === "Rule" && parts.length >= 4) {
            const planName = parts[parts.length - 1];
            const compName = parts[parts.length - 2];
            label = `View in HTML (under ${escapeHtml(compName)} / ${escapeHtml(planName)})`;
          } else if (node.type === "PlanComponent" && parts.length >= 3) {
            const planName = parts[parts.length - 1];
            label = `View in HTML (under ${escapeHtml(planName)})`;
          }
        }
        return `<button class="view-html-anchor-btn" data-anchor="${escapeHtml(anchor)}" type="button" style="display: block; margin-top: 4px; text-align: left; padding: 4px 8px; font-size: 12px; cursor: pointer; width: 100%;">${label}</button>`;
      }).join("");
    }
  }

  const asOfVal = effectiveDateFilter ? effectiveDateFilter.value : "";
  const temporal = computeTemporalStatus(node, asOfVal);

  summaryEl.innerHTML = `
    <dt>Name</dt><dd>${escapeHtml(node.label)}</dd>
    ${riskHtml}
    <dt>Type</dt><dd>${escapeHtml(node.type)}</dd>
    <dt>Temporal status</dt>
    <dd>
      <span class="temporal-badge ${escapeHtml(temporal.status)}">${escapeHtml(temporal.label)}</span>
      <div class="temporal-explanation">${escapeHtml(temporal.explanation)}</div>
    </dd>
    <dt>Effective range</dt><dd>${escapeHtml(temporal.range)}</dd>
    ${node.type === "Rule" ? '<dt>Lineage</dt><dd><button id="open-lineage-button" type="button">Open lineage</button></dd>' : ""}
    <dt>HTML Preview</dt><dd>${htmlLinksHtml}</dd>
    <dt>Associated plans</dt><dd>${escapeHtml(hierarchy.plans.join(", ") || "None")}</dd>
    <dt>Associated plan components</dt><dd>${escapeHtml(hierarchy.components.join(", ") || "None")}</dd>
    <dt>Associated rules</dt><dd>${escapeHtml(hierarchy.rules.join(", ") || "None")}</dd>
    <dt>Source file</dt><dd>${escapeHtml(node.sourceFile)}</dd>
    <dt>XML path</dt><dd>${escapeHtml(node.xmlPath)}</dd>
    <dt>Metadata</dt><dd>${escapeHtml(JSON.stringify(node.metadata, null, 2))}</dd>
  `;
  rawXmlEl.textContent = node.rawXml || "";
  document.getElementById("open-lineage-button")?.addEventListener("click", () => openRuleLineage(node));

  // Add listeners for any HTML preview anchor buttons inside the summary
  summaryEl.querySelectorAll(".view-html-anchor-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const anchor = btn.dataset.anchor;
      switchWorkspace("html-output-view");
      const preview = document.getElementById("html-output-preview");
      const doc = preview.contentDocument || preview.contentWindow.document;
      if (doc) {
        const candidates = [anchor, decodeURIComponent(anchor)];
        let element = null;
        for (const cand of candidates) {
          element = doc.getElementsByName(cand)[0] || doc.getElementById(cand);
          if (element) break;
        }
        if (element) {
          element.scrollIntoView({ block: "start", behavior: "smooth" });
          setStatus(`Navigated to HTML section for ${node.label}`);
        } else {
          setStatus(`HTML representation unavailable: Anchor '${anchor}' not found in preview.`);
        }
      }
    });
  });

  setupAiSummaryForNode(node, hierarchy);
}

window.showNodeDetails = showNodeDetails;

function clearSelectedRule() {
  state.selectedRule = null;
  state.selectedNode = null;
  lineageTab.disabled = true;
  if (typeof updateAiSummaryPanel === "function") {
    updateAiSummaryPanel();
  }
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

const PIPELINE_STAGE_COLORS = {
  allocate: { bg: "#7b1fa2", text: "#ffffff", border: "#4a148c" },
  credit: { bg: "#1976d2", text: "#ffffff", border: "#0d47a1" },
  primary_measurement: { bg: "#0097a7", text: "#ffffff", border: "#006064" },
  secondary_measurement: { bg: "#00796b", text: "#ffffff", border: "#004d40" },
  incentive: { bg: "#2e7d32", text: "#ffffff", border: "#1b5e20" },
  deposit: { bg: "#ef6c00", text: "#ffffff", border: "#e65100" },
  payment: { bg: "#c62828", text: "#ffffff", border: "#b71c1c" },
  unknown: { bg: "#616161", text: "#ffffff", border: "#424242" },
};

function populatePipelinePlanFilter(graph) {
  if (!pipelinePlanFilter) return;
  const plans = (graph?.nodes || []).filter((n) => n.type === "Plan");
  const currentVal = pipelinePlanFilter.value;
  pipelinePlanFilter.innerHTML = '<option value="">All Plans / Full Model</option>';
  plans.forEach((plan) => {
    const opt = document.createElement("option");
    opt.value = plan.id;
    opt.textContent = plan.label;
    pipelinePlanFilter.appendChild(opt);
  });
  if (plans.some((p) => p.id === currentVal)) {
    pipelinePlanFilter.value = currentVal;
  } else {
    pipelinePlanFilter.value = "";
  }
}

function destroyPipelineRenderer() {
  if (state.pipelineCy) {
    state.pipelineCy.destroy();
    state.pipelineCy = null;
  }
  if (pipelineGraphEl) {
    pipelineGraphEl.replaceChildren();
  }
  if (pipelineEvidencePanel) {
    pipelineEvidencePanel.hidden = true;
  }
  if (pipelineSummaryText) {
    pipelineSummaryText.textContent = "Select or load configuration to analyze pipeline execution flow.";
  }
  if (pipelineSummaryMetrics) {
    pipelineSummaryMetrics.replaceChildren();
  }
  if (pipelineEmptyEl) {
    pipelineEmptyEl.hidden = true;
  }
}

function pipelineCytoscapeStyles(graphTheme) {
  return [
    {
      selector: "node",
      style: {
        shape: "round-rectangle",
        "background-color": "data(stageBg)",
        "border-color": "data(nodeBorderColor)",
        "border-width": 2,
        "border-style": "data(borderStyle)",
        color: "#ffffff",
        label: "data(label)",
        "font-size": 11,
        "font-weight": 600,
        height: 52,
        width: 140,
        "text-valign": "center",
        "text-halign": "center",
        "text-wrap": "wrap",
        "text-max-width": 130,
        padding: 6,
      },
    },
    {
      selector: "node[orderStatus = 'unknown']",
      style: {
        "border-style": "dashed",
        "border-color": "#ffa726",
        "border-width": 3,
      },
    },
    {
      selector: "node:selected",
      style: {
        "border-color": "#ffffff",
        "border-width": 4,
      },
    },
    {
      selector: "edge",
      style: {
        "curve-style": "bezier",
        "line-color": "#2e7d32",
        "target-arrow-color": "#2e7d32",
        "target-arrow-shape": "triangle",
        width: 2,
        label: "data(edgeLabel)",
        "font-size": 9,
        color: graphTheme.text,
        "text-background-color": graphTheme.labelBackground,
        "text-background-opacity": 0.85,
        "text-background-padding": 2,
      },
    },
    {
      selector: "edge[orderStatus = 'unknown']",
      style: {
        "line-style": "dashed",
        "line-color": "#e65100",
        "target-arrow-color": "#e65100",
        "target-arrow-shape": "triangle",
        width: 2.5,
      },
    },
    {
      selector: "edge:selected",
      style: {
        width: 4,
        "line-color": graphTheme.accent,
        "target-arrow-color": graphTheme.accent,
      },
    },
  ];
}

async function renderPipelineFlow() {
  if (!state.graph || !state.graph.nodes || state.graph.nodes.length === 0) {
    if (pipelineSummaryText) {
      pipelineSummaryText.textContent = "Load a configuration to view pipeline execution flow.";
    }
    return;
  }

  const planId = pipelinePlanFilter ? pipelinePlanFilter.value : "";
  const orderFilter = pipelineOrderFilter ? pipelineOrderFilter.value : "";

  let flowData = null;
  try {
    const url = `/api/pipeline-flow${planId ? `?plan_id=${encodeURIComponent(planId)}` : ""}`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.graph),
    });
    if (resp.ok) {
      flowData = await resp.json();
    }
  } catch (err) {
    console.warn("Failed to fetch pipeline flow from API:", err);
  }

  if (!flowData) {
    if (pipelineSummaryText) {
      pipelineSummaryText.textContent = "Unable to compute pipeline execution flow.";
    }
    return;
  }

  state.pipelineFlow = flowData;

  let steps = flowData.steps || [];
  let transitions = flowData.transitions || [];

  if (orderFilter === "known") {
    steps = steps.filter((s) => s.orderStatus === "known");
    const stepIds = new Set(steps.map((s) => s.id));
    transitions = transitions.filter((t) => t.orderStatus === "known" && stepIds.has(t.sourceStepId) && stepIds.has(t.targetStepId));
  } else if (orderFilter === "unknown") {
    const unknownTrans = transitions.filter((t) => t.orderStatus === "unknown");
    const unknownNodeIds = new Set([
      ...steps.filter((s) => s.orderStatus === "unknown").map((s) => s.id),
      ...unknownTrans.flatMap((t) => [t.sourceStepId, t.targetStepId]),
    ]);
    steps = steps.filter((s) => unknownNodeIds.has(s.id));
    const stepIds = new Set(steps.map((s) => s.id));
    transitions = unknownTrans.filter((t) => stepIds.has(t.sourceStepId) && stepIds.has(t.targetStepId));
  }

  const scopeLabel = flowData.scopedPlanLabel || "Full Configuration";
  if (pipelineSummaryText) {
    pipelineSummaryText.textContent = `Pipeline execution flow for ${scopeLabel}: ${steps.length} step${steps.length === 1 ? "" : "s"}, ${transitions.length} transition${transitions.length === 1 ? "" : "s"}.`;
  }

  const knownCount = flowData.summary?.knownCount ?? transitions.filter((t) => t.orderStatus === "known").length;
  const unknownCount = flowData.summary?.unknownCount ?? transitions.filter((t) => t.orderStatus === "unknown").length;

  if (pipelineSummaryMetrics) {
    pipelineSummaryMetrics.innerHTML = `
      <span class="pipeline-badge known" title="${knownCount} transitions with verifiable deterministic execution order">${knownCount} Known Order</span>
      ${unknownCount > 0 ? `<span class="pipeline-badge unknown" title="${unknownCount} transitions with unknown execution order (cannot be determined from source XML)">${unknownCount} Unknown Execution Order</span>` : ""}
    `;
  }

  if (steps.length === 0) {
    if (state.pipelineCy) {
      state.pipelineCy.destroy();
      state.pipelineCy = null;
    }
    if (pipelineEmptyEl) pipelineEmptyEl.hidden = false;
    if (pipelineGraphEl) pipelineGraphEl.hidden = true;
    return;
  }

  if (pipelineEmptyEl) pipelineEmptyEl.hidden = true;
  if (pipelineGraphEl) pipelineGraphEl.hidden = false;

  const graphTheme = graphThemeColors();

  const cyElements = [];

  steps.forEach((step) => {
    const stageKey = step.stage || "unknown";
    const stageColor = PIPELINE_STAGE_COLORS[stageKey] || PIPELINE_STAGE_COLORS.unknown;
    const seqLabel = step.sequenceNumber !== null && step.sequenceNumber !== undefined ? ` (Seq: ${step.sequenceNumber})` : "";
    const orderBadge = step.orderStatus === "unknown" ? " [Unknown Order]" : "";
    cyElements.push({
      data: {
        id: step.id,
        ruleId: step.ruleId,
        label: `${step.label}\n[${step.stageLabel}]${seqLabel}${orderBadge}`,
        stage: step.stage,
        stageLabel: step.stageLabel,
        stageBg: stageColor.bg,
        nodeBorderColor: stageColor.border,
        borderStyle: step.orderStatus === "unknown" ? "dashed" : "solid",
        orderStatus: step.orderStatus,
        sequenceNumber: step.sequenceNumber,
        ruleSubtype: step.ruleSubtype,
        planLabel: step.planLabel,
        componentLabel: step.componentLabel,
        sourceFile: step.sourceFile,
        evidence: step.sourceEvidence,
        isStep: true,
      },
    });
  });

  transitions.forEach((t) => {
    const isUnknown = t.orderStatus === "unknown";
    let edgeLabel = "";
    if (isUnknown) {
      edgeLabel = "Unknown Order";
    } else if (t.transitionType === "explicit_sequence") {
      edgeLabel = "Sequence";
    }
    cyElements.push({
      data: {
        id: t.id || `t_${t.sourceStepId}_${t.targetStepId}`,
        source: t.sourceStepId,
        target: t.targetStepId,
        orderStatus: t.orderStatus,
        transitionType: t.transitionType,
        evidence: t.sourceEvidence,
        sourceRuleLabel: t.sourceRuleLabel,
        targetRuleLabel: t.targetRuleLabel,
        edgeLabel,
        isTransition: true,
      },
    });
  });

  if (state.pipelineCy) {
    state.pipelineCy.destroy();
    state.pipelineCy = null;
  }

  state.pipelineCy = cytoscape({
    container: pipelineGraphEl,
    elements: cyElements,
    style: pipelineCytoscapeStyles(graphTheme),
    layout: {
      name: "breadthfirst",
      directed: true,
      animate: false,
      fit: true,
      padding: 36,
      spacingFactor: 1.4,
    },
  });

  state.pipelineCy.on("tap", "node", (evt) => {
    showPipelineStepEvidence(evt.target.data());
  });

  state.pipelineCy.on("tap", "edge", (evt) => {
    showPipelineTransitionEvidence(evt.target.data());
  });

  state.pipelineCy.on("tap", (evt) => {
    if (evt.target === state.pipelineCy) {
      if (pipelineEvidencePanel) pipelineEvidencePanel.hidden = true;
    }
  });
}

function showPipelineStepEvidence(d) {
  if (!pipelineEvidencePanel || !pipelineEvidenceBody || !pipelineEvidenceTitle) return;
  pipelineEvidenceTitle.textContent = `Pipeline Step: ${d.label.split('\n')[0]}`;
  const isUnknown = d.orderStatus === "unknown";
  const badgeClass = isUnknown ? "unknown" : "known";
  const badgeText = isUnknown ? "Unknown Execution Order" : "Known Execution Order";

  pipelineEvidenceBody.innerHTML = `
    <div class="pipeline-evidence-field">
      <span class="pipeline-badge ${badgeClass}">${escapeHtml(badgeText)}</span>
    </div>
    <div class="pipeline-evidence-field">
      <strong>Stage:</strong> ${escapeHtml(d.stageLabel || d.stage)}
    </div>
    ${d.sequenceNumber !== null && d.sequenceNumber !== undefined ? `
    <div class="pipeline-evidence-field">
      <strong>Sequence / Order:</strong> ${escapeHtml(String(d.sequenceNumber))}
    </div>` : ""}
    <div class="pipeline-evidence-field">
      <strong>Rule Type:</strong> ${escapeHtml(d.ruleSubtype || "Rule")}
    </div>
    ${d.planLabel ? `
    <div class="pipeline-evidence-field">
      <strong>Plan:</strong> ${escapeHtml(d.planLabel)}
    </div>` : ""}
    ${d.componentLabel ? `
    <div class="pipeline-evidence-field">
      <strong>Plan Component:</strong> ${escapeHtml(d.componentLabel)}
    </div>` : ""}
    ${d.sourceFile ? `
    <div class="pipeline-evidence-field">
      <strong>Source File:</strong> ${escapeHtml(d.sourceFile)}
    </div>` : ""}
    <div class="pipeline-evidence-field" style="margin-top: 8px; border-top: 1px dashed var(--border); padding-top: 6px;">
      <strong>Classification Evidence:</strong>
      <div style="margin-top: 4px; color: var(--text-muted); font-style: italic;">${escapeHtml(d.evidence || "No evidence recorded.")}</div>
    </div>
  `;
  pipelineEvidencePanel.hidden = false;
}

function showPipelineTransitionEvidence(d) {
  if (!pipelineEvidencePanel || !pipelineEvidenceBody || !pipelineEvidenceTitle) return;
  pipelineEvidenceTitle.textContent = "Pipeline Transition Evidence";
  const isUnknown = d.orderStatus === "unknown";
  const badgeClass = isUnknown ? "unknown" : "known";
  const badgeText = isUnknown ? "Unknown Execution Order" : "Deterministic Precedence";

  pipelineEvidenceBody.innerHTML = `
    <div class="pipeline-evidence-field">
      <span class="pipeline-badge ${badgeClass}">${escapeHtml(badgeText)}</span>
    </div>
    <div class="pipeline-evidence-field">
      <strong>Transition Type:</strong> ${escapeHtml(d.transitionType || "transition")}
    </div>
    <div class="pipeline-evidence-field">
      <strong>Source Rule:</strong> ${escapeHtml(d.sourceRuleLabel || d.source)}
    </div>
    <div class="pipeline-evidence-field">
      <strong>Target Rule:</strong> ${escapeHtml(d.targetRuleLabel || d.target)}
    </div>
    <div class="pipeline-evidence-field" style="margin-top: 8px; border-top: 1px dashed var(--border); padding-top: 6px;">
      <strong>Order Determination Evidence:</strong>
      <div style="margin-top: 4px; color: var(--text-muted); line-height: 1.4;">${escapeHtml(d.evidence || "No evidence recorded.")}</div>
    </div>
  `;
  pipelineEvidencePanel.hidden = false;
}

window.renderPipelineFlow = renderPipelineFlow;
window.PIPELINE_STAGE_COLORS = PIPELINE_STAGE_COLORS;

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
  hideAiSummary();
}

const graphExportFormats = {
  json: {
    endpoint: "/api/export/graph-json",
    filename: "sap-im-config-graph.json",
    label: "JSON",
  },
  csv: {
    endpoint: "/api/export/graph-csv",
    filename: "sap-im-config-graph-csv.zip",
    label: "CSV",
  },
  markdown: {
    endpoint: "/api/export/graph-markdown",
    filename: "sap-im-config-graph.md",
    label: "Markdown",
  },
  graphml: {
    endpoint: "/api/export/graph-graphml",
    filename: "sap-im-config-graph.graphml",
    label: "GraphML",
  },
  neo4j: {
    endpoint: "/api/export/graph-neo4j",
    filename: "sap-im-config-graph-neo4j.zip",
    label: "Neo4j",
  },
};

async function exportGraph(format) {
  const exportFormat = graphExportFormats[format];
  if (!exportFormat) return setStatus("Unsupported graph export format.");
  try {
    while (pendingGraphGeneration) await pendingGraphGeneration;
    state.graph.waivers = Object.values(state.waivers);
    const asOfDate = effectiveDateFilter?.value?.trim() || null;
    if (asOfDate) {
      state.graph.asOfDate = asOfDate;
    } else {
      delete state.graph.asOfDate;
    }
    const response = await fetch(exportFormat.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.graph),
    });
    if (!response.ok) {
      const detail = await graphExportErrorDetail(response);
      return setStatus(`${exportFormat.label} export failed: ${detail}`);
    }
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = exportFormat.filename;
    link.click();
    URL.revokeObjectURL(link.href);
    setStatus(`Exported ${topologyLabel(state.graph.topologyMode)} topology graph ${exportFormat.label}`);
  } catch (error) {
    const detail = error instanceof Error && error.message
      ? error.message
      : "Unexpected local export error.";
    setStatus(`${exportFormat.label} export failed: ${detail}`);
  }
}

function validateGraphForImageExport() {
  if (!state.graph || !state.graph.nodes || state.graph.nodes.length === 0 || !state.cy) {
    setStatus("Cannot export image: Graph is empty. Load or generate a graph first.");
    return null;
  }
  const visibleNodes = state.cy.nodes().filter((node) => node.visible());
  if (visibleNodes.length === 0) {
    setStatus("Cannot export image: No visible nodes match current filters.");
    return null;
  }
  if (visibleNodes.length > 1000) {
    setStatus("Warning: Graph exceeds 1,000 nodes. Use filters to reduce graph size for optimal export.");
  }
  return visibleNodes;
}

function getExportProvenance(visibleNodesCount, totalNodesCount) {
  const schemaVersion = state.graph.schemaVersion || "1.3";
  const sourceFiles = Array.from(
    new Set(
      (state.graph.snapshots || [])
        .flatMap((s) => s.sourceFiles || [])
        .concat(state.graph.nodes.map((n) => n.sourceFile).filter(Boolean))
    )
  );
  const fileNames =
    sourceFiles.map((f) => f.split(/[/\\]/).pop()).join(", ") || "Active configuration";
  const now = new Date();
  const dateStr = now.toISOString().replace("T", " ").substring(0, 19) + " UTC";
  const isFiltered = visibleNodesCount < totalNodesCount;
  const statusLabel = isFiltered
    ? `Filtered Graph (${visibleNodesCount} of ${totalNodesCount} nodes)`
    : `Full Graph (${totalNodesCount} nodes)`;
  const topology = topologyLabel(state.graph.topologyMode);
  const asOfDate = effectiveDateFilter?.value?.trim() || null;
  return {
    schemaVersion,
    fileNames,
    timestamp: dateStr,
    isFiltered,
    statusLabel,
    topology,
    asOfDate,
  };
}

function escapeXml(str) {
  return String(str ?? "").replace(/[<>&"']/g, (c) => {
    switch (c) {
      case "<": return "&lt;";
      case ">": return "&gt;";
      case "&": return "&amp;";
      case '"': return "&quot;";
      case "'": return "&apos;";
      default: return c;
    }
  });
}

async function exportGraphAsPng() {
  const visibleNodes = validateGraphForImageExport();
  if (!visibleNodes) return;
  const themeColors = graphThemeColors();
  const meta = getExportProvenance(visibleNodes.length, state.graph.nodes.length);
  const visibleTypes = Array.from(
    new Set(visibleNodes.map((n) => n.data("type")).filter(Boolean))
  ).sort((a, b) => a.localeCompare(b));

  try {
    const cyPngData = state.cy.png({
      full: true,
      scale: 2,
      bg: themeColors.background,
    });

    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        return setStatus("PNG export failed: Canvas 2D context unavailable.");
      }

      const bannerHeight = 112;
      const padding = 24;
      canvas.width = Math.max(img.width, 820);
      canvas.height = img.height + bannerHeight;

      // Banner background
      ctx.fillStyle = themeColors.surface;
      ctx.fillRect(0, 0, canvas.width, bannerHeight);

      // Separator line
      ctx.strokeStyle = themeColors.border;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, bannerHeight);
      ctx.lineTo(canvas.width, bannerHeight);
      ctx.stroke();

      // Title
      ctx.fillStyle = themeColors.text;
      ctx.font = "bold 16px Inter, -apple-system, sans-serif";
      ctx.fillText(
        `SAP IM Config Explorer - ${meta.topology} (${meta.statusLabel})`,
        padding,
        30
      );

      // Provenance metadata
      const asOfStr = meta.asOfDate ? `  |  As-of Date: ${meta.asOfDate}` : "";
      ctx.fillStyle = themeColors.textMuted || themeColors.text;
      ctx.font = "12px Inter, -apple-system, sans-serif";
      ctx.fillText(
        `Generated: ${meta.timestamp}  |  Schema: ${meta.schemaVersion}  |  Files: ${meta.fileNames}${asOfStr}`,
        padding,
        54
      );

      // Dynamic Legend
      ctx.font = "12px Inter, -apple-system, sans-serif";
      let legendX = padding;
      const legendY = 86;
      ctx.fillStyle = themeColors.text;
      ctx.fillText("Legend:", legendX, legendY);
      legendX += 54;

      visibleTypes.forEach((type) => {
        const color = colorForType(type);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(legendX + 6, legendY - 4, 6, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = themeColors.text;
        ctx.fillText(type, legendX + 16, legendY);
        legendX += ctx.measureText(type).width + 26;
      });

      // Graph body
      ctx.fillStyle = themeColors.background;
      ctx.fillRect(0, bannerHeight, canvas.width, img.height);
      const offsetX = Math.floor((canvas.width - img.width) / 2);
      ctx.drawImage(img, offsetX, bannerHeight);

      // Download
      canvas.toBlob((blob) => {
        if (!blob) return setStatus("PNG export failed: Could not create image blob.");
        const filename = `sap-im-config-graph-${meta.isFiltered ? "filtered" : "full"}.png`;
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
        URL.revokeObjectURL(link.href);
        setStatus(`Exported visible graph as PNG image (${meta.statusLabel}).`);
      }, "image/png");
    };
    img.onerror = () => {
      setStatus("PNG export failed: Image rendering error.");
    };
    img.src = cyPngData;
  } catch (error) {
    const detail = error instanceof Error && error.message ? error.message : "Export failed";
    setStatus(`PNG export failed: ${detail}`);
  }
}

function exportGraphAsSvg() {
  const visibleNodes = validateGraphForImageExport();
  if (!visibleNodes) return;
  const themeColors = graphThemeColors();
  const meta = getExportProvenance(visibleNodes.length, state.graph.nodes.length);
  const visibleTypes = Array.from(
    new Set(visibleNodes.map((n) => n.data("type")).filter(Boolean))
  ).sort((a, b) => a.localeCompare(b));

  try {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    visibleNodes.forEach((node) => {
      const pos = node.position();
      const w = 112;
      const h = 48;
      if (pos.x - w / 2 < minX) minX = pos.x - w / 2;
      if (pos.y - h / 2 < minY) minY = pos.y - h / 2;
      if (pos.x + w / 2 > maxX) maxX = pos.x + w / 2;
      if (pos.y + h / 2 > maxY) maxY = pos.y + h / 2;
    });

    const margin = 48;
    const bannerHeight = 112;
    const graphWidth = Math.max(maxX - minX + margin * 2, 820);
    const graphHeight = maxY - minY + margin * 2;
    const totalWidth = Math.ceil(graphWidth);
    const totalHeight = Math.ceil(graphHeight + bannerHeight);
    const offsetX = Math.round(-minX + (totalWidth - (maxX - minX)) / 2);
    const offsetY = Math.round(-minY + margin + bannerHeight);

    let svg = `<?xml version="1.0" encoding="UTF-8"?>\n`;
    svg += `<svg xmlns="http://www.w3.org/2000/svg" width="${totalWidth}" height="${totalHeight}" viewBox="0 0 ${totalWidth} ${totalHeight}">\n`;
    svg += `  <defs>\n`;
    svg += `    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">\n`;
    svg += `      <path d="M 0 0 L 10 5 L 0 10 z" fill="${themeColors.edge}" />\n`;
    svg += `    </marker>\n`;
    svg += `  </defs>\n`;
    svg += `  <rect width="100%" height="100%" fill="${themeColors.background}" />\n`;

    // Banner
    svg += `  <rect x="0" y="0" width="${totalWidth}" height="${bannerHeight}" fill="${themeColors.surface}" />\n`;
    svg += `  <line x1="0" y1="${bannerHeight}" x2="${totalWidth}" y2="${bannerHeight}" stroke="${themeColors.border}" stroke-width="1" />\n`;

    // Title & Provenance
    svg += `  <text x="24" y="32" font-family="Inter, -apple-system, sans-serif" font-size="16" font-weight="bold" fill="${themeColors.text}">SAP IM Config Explorer - ${escapeXml(meta.topology)} (${escapeXml(meta.statusLabel)})</text>\n`;
    const asOfStr = meta.asOfDate ? `  |  As-of Date: ${escapeXml(meta.asOfDate)}` : "";
    svg += `  <text x="24" y="56" font-family="Inter, -apple-system, sans-serif" font-size="12" fill="${themeColors.textMuted || themeColors.text}">Generated: ${escapeXml(meta.timestamp)}  |  Schema: ${escapeXml(meta.schemaVersion)}  |  Files: ${escapeXml(meta.fileNames)}${asOfStr}</text>\n`;

    // Legend
    svg += `  <text x="24" y="88" font-family="Inter, -apple-system, sans-serif" font-size="12" font-weight="600" fill="${themeColors.text}">Legend:</text>\n`;
    let legX = 80;
    visibleTypes.forEach((type) => {
      const col = colorForType(type);
      svg += `  <circle cx="${legX + 6}" cy="84" r="6" fill="${col}" />\n`;
      svg += `  <text x="${legX + 16}" cy="88" font-family="Inter, -apple-system, sans-serif" font-size="12" fill="${themeColors.text}">${escapeXml(type)}</text>\n`;
      legX += (type.length * 8) + 30;
    });

    // Visible Edges
    const visibleEdges = state.cy.edges().filter((edge) => edge.visible());
    visibleEdges.forEach((edge) => {
      const src = edge.source();
      const tgt = edge.target();
      if (src.visible() && tgt.visible()) {
        const sp = src.position();
        const tp = tgt.position();
        const x1 = Math.round(sp.x + offsetX);
        const y1 = Math.round(sp.y + offsetY);
        const x2 = Math.round(tp.x + offsetX);
        const y2 = Math.round(tp.y + offsetY);
        svg += `  <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${themeColors.edge}" stroke-width="1.5" marker-end="url(#arrow)" />\n`;
      }
    });

    // Visible Nodes
    visibleNodes.forEach((node) => {
      const pos = node.position();
      const w = 112;
      const h = 48;
      const x = Math.round(pos.x + offsetX - w / 2);
      const y = Math.round(pos.y + offsetY - h / 2);
      const col = node.data("displayColor") || colorForType(node.data("type"));
      const label = node.data("label") || node.id();

      svg += `  <g class="graph-node" data-id="${escapeXml(node.id())}">\n`;
      svg += `    <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" ry="6" fill="${col}" stroke="${themeColors.border}" stroke-width="2" />\n`;
      svg += `    <text x="${x + w / 2}" y="${y + h / 2 + 4}" font-family="Inter, -apple-system, sans-serif" font-size="11" text-anchor="middle" fill="${themeColors.text}">${escapeXml(label)}</text>\n`;
      svg += `  </g>\n`;
    });

    svg += `</svg>\n`;

    const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
    const filename = `sap-im-config-graph-${meta.isFiltered ? "filtered" : "full"}.svg`;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
    setStatus(`Exported visible graph as SVG vector (${meta.statusLabel}).`);
  } catch (error) {
    const detail = error instanceof Error && error.message ? error.message : "Export failed";
    setStatus(`SVG export failed: ${detail}`);
  }
}

async function graphExportErrorDetail(response) {
  try {
    const payload = await response.json();
    if (typeof payload.error === "string" && payload.error.trim()) {
      return payload.error.trim();
    }
  } catch (_error) {
    // Fall through to the HTTP status when the local response is not JSON.
  }
  return `${response.status} ${response.statusText}`.trim();
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

async function fetchAiStatus() {
  try {
    const response = await fetch("/api/ai/status");
    if (response.ok) {
      state.aiStatus = await response.json();
    } else {
      state.aiStatus = { enabled: false, provider: "none", configured: false, message: "Failed to load AI status." };
    }
  } catch (error) {
    state.aiStatus = { enabled: false, provider: "none", configured: false, message: `Failed to load AI status: ${error.message}` };
  }
}

let currentSelectedNodeForSummary = null;

function setupAiSummaryForNode(node, hierarchy) {
  currentSelectedNodeForSummary = { node, hierarchy: hierarchy || {} };
  const actionsEl = document.getElementById("ai-summary-actions");
  const unconfiguredEl = document.getElementById("ai-summary-unconfigured");
  const generateAiBtn = document.getElementById("generate-ai-summary-button");

  aiSummaryLabel.style.display = "none";
  aiSummaryContent.style.display = "none";
  aiSummaryContent.innerHTML = '<p class="empty-summary">Select a node to generate an AI summary.</p>';

  if (actionsEl) actionsEl.hidden = false;

  // If aiConfig is disabled, show unconfigured warning and hide the Phase 6 generate button
  if (aiConfig && !aiConfig.enabled) {
    if (unconfiguredEl) {
      unconfiguredEl.hidden = false;
      unconfiguredEl.style.display = "block";
      unconfiguredEl.textContent = aiConfig.message || "AI features are unconfigured or disabled on this workstation.";
    }
    if (generateAiBtn) {
      generateAiBtn.style.display = "none";
    }
  } else {
    if (unconfiguredEl) {
      unconfiguredEl.hidden = true;
      unconfiguredEl.style.display = "none";
    }
    if (generateAiBtn) {
      generateAiBtn.disabled = false;
      generateAiBtn.style.display = "inline-block";
    }
  }

  // Handle local stub / status summary button
  if (!state.aiStatus) {
    generateSummaryButton.disabled = true;
    aiSummaryStatus.textContent = "AI status is loading...";
  } else if (!state.aiStatus.enabled && (!aiConfig || !aiConfig.enabled)) {
    generateSummaryButton.disabled = true;
    generateSummaryButton.style.display = "none";
    aiSummaryStatus.textContent = state.aiStatus.message || "AI summary is not configured.";
  } else {
    generateSummaryButton.disabled = false;
    generateSummaryButton.style.display = "inline-block";
    const provName = state.aiStatus?.provider === "stub" ? "local stub" : (aiConfig?.model === "mock" ? "mock" : "OpenAI");
    aiSummaryStatus.textContent = `Ready to generate summary via ${provName} provider.`;
  }

  aiSummaryContainer.style.display = "block";
}

function hideAiSummary() {
  currentSelectedNodeForSummary = null;
  const actionsEl = document.getElementById("ai-summary-actions");
  const unconfiguredEl = document.getElementById("ai-summary-unconfigured");
  const generateAiBtn = document.getElementById("generate-ai-summary-button");

  if (aiSummaryContainer) {
    aiSummaryContainer.style.display = "none";
    aiSummaryLabel.style.display = "none";
    aiSummaryContent.style.display = "none";
    aiSummaryContent.innerHTML = '<p class="empty-summary">Select a node to generate an AI summary.</p>';
    aiSummaryStatus.textContent = "";
  }
  if (actionsEl) actionsEl.hidden = true;
  if (unconfiguredEl) {
    unconfiguredEl.hidden = true;
    unconfiguredEl.style.display = "none";
  }
  if (generateAiBtn) generateAiBtn.style.display = "none";
}

function updateAiSummaryPanel() {
  if (state.selectedNode) {
    setupAiSummaryForNode(state.selectedNode, {});
  } else {
    hideAiSummary();
  }
}

async function handleGenerateSummaryClick() {
  const node = (currentSelectedNodeForSummary && currentSelectedNodeForSummary.node) || state.selectedNode;
  if (!node) return;
  const hierarchy = (currentSelectedNodeForSummary && currentSelectedNodeForSummary.hierarchy) || {};

  generateSummaryButton.disabled = true;
  const generateAiBtn = document.getElementById("generate-ai-summary-button");
  if (generateAiBtn) generateAiBtn.disabled = true;

  aiSummaryStatus.textContent = "Generating summary...";
  aiSummaryLabel.style.display = "none";
  aiSummaryContent.style.display = "none";
  aiSummaryContent.innerHTML = '<p class="empty-summary">Generating local AI summary...</p>';

  try {
    const payload = {
      id: node.id,
      nodeId: node.id,
      label: node.label,
      type: node.type,
      sourceFile: node.sourceFile,
      xmlPath: node.xmlPath,
      rawXml: node.rawXml || "",
      metadata: node.metadata || {},
      associatedPlans: hierarchy.plans || [],
      associatedPlanComponents: hierarchy.components || [],
      associatedRules: hierarchy.rules || []
    };

    const response = await fetch("/api/ai/summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || `Failed with status ${response.status}`);
    }

    const providerLabel = data.provider === "stub" ? "Stub" : (data.provider || "OpenAI");
    aiSummaryLabel.textContent = `AI-Generated Summary (${providerLabel} Provider)`;
    aiSummaryLabel.style.display = "block";

    const summaryText = data.text || data.summary || "";
    const disclaimerHtml = data.disclaimer ? `<div class="ai-disclaimer">${escapeHtml(data.disclaimer)}</div>` : "";
    const formattedHtml = formatMarkdown(summaryText);
    const metaHtml = `<div class="ai-metadata-footer">Model: ${escapeHtml(data.model || "stub")} | Provider: ${escapeHtml(data.provider || "Local Mock Provider")}<br>Generated at: ${escapeHtml(new Date(data.timestamp || Date.now()).toLocaleString())}</div>`;

    aiSummaryContent.innerHTML = `${disclaimerHtml}<div class="markdown-preview">${formattedHtml}</div>${metaHtml}`;
    aiSummaryContent.style.display = "block";
    aiSummaryStatus.textContent = "Summary generated successfully.";
  } catch (error) {
    aiSummaryStatus.textContent = "Error generating summary.";
    aiSummaryContent.innerHTML = `<p class="empty-summary" style="color:var(--error);">${escapeHtml(error.message || "An unexpected error occurred.")}</p>`;
    aiSummaryContent.style.display = "block";
  } finally {
    generateSummaryButton.disabled = false;
    if (generateAiBtn) generateAiBtn.disabled = false;
  }
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

// Saved Graph Exploration Sessions implementation

function showSessionMessage(text, type = "success") {
  sessionMessageBox.textContent = text;
  sessionMessageBox.className = `session-message-box ${type}`;
  sessionMessageBox.hidden = false;
}

function hideSessionMessage() {
  sessionMessageBox.hidden = true;
  sessionMessageBox.textContent = "";
}

function loadSessionsFromStorage() {
  try {
    const raw = localStorage.getItem("sap-im-config-explorer-sessions");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        state.sessions = parsed.filter(validateSessionData);
      } else {
        state.sessions = [];
      }
    } else {
      state.sessions = [];
    }
  } catch (e) {
    state.sessions = [];
    showSessionMessage("Failed to load saved sessions from localStorage.", "error");
  }
  renderSessionsList();
}

function saveSessionsToStorage() {
  try {
    localStorage.setItem("sap-im-config-explorer-sessions", JSON.stringify(state.sessions));
  } catch (e) {
    showSessionMessage("Failed to persist sessions to localStorage: " + e.message, "error");
  }
}

function validateSessionData(session) {
  if (!session || typeof session !== "object") return false;
  if (typeof session.id !== "string" || !session.id) return false;
  if (typeof session.name !== "string" || !session.name) return false;
  if (typeof session.createdAt !== "string") return false;
  if (typeof session.themePreference !== "string") return false;
  if (!session.files || typeof session.files !== "object") return false;
  if (!Array.isArray(session.files.nonProduction) || !Array.isArray(session.files.production)) return false;
  if (!session.filters || typeof session.filters !== "object") return false;
  if (!session.graph || typeof session.graph !== "object") return false;
  return true;
}

window.validateSessionData = validateSessionData;

function serializeSession(name) {
  const npFiles = [...npFileInput.files].map(f => f.name);
  const pFiles = [...pFileInput.files].map(f => f.name);

  // Layout info: zoom, pan, and position of all nodes
  const layout = {
    zoom: state.cy ? state.cy.zoom() : 1,
    pan: state.cy ? state.cy.pan() : { x: 0, y: 0 },
    nodes: state.cy ? state.cy.nodes().map(node => ({
      id: node.id(),
      position: { ...node.position() }
    })) : []
  };

  const selectedItem = state.selectedRule ? {
    id: state.selectedRule.id,
    snapshotId: state.selectedRule.snapshotId,
    type: "Rule"
  } : (state.cy && state.cy.nodes(":selected").length ? {
    id: state.cy.nodes(":selected").first().id(),
    snapshotId: state.cy.nodes(":selected").first().data("snapshotId"),
    type: state.cy.nodes(":selected").first().data("type")
  } : (state.cy && state.cy.edges(":selected").length ? {
    id: state.cy.edges(":selected").first().id(),
    type: "Edge",
    data: state.cy.edges(":selected").first().data()
  } : null));

  return {
    id: "session-" + Date.now() + "-" + Math.random().toString(36).substr(2, 9),
    name: name,
    createdAt: new Date().toISOString(),
    themePreference: currentTheme(),
    topologyMode: topologySelect.value,
    files: {
      nonProduction: npFiles,
      production: pFiles
    },
    filters: {
      search: searchInput.value,
      type: typeFilter.value,
      sourceFile: sourceFileFilter.value,
      relationship: relationshipFilter.value,
      confidence: confidenceFilter.value,
      effectiveDate: effectiveDateFilter.value
    },
    layout: layout,
    selectedItem: selectedItem,
    graph: {
      nodes: state.graph.nodes,
      links: state.graph.links,
      findings: state.graph.findings,
      waivers: Object.values(state.waivers),
      migrationRisk: state.graph.migrationRisk
    }
  };
}

window.serializeSession = serializeSession;

function handleSaveSession() {
  const name = sessionNameInput.value.trim();
  if (!name) {
    showSessionMessage("Please enter a valid session name.", "error");
    return;
  }
  const session = serializeSession(name);
  state.sessions.push(session);
  saveSessionsToStorage();
  renderSessionsList();
  sessionNameInput.value = "";
  showSessionMessage(`Session "${name}" saved successfully.`, "success");
}

window.handleSaveSession = handleSaveSession;

function renderSessionsList() {
  savedSessionsList.innerHTML = "";
  if (state.sessions.length === 0) {
    savedSessionsList.innerHTML = '<li class="status">No saved sessions.</li>';
    return;
  }
  state.sessions.forEach(session => {
    const li = document.createElement("li");
    li.className = "session-item";
    li.setAttribute("data-session-id", session.id);

    const nameSpan = document.createElement("span");
    nameSpan.className = "session-item-name";
    nameSpan.textContent = session.name;

    const actionsDiv = document.createElement("div");
    actionsDiv.className = "session-item-actions";

    const restoreBtn = document.createElement("button");
    restoreBtn.type = "button";
    restoreBtn.className = "secondary";
    restoreBtn.textContent = "Restore";
    restoreBtn.addEventListener("click", () => handleRestoreSession(session.id));

    const renameBtn = document.createElement("button");
    renameBtn.type = "button";
    renameBtn.className = "secondary";
    renameBtn.textContent = "Rename";
    renameBtn.addEventListener("click", () => handleRenameSession(session.id));

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "secondary";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", () => handleDeleteSession(session.id));

    actionsDiv.appendChild(restoreBtn);
    actionsDiv.appendChild(renameBtn);
    actionsDiv.appendChild(deleteBtn);

    li.appendChild(nameSpan);
    li.appendChild(actionsDiv);
    savedSessionsList.appendChild(li);
  });
}

function handleRenameSession(id) {
  const session = state.sessions.find(s => s.id === id);
  if (!session) return;
  const newName = prompt("Enter new name for the session:", session.name);
  if (newName === null) return;
  const trimmed = newName.trim();
  if (!trimmed) {
    showSessionMessage("Session name cannot be empty.", "error");
    return;
  }
  session.name = trimmed;
  saveSessionsToStorage();
  renderSessionsList();
  showSessionMessage(`Session renamed to "${trimmed}".`, "success");
}

function handleDeleteSession(id) {
  const session = state.sessions.find(s => s.id === id);
  if (!session) return;
  if (!confirm(`Are you sure you want to delete session "${session.name}"?`)) return;
  state.sessions = state.sessions.filter(s => s.id !== id);
  saveSessionsToStorage();
  renderSessionsList();
  showSessionMessage(`Session "${session.name}" deleted.`, "success");
}

function handleRestoreSession(id) {
  hideSessionMessage();
  const session = state.sessions.find(s => s.id === id);
  if (!session) {
    showSessionMessage("Session not found.", "error");
    return;
  }
  if (!validateSessionData(session)) {
    showSessionMessage("Invalid or outdated session data. Cannot restore.", "error");
    return;
  }

  // Restore Theme Preference
  applyTheme(session.themePreference || "light");

  // Restore Active Filters
  searchInput.value = session.filters?.search || "";
  if (session.topologyMode) {
    topologySelect.value = session.topologyMode;
  }

  // Determine if XML files are matching
  const currentNpFiles = [...npFileInput.files].map(f => f.name);
  const currentPFiles = [...pFileInput.files].map(f => f.name);

  const savedNpFiles = session.files?.nonProduction || [];
  const savedPFiles = session.files?.production || [];

  const arraysEqual = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
  const filesMatch = arraysEqual(currentNpFiles, savedNpFiles) && arraysEqual(currentPFiles, savedPFiles);

  if (filesMatch) {
    sessionExplanation.hidden = true;
    requiredFilesList.textContent = "";
    // If files match, directly restore the full serialized graph, layout, filters, and selection
    restoreGraphAndLayout(session);
    showSessionMessage(`Session "${session.name}" restored successfully.`, "success");
  } else {
    // Show explanation warning and required files
    sessionExplanation.hidden = false;
    const npList = savedNpFiles.length ? `Non-Prod: [${savedNpFiles.join(", ")}]` : "";
    const pList = savedPFiles.length ? `Prod: [${savedPFiles.join(", ")}]` : "";
    requiredFilesList.innerHTML = `<strong>Required files:</strong><br>${npList ? npList + "<br>" : ""}${pList}`;

    // Fallback: we cannot fully restore graph viewport/node positions since files don't match,
    // but we can restore what's possible, or let user know to reselect files first.
    // If we want to be safe, we fail restoration of graph layout but restore inputs/filters.
    showSessionMessage(`Please reselect the original XML files to restore the graph for "${session.name}".`, "error");
  }
}

window.handleRestoreSession = handleRestoreSession;

function restoreGraphAndLayout(session) {
  // Restore State Graph Data
  state.graph = session.graph || { nodes: [], links: [], findings: [] };
  if (session.graph?.waivers && Array.isArray(session.graph.waivers)) {
    session.graph.waivers.forEach((w) => {
      if (w && w.findingId && w.reason && w.reviewer) {
        state.waivers[w.findingId] = {
          findingId: w.findingId,
          reason: w.reason,
          reviewer: w.reviewer,
          createdAt: w.createdAt || new Date().toISOString(),
          expiresAt: w.expiresAt || null,
        };
      }
    });
    saveWaivers(state.waivers);
  }
  clearSelectedRule();
  destroyLineageRenderer();
  populateFilterControls(state.graph);
  renderFindings(state.graph.findings || []);
  renderRiskReport(state.graph.migrationRisk);

  // Restore Filters to input elements before rendering
  typeFilter.value = session.filters?.type || "";
  sourceFileFilter.value = session.filters?.sourceFile || "";
  relationshipFilter.value = session.filters?.relationship || "";
  confidenceFilter.value = session.filters?.confidence || "";
  effectiveDateFilter.value = session.filters?.effectiveDate || "";

  renderGraph();
  setStatus(graphStatus(state.graph));

  // Now apply the saved graph layout (zoom, pan, node positions)
  if (state.cy && session.layout) {
    const layout = session.layout;
    if (layout.nodes) {
      layout.nodes.forEach(savedNode => {
        const node = state.cy.getElementById(savedNode.id);
        if (node.length && savedNode.position) {
          node.position(savedNode.position);
        }
      });
    }
    if (typeof layout.zoom === "number") {
      state.cy.zoom(layout.zoom);
    }
    if (layout.pan) {
      state.cy.pan(layout.pan);
    }
  }

  // Restore Selected Item
  if (state.cy && session.selectedItem) {
    const sel = session.selectedItem;
    if (sel.type === "Rule") {
      state.selectedRule = { id: sel.id, snapshotId: sel.snapshotId };
      lineageTab.disabled = false;
      const node = state.cy.getElementById(sel.id);
      if (node.length) {
        node.select();
        showNodeDetails(node.data());
      }
    } else if (sel.type === "Edge") {
      const edge = state.cy.getElementById(sel.id);
      if (edge.length) {
        edge.select();
        showEdgeDetails(sel.data || edge.data());
      }
    } else {
      const node = state.cy.getElementById(sel.id);
      if (node.length) {
        node.select();
        showNodeDetails(node.data());
      }
    }
  }
}

/* AI Features Integration */
let aiConfig = { enabled: false, message: "" };

async function fetchAiConfig() {
  try {
    const res = await fetch("/api/ai/config");
    if (res.ok) {
      aiConfig = await res.json();
    }
  } catch (err) {
    console.error("Failed to fetch AI configuration:", err);
  }
}

async function updateAiDocsPanel() {
  const actionsEl = document.querySelector(".ai-docs-actions");
  const unconfiguredEl = document.getElementById("ai-docs-unconfigured");
  const containerEl = document.getElementById("ai-docs-content-container");
  const statusEl = document.getElementById("ai-docs-status");
  const generateBtn = document.getElementById("generate-ai-docs-button");

  if (!actionsEl || !unconfiguredEl) return;

  if (aiConfig.enabled) {
    unconfiguredEl.hidden = true;
    unconfiguredEl.style.display = "none";
    actionsEl.style.display = "flex";
    if (!state.graph || !state.graph.nodes || state.graph.nodes.length === 0) {
      if (generateBtn) generateBtn.disabled = true;
      if (statusEl) statusEl.textContent = "Generate a graph first to enable documentation.";
    } else {
      if (generateBtn) generateBtn.disabled = false;
      if (statusEl) statusEl.textContent = "Ready to generate full system documentation.";
    }
  } else {
    unconfiguredEl.hidden = false;
    unconfiguredEl.style.display = "block";
    unconfiguredEl.textContent = aiConfig.message || "AI features are unconfigured or disabled on this workstation.";
    actionsEl.style.display = "none";
    if (containerEl) containerEl.hidden = true;
  }
}

let docDownloadUrl = "";

async function handleGenerateAiDocs() {
  const textEl = document.getElementById("ai-docs-text");
  const metadataEl = document.getElementById("ai-docs-metadata");
  const containerEl = document.getElementById("ai-docs-content-container");
  const generateBtn = document.getElementById("generate-ai-docs-button");
  const downloadLink = document.getElementById("download-ai-docs");
  const statusEl = document.getElementById("ai-docs-status");

  generateBtn.disabled = true;
  if (statusEl) statusEl.textContent = "Generating local AI documentation...";
  if (containerEl) containerEl.hidden = false;
  if (textEl) textEl.innerHTML = '<p class="empty-summary">Running local model to generate comprehensive documentation...</p>';
  if (metadataEl) metadataEl.innerHTML = "";
  if (downloadLink) downloadLink.hidden = true;

  try {
    const response = await fetch("/api/ai/documentation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.graph || {})
    });
    const payload = await response.json();
    if (!response.ok) {
      if (textEl) textEl.innerHTML = `<p class="empty-summary" style="color:var(--error);">${escapeHtml(payload.error || "AI documentation generation failed.")}</p>`;
      if (statusEl) statusEl.textContent = "Generation failed.";
      return;
    }

    if (statusEl) statusEl.textContent = "Generated successfully.";
    if (textEl) textEl.innerHTML = formatMarkdown(payload.text);
    if (metadataEl) {
      metadataEl.innerHTML = `
        <div class="ai-disclaimer">${escapeHtml(payload.disclaimer)}</div>
        Model: ${escapeHtml(payload.model)} | Provider: ${escapeHtml(payload.provider)}<br>
        Generated at: ${escapeHtml(new Date(payload.timestamp).toLocaleString())}
      `;
    }

    if (docDownloadUrl) {
      URL.revokeObjectURL(docDownloadUrl);
    }
    docDownloadUrl = URL.createObjectURL(
      new Blob([payload.text], { type: "text/markdown" })
    );
    if (downloadLink) {
      downloadLink.href = docDownloadUrl;
      downloadLink.hidden = false;
    }
  } catch (err) {
    if (textEl) textEl.innerHTML = `<p class="empty-summary" style="color:var(--error);">Network or connection failure: ${escapeHtml(err.message)}</p>`;
    if (statusEl) statusEl.textContent = "Network failure.";
  } finally {
    generateBtn.disabled = false;
  }
}

function formatMarkdown(text) {
  if (!text) return "";
  let formatted = escapeHtml(text);

  formatted = formatted.replace(/^### (.*?)$/gm, "<h3>$1</h3>");
  formatted = formatted.replace(/^## (.*?)$/gm, "<h2>$1</h2>");
  formatted = formatted.replace(/^# (.*?)$/gm, "<h1>$1</h1>");

  formatted = formatted.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  formatted = formatted.replace(/`(.*?)`/g, "<code>$1</code>");
  formatted = formatted.replace(/^- (.*?)$/gm, "<li>$1</li>");
  formatted = formatted.replace(/(<li>.*?<\/li>)+/gs, "<ul>$&</ul>");

  const blocks = formatted.split(/\n\n+/);
  formatted = blocks.map(block => {
    block = block.trim();
    if (!block) return "";
    if (block.startsWith("<h") || block.startsWith("<ul") || block.startsWith("<li")) {
      return block;
    }
    return `<p>${block.replace(/\n/g, "<br>")}</p>`;
  }).join("\n");

  return formatted;
}

// Initial AI triggers
fetchAiConfig().then(() => {
  updateAiSummaryPanel();
  updateAiDocsPanel();
});
fetchAiStatus();

document.getElementById("generate-summary-button")?.addEventListener("click", handleGenerateSummaryClick);
document.getElementById("generate-ai-summary-button")?.addEventListener("click", handleGenerateSummaryClick);
document.getElementById("generate-ai-docs-button")?.addEventListener("click", handleGenerateAiDocs);

// --- Compare XML Feature ---
const compareBaselineInput = document.getElementById("compare-baseline-file");
const compareCandidateInput = document.getElementById("compare-candidate-file");
const compareButton = document.getElementById("compare-button");
const compareStatusEl = document.getElementById("compare-status");
const compareErrorEl = document.getElementById("compare-error");
const compareResultsContainer = document.getElementById("compare-results-container");
const compareCountAdded = document.getElementById("compare-count-added");
const compareCountRemoved = document.getElementById("compare-count-removed");
const compareCountChanged = document.getElementById("compare-count-changed");
const compareCountUnchanged = document.getElementById("compare-count-unchanged");
const compareTypeFilter = document.getElementById("compare-type-filter");
const compareCategoryFilter = document.getElementById("compare-category-filter");
const compareSearchInput = document.getElementById("compare-search");
const compareAsOfDateInput = document.getElementById("compare-as-of-date");
const compareClearFiltersButton = document.getElementById("compare-clear-filters");
const compareItemsList = document.getElementById("compare-items-list");
const compareSummaryCards = document.querySelectorAll(".compare-card");

async function runComparison() {
  if (!compareBaselineInput || !compareCandidateInput) return;
  const bFiles = compareBaselineInput.files;
  const cFiles = compareCandidateInput.files;

  if (!bFiles || bFiles.length === 0 || !cFiles || cFiles.length === 0) {
    if (compareErrorEl) {
      compareErrorEl.textContent = "Please select both a baseline and a candidate XML file to compare.";
      compareErrorEl.hidden = false;
    }
    if (compareStatusEl) {
      compareStatusEl.textContent = "Comparison requires two selected XML files.";
    }
    return;
  }

  const baselineFile = bFiles[0];
  const candidateFile = cFiles[0];

  const formData = new FormData();
  formData.append("baseline_file", baselineFile);
  formData.append("candidate_file", candidateFile);
  formData.append("topology_mode", "full");
  const asOfDate = compareAsOfDateInput ? compareAsOfDateInput.value.trim() : "";
  if (asOfDate) {
    formData.append("as_of_date", asOfDate);
  }

  if (compareStatusEl) compareStatusEl.textContent = `Comparing "${baselineFile.name}" and "${candidateFile.name}"...`;
  if (compareButton) compareButton.disabled = true;

  try {
    const response = await fetch("/api/compare", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({ error: `Server error (${response.status})` }));
      const msg = errData.error || errData.detail || "Comparison failed. Please verify your XML export files.";
      if (compareErrorEl) {
        compareErrorEl.textContent = msg;
        compareErrorEl.hidden = false;
      }
      if (compareStatusEl) {
        compareStatusEl.textContent = "Comparison failed.";
      }
      // Note: we preserve existing comparisonResult and compareResultsContainer without overwriting!
      return;
    }

    const result = await response.json();
    state.comparisonResult = result;
    state.compareActiveCategory = "all";

    if (compareErrorEl) {
      compareErrorEl.hidden = true;
      compareErrorEl.textContent = "";
    }
    if (compareStatusEl) {
      compareStatusEl.textContent = `Comparison complete: ${result.summary.totalAdded} added, ${result.summary.totalRemoved} removed, ${result.summary.totalChanged} changed, ${result.summary.totalUnchanged} unchanged.`;
    }

    renderComparisonResults();
  } catch (err) {
    if (compareErrorEl) {
      compareErrorEl.textContent = `Network or comparison error: ${err.message}`;
      compareErrorEl.hidden = false;
    }
    if (compareStatusEl) {
      compareStatusEl.textContent = "Comparison failed.";
    }
  } finally {
    if (compareButton) compareButton.disabled = false;
  }
}

function renderComparisonResults() {
  if (!state.comparisonResult || !compareResultsContainer) return;
  compareResultsContainer.hidden = false;

  if (state.comparisonResult.asOfDate && compareAsOfDateInput && !compareAsOfDateInput.value) {
    compareAsOfDateInput.value = state.comparisonResult.asOfDate;
  }

  const summary = state.comparisonResult.summary;
  if (compareCountAdded) compareCountAdded.textContent = summary.totalAdded;
  if (compareCountRemoved) compareCountRemoved.textContent = summary.totalRemoved;
  if (compareCountChanged) compareCountChanged.textContent = summary.totalChanged;
  if (compareCountUnchanged) compareCountUnchanged.textContent = summary.totalUnchanged;

  // Populate type filter
  if (compareTypeFilter) {
    const currentVal = compareTypeFilter.value;
    const types = new Set();
    state.comparisonResult.added.forEach((item) => types.add(item.type));
    state.comparisonResult.removed.forEach((item) => types.add(item.type));
    state.comparisonResult.changed.forEach((item) => types.add(item.type));
    state.comparisonResult.unchanged.forEach((item) => types.add(item.type));

    const sortedTypes = Array.from(types).sort();
    compareTypeFilter.innerHTML = '<option value="">All types</option>';
    sortedTypes.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      compareTypeFilter.appendChild(opt);
    });
    if (types.has(currentVal)) {
      compareTypeFilter.value = currentVal;
    }
  }

  updateComparisonCardHighlights();
  renderComparisonItems();
}

function updateComparisonCardHighlights() {
  compareSummaryCards.forEach((card) => {
    if (card.dataset.filter === state.compareActiveCategory) {
      card.classList.add("active");
    } else {
      card.classList.remove("active");
    }
  });
}

function renderComparisonItems() {
  if (!state.comparisonResult || !compareItemsList) return;

  const category = state.compareActiveCategory || "all";
  const selectedType = compareTypeFilter ? compareTypeFilter.value : "";
  const searchTerm = compareSearchInput ? (compareSearchInput.value || "").trim().toLowerCase() : "";
  const asOfDate = (compareAsOfDateInput && compareAsOfDateInput.value ? compareAsOfDateInput.value.trim() : "") || (state.comparisonResult && state.comparisonResult.asOfDate ? state.comparisonResult.asOfDate : "");

  const allItems = [];
  state.comparisonResult.changed.forEach((item) => allItems.push({ ...item, category: "changed" }));
  state.comparisonResult.added.forEach((item) => allItems.push({ ...item, category: "added" }));
  state.comparisonResult.removed.forEach((item) => allItems.push({ ...item, category: "removed" }));
  state.comparisonResult.unchanged.forEach((item) => allItems.push({ ...item, category: "unchanged" }));

  const filtered = allItems.filter((item) => {
    if (category !== "all" && item.category !== category) return false;
    if (selectedType && item.type !== selectedType) return false;
    if (searchTerm) {
      const labelMatch = item.label && item.label.toLowerCase().includes(searchTerm);
      const summaryMatch = item.summary && item.summary.toLowerCase().includes(searchTerm);
      if (!labelMatch && !summaryMatch) return false;
    }
    if (compareAsOfDateInput && compareAsOfDateInput.value.trim()) {
      const temporal = computeTemporalStatus(item, compareAsOfDateInput.value.trim());
      if (temporal.status !== "active" && temporal.status !== "undated") return false;
    }
    return true;
  });

  let asOfBannerHtml = "";
  if (asOfDate) {
    asOfBannerHtml = `<div class="compare-as-of-banner"><strong>As-of Date:</strong> ${escapeHtml(asOfDate)}</div>`;
  }

  if (filtered.length === 0) {
    compareItemsList.innerHTML = `${asOfBannerHtml}<p class="empty-summary" style="padding: 12px 0;">No configuration objects match the selected filters.</p>`;
    return;
  }

  const html = filtered.map((item) => {
    const badgeClass = item.category;
    const badgeText = item.category.toUpperCase();
    const temporal = asOfDate ? computeTemporalStatus(item, asOfDate) : null;
    const temporalBadgeHtml = temporal
      ? `<span class="temporal-badge ${escapeHtml(temporal.status)}">${escapeHtml(temporal.label)}</span>`
      : "";

    let detailsHtml = "";
    if (item.category === "changed" && item.differences && item.differences.length > 0) {
      const diffEntries = item.differences
        .map((d) => `<li class="compare-diff-entry">${escapeHtml(d.description)}</li>`)
        .join("");
      detailsHtml = `
        <div class="compare-diff-details">
          <ul class="compare-diff-list">${diffEntries}</ul>
        </div>
      `;
    }

    let summaryText = "";
    if (item.category === "changed") {
      summaryText = item.summary || "Configuration differences detected.";
    } else if (item.category === "added") {
      summaryText = `Added in candidate configuration "${escapeHtml(state.comparisonResult.candidateFile)}".`;
    } else if (item.category === "removed") {
      summaryText = `Removed from baseline configuration "${escapeHtml(state.comparisonResult.baselineFile)}".`;
    } else {
      summaryText = "Identical in both configurations.";
    }

    return `
      <div class="compare-item-card item-${badgeClass}">
        <div class="compare-item-header">
          <div class="compare-item-title">
            <span class="compare-badge ${badgeClass}">${badgeText}</span>
            <span>${escapeHtml(item.type)}: ${escapeHtml(item.label)}</span>
          </div>
          ${temporalBadgeHtml}
        </div>
        <div class="compare-item-summary">${escapeHtml(summaryText)}</div>
        ${detailsHtml}
      </div>
    `;
  }).join("");

  compareItemsList.innerHTML = asOfBannerHtml + html;
}

if (compareButton) compareButton.addEventListener("click", runComparison);
if (compareCategoryFilter) {
  compareCategoryFilter.addEventListener("change", () => {
    state.compareActiveCategory = compareCategoryFilter.value;
    updateComparisonCardHighlights();
    renderComparisonItems();
  });
}
if (compareTypeFilter) {
  compareTypeFilter.addEventListener("change", renderComparisonItems);
}
if (compareSearchInput) {
  compareSearchInput.addEventListener("input", renderComparisonItems);
}
if (compareAsOfDateInput) {
  compareAsOfDateInput.addEventListener("input", renderComparisonItems);
}
if (compareClearFiltersButton) {
  compareClearFiltersButton.addEventListener("click", () => {
    if (compareTypeFilter) compareTypeFilter.value = "";
    if (compareCategoryFilter) compareCategoryFilter.value = "all";
    if (compareSearchInput) compareSearchInput.value = "";
    if (compareAsOfDateInput) compareAsOfDateInput.value = "";
    state.compareActiveCategory = "all";
    updateComparisonCardHighlights();
    renderComparisonItems();
  });
}
compareSummaryCards.forEach((card) => {
  const handler = () => {
    const filter = card.dataset.filter;
    if (state.compareActiveCategory === filter) {
      state.compareActiveCategory = "all";
      if (compareCategoryFilter) compareCategoryFilter.value = "all";
    } else {
      state.compareActiveCategory = filter;
      if (compareCategoryFilter) compareCategoryFilter.value = filter;
    }
    updateComparisonCardHighlights();
    renderComparisonItems();
  };
  card.addEventListener("click", handler);
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handler();
    }
  });
});

