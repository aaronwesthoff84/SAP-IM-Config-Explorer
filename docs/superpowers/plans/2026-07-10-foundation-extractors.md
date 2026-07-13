# Foundation and Object-Specific Extractors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace generic graph extraction with a reproducible, snapshot-aware, allowlist-enforced object extraction and reference-resolution foundation that completes GitHub issues #1-#5 while preserving the legacy SAP Incentive Management XML-to-HTML converter.

**Architecture:** A versioned graph contract separates snapshot identity, canonical object identity, and instance identity. Dedicated extractors produce object/reference candidates through a shared registry and node factory; a document-aware resolver turns unique references into real-node links and missing or ambiguous references into structured findings.

**Tech Stack:** Python 3.14, FastAPI 0.139.0, Pydantic 2.13.4 with pydantic-core 2.46.4, ElementTree, dataclasses, pytest 9.1.1, plain JavaScript.

## Global Constraints

- Preserve `python sap_im_transformer.py input.xml [output.html] [--variant=A|B]` and the browser HTML-generation workflow.
- Do not require cloud services, runtime CDN assets, React, or a Node build system.
- Only the 17 node types in `NODE_TYPES` may be emitted.
- Formula functions, parameters, conditions, actions, and other object internals remain metadata/reference evidence and never become graph nodes.
- Custom extractors may emit only established allowlisted types.
- All Rule family extractors emit `type="Rule"` plus normalized family/subtype metadata.
- Dependency links point from the dependent object to the object it consumes.
- Containment links point from child to owner.
- Missing and ambiguous references become findings, not links to nonexistent nodes.
- Duplicate scope is one snapshot; matching objects across snapshots are not duplicates.
- Use red-green-refactor for every production behavior change.
- Do not change `sap_im_config_graph_explorer/xml_to_html_converter.py` except for a compatibility fix proven necessary by a failing legacy-converter test.

## File Structure

- `.gitignore`: excludes Python, pytest, virtual-environment, and Superpowers scratch artifacts.
- `requirements.txt`, `requirements-dev.txt`: reproducible runtime/test dependency set.
- `sap_im_config_graph_explorer/models.py`: versioned graph, snapshot, link, and finding contracts.
- `sap_im_config_graph_explorer/object_extractors/base.py`: extractor protocol and candidate records.
- `sap_im_config_graph_explorer/object_extractors/registry.py`: ordered extractor registration and dispatch.
- `sap_im_config_graph_explorer/object_extractors/node_factory.py`: allowlist enforcement, canonical keys, stable instance IDs, duplicate grouping.
- `sap_im_config_graph_explorer/object_extractors/common.py`: label/metadata/reference normalization helpers.
- `sap_im_config_graph_explorer/object_extractors/primary.py`: Fixed Value, Lookup Table, Quota, Rate Table, Territory, Variable.
- `sap_im_config_graph_explorer/object_extractors/auxiliary.py`: Event Type, Credit Type, Earning Code, Earning Group, Business Unit, Processing Unit, Calendar.
- `sap_im_config_graph_explorer/object_extractors/formula.py`: Formula object/expression-input extraction.
- `sap_im_config_graph_explorer/object_extractors/rules.py`: Credit, Measurement, Incentive, Deposit, and fallback Rule extractors.
- `sap_im_config_graph_explorer/object_extractors/plans.py`: Plan and Plan Component extraction/containment references.
- `sap_im_config_graph_explorer/reference_resolver.py`: snapshot-scoped unique/missing/ambiguous resolution.
- `sap_im_config_graph_explorer/graph_builder.py`: orchestrates snapshots, extractors, node factory, and resolver.
- `tests/fixtures/extractor_families.xml`: representative allowlisted objects and dependency references.
- `tests/fixtures/rule_families.xml`: all four Rule families plus unknown Rule subtype behavior.
- `tests/fixtures/reference_resolution.xml`: resolved, missing, ambiguous, and containment cases.
- `tests/test_project_hygiene.py`: dependency/cache reproducibility checks.
- `tests/test_models.py`: versioned contract serialization tests.
- `tests/test_object_extractors.py`: extractor, allowlist, metadata, identity, and duplicate tests.
- `tests/test_reference_resolution.py`: link direction, de-duplication, and finding tests.
- `tests/test_converter_and_graph.py`, `tests/test_app.py`: integration and legacy regression updates.

---

### Task 1: Reproducible Python Environment and Repository Hygiene

**Files:**
- Create: `.gitignore`
- Create: `tests/test_project_hygiene.py`
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Remove from Git: every tracked `__pycache__/*.pyc` and `tests/__pycache__/*.pyc`

**Interfaces:**
- Consumes: current Python 3.14 environment and repository root.
- Produces: `.venv/Scripts/python.exe` using an internally compatible FastAPI/Pydantic stack and a cache-clean Git index.

- [ ] **Step 1: Write the failing hygiene tests**

```python
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def _nonblank(path: str) -> list[str]:
    return [
        line.strip()
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_dependency_versions_are_reproducible():
    assert _nonblank("requirements.txt") == [
        "fastapi==0.139.0",
        "pydantic==2.13.4",
        "pydantic-core==2.46.4",
        "python-multipart==0.0.32",
        "starlette==1.3.1",
        "uvicorn==0.51.0",
    ]
    assert _nonblank("requirements-dev.txt") == [
        "-r requirements.txt",
        "httpx==0.28.1",
        "pytest==9.1.1",
    ]


def test_python_cache_files_are_ignored_and_untracked():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout.splitlines()
    assert not [path for path in tracked if "__pycache__" in path or path.endswith(".pyc")]
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"__pycache__/", "*.py[cod]", ".pytest_cache/", ".venv/", ".superpowers/"} <= set(ignored)
```

- [ ] **Step 2: Run the targeted tests and verify RED**

Run: `python -m pytest tests/test_project_hygiene.py -q -p no:cacheprovider`

Expected: FAIL because dependencies are unpinned, `.gitignore` is absent, and tracked bytecode exists.

- [ ] **Step 3: Add exact dependency and ignore configuration**

Write `requirements.txt` exactly as:

```text
fastapi==0.139.0
pydantic==2.13.4
pydantic-core==2.46.4
python-multipart==0.0.32
starlette==1.3.1
uvicorn==0.51.0
```

Write `requirements-dev.txt` exactly as:

```text
-r requirements.txt
httpx==0.28.1
pytest==9.1.1
```

Write `.gitignore` exactly as:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
.superpowers/
```

Remove tracked bytecode with `git rm --cached` for the paths returned by `git ls-files` containing `__pycache__` or ending in `.pyc`; do not delete source or fixture files.

- [ ] **Step 4: Build the isolated environment and verify GREEN**

Run:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest tests\test_project_hygiene.py -q -p no:cacheprovider
```

Expected: dependency installation succeeds and `2 passed`.

- [ ] **Step 5: Run the existing baseline suite in the clean environment**

Run: `.\.venv\Scripts\python -m pytest -q -p no:cacheprovider`

Expected: the existing 14-test baseline passes before contract changes begin.

- [ ] **Step 6: Commit the hygiene slice**

```powershell
git add .gitignore requirements.txt requirements-dev.txt tests/test_project_hygiene.py
git add -u
git commit -m "build: make Python environment reproducible"
```

---

### Task 2: Versioned Snapshot-Aware Graph Contract

**Files:**
- Create: `tests/test_models.py`
- Modify: `sap_im_config_graph_explorer/models.py`
- Modify: `tests/test_converter_and_graph.py`

**Interfaces:**
- Consumes: existing `NODE_TYPES`, `RELATIONSHIP_TYPES`, `GraphNode`, `GraphLink`, `GraphDocument`.
- Produces: `GRAPH_SCHEMA_VERSION`, `Snapshot`, `ValidationFinding`, expanded `GraphNode`/`GraphLink`, and `GraphDocument(schemaVersion, snapshots, nodes, links, findings)`.

- [ ] **Step 1: Write the failing contract serialization test**

```python
from sap_im_config_graph_explorer.models import (
    GRAPH_SCHEMA_VERSION,
    GraphDocument,
    GraphLink,
    GraphNode,
    Snapshot,
    ValidationFinding,
)


def test_versioned_graph_contract_serializes_snapshot_identity_and_findings():
    snapshot = Snapshot(id="non-prod", role="non_production", sourceFiles=["np.xml"])
    node = GraphNode(
        id="node-1",
        canonicalKey="formula:eligibility",
        snapshotId="non-prod",
        label="Eligibility",
        type="Formula",
        sourceFile="np.xml",
        xmlPath="/DATA_IMPORT[1]/FORMULA_SET[1]/FORMULA[1]",
        rawXml='<FORMULA NAME="Eligibility" />',
    )
    link = GraphLink(
        id="link-1",
        source="node-1",
        target="node-2",
        relationship="uses_variable",
        confidence="high",
    )
    finding = ValidationFinding(
        id="finding-1",
        code="missing_reference",
        severity="error",
        snapshotId="non-prod",
        nodeIds=("node-1",),
        message="Missing variable Gate",
        details={"reference": "Gate"},
    )

    payload = GraphDocument(
        snapshots=[snapshot], nodes=[node], links=[link], findings=[finding]
    ).to_dict()

    assert payload["schemaVersion"] == GRAPH_SCHEMA_VERSION == "1.0"
    assert payload["snapshots"][0]["role"] == "non_production"
    assert payload["nodes"][0]["canonicalKey"] == "formula:eligibility"
    assert payload["links"][0]["id"] == "link-1"
    assert payload["findings"][0]["code"] == "missing_reference"
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests\test_models.py -q -p no:cacheprovider`

Expected: FAIL importing `GRAPH_SCHEMA_VERSION`, `Snapshot`, and `ValidationFinding`.

- [ ] **Step 3: Implement the complete model contract**

Add these public contracts to `models.py` and update every `to_dict()` to include exactly these fields:

```python
GRAPH_SCHEMA_VERSION = "1.0"
SNAPSHOT_ROLES = {"configuration", "non_production", "production"}
FINDING_SEVERITIES = {"error", "warning", "info"}

# Task 7 removes legacy relationships that cannot survive the
# object-specific resolver migration.
RELATIONSHIP_TYPES = {
    "uses_fixed_value", "uses_formula", "uses_lookup", "uses_quota",
    "uses_rate_table", "uses_classifier", "uses_territory", "uses_variable",
    "uses_rule", "belongs_to_plan", "belongs_to_plan_component",
    "runs_in_pipeline", "uses_event_type", "outputs_credit_type",
    "uses_earning_code", "uses_earning_group", "uses_business_unit",
    "uses_processing_unit", "uses_calendar", "feeds_deposit",
    "depends_on_period", "references_custom_object", "references_report",
    "references_integration", "parent_child", "unknown_reference",
}


@dataclass(frozen=True)
class Snapshot:
    id: str
    role: str
    sourceFiles: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.role not in SNAPSHOT_ROLES:
            raise ValueError(f"Unsupported snapshot role: {self.role}")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "role": self.role, "sourceFiles": self.sourceFiles}


@dataclass
class GraphNode:
    id: str
    label: str
    type: str
    sourceFile: str
    xmlPath: str
    rawXml: str
    canonicalKey: str = ""
    snapshotId: str = "configuration"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in NODE_TYPES:
            raise ValueError(f"Unsupported graph node type: {self.type}")


@dataclass(frozen=True)
class GraphLink:
    source: str
    target: str
    relationship: str
    confidence: str
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        if self.relationship not in RELATIONSHIP_TYPES:
            raise ValueError(f"Unsupported graph relationship: {self.relationship}")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"Unsupported confidence level: {self.confidence}")


@dataclass(frozen=True)
class ValidationFinding:
    id: str
    code: str
    severity: str
    snapshotId: str
    nodeIds: tuple[str, ...]
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in FINDING_SEVERITIES:
            raise ValueError(f"Unsupported finding severity: {self.severity}")


@dataclass
class GraphDocument:
    snapshots: list[Snapshot] = field(default_factory=list)
    nodes: list[GraphNode] = field(default_factory=list)
    links: list[GraphLink] = field(default_factory=list)
    findings: list[ValidationFinding] = field(default_factory=list)
    schemaVersion: str = GRAPH_SCHEMA_VERSION
```

`GraphNode.to_dict()` must emit `id`, `canonicalKey`, `snapshotId`, `label`, `type`, `sourceFile`, `xmlPath`, `rawXml`, `metadata`. `GraphLink.to_dict()` must emit `id`, `source`, `target`, `relationship`, `confidence`, `metadata`. `ValidationFinding.to_dict()` must emit all seven fields and convert `nodeIds` to a JSON list. `GraphDocument.to_dict()` must emit `schemaVersion`, `snapshots`, `nodes`, `links`, `findings`.

The empty `canonicalKey`/link `id` and default `snapshotId` preserve existing GenericObjectExtractor/ReferenceResolver call sites only until Task 7. Update `test_exported_graph_json_matches_expected_schema` now to assert the five top-level graph keys, the nine node keys, and the six link keys. Task 7 replaces every temporary default with real values before Phase 1 acceptance.

- [ ] **Step 4: Run model tests and verify GREEN**

Run: `.\.venv\Scripts\python -m pytest tests\test_models.py -q -p no:cacheprovider`

Expected: `1 passed`.

- [ ] **Step 5: Verify the complete suite remains GREEN during migration**

Run: `.\.venv\Scripts\python -m pytest -q -p no:cacheprovider`

Expected: all tests pass; the known Starlette deprecation warning may remain recorded as a pre-existing Minor finding.

- [ ] **Step 6: Commit the contract**

```powershell
git add sap_im_config_graph_explorer/models.py tests/test_models.py tests/test_converter_and_graph.py
git commit -m "feat: version the graph data contract"
```

---

### Task 3: Extractor Protocol, Registry, and Shared Node Factory

**Files:**
- Create: `sap_im_config_graph_explorer/object_extractors/base.py`
- Create: `sap_im_config_graph_explorer/object_extractors/registry.py`
- Create: `sap_im_config_graph_explorer/object_extractors/node_factory.py`
- Create: `sap_im_config_graph_explorer/object_extractors/common.py`
- Create: `tests/test_object_extractors.py`
- Modify: `sap_im_config_graph_explorer/object_extractors/__init__.py`

**Interfaces:**
- Consumes: `XmlDocument`, `GraphNode`, `NODE_TYPES`.
- Produces: `ExtractionContext`, `ObjectCandidate`, `ReferenceCandidate`, `ExtractionBatch`, `ObjectExtractor`, `ExtractorRegistry`, `NodeFactory`.

- [ ] **Step 1: Write failing registry, allowlist, identity, and duplicate tests**

```python
from dataclasses import dataclass
from xml.etree import ElementTree as ET

import pytest

from sap_im_config_graph_explorer.object_extractors.base import (
    ExtractionBatch,
    ExtractionContext,
    ObjectCandidate,
)
from sap_im_config_graph_explorer.object_extractors.node_factory import NodeFactory
from sap_im_config_graph_explorer.object_extractors.registry import ExtractorRegistry
from sap_im_config_graph_explorer.xml_loader import load_xml_text


@dataclass
class FormulaTestExtractor:
    def matches(self, element: ET.Element) -> bool:
        return element.tag.upper() == "FORMULA"

    def extract(self, element: ET.Element, context: ExtractionContext) -> ExtractionBatch:
        return ExtractionBatch(objects=[ObjectCandidate(element, "Formula", element.get("NAME", ""))])


def test_registry_dispatches_and_node_factory_enforces_allowlist_and_identity():
    document = load_xml_text(
        '<DATA_IMPORT><FORMULA ID="F-1" NAME="Gate" /></DATA_IMPORT>', "one.xml"
    )
    context = ExtractionContext("non-prod", "non_production", document)
    batch = ExtractorRegistry([FormulaTestExtractor()]).extract(context)
    nodes = NodeFactory().build(batch.objects, context)
    assert len(nodes) == 1
    assert nodes[0].canonicalKey == "formula:f-1"
    assert nodes[0].snapshotId == "non-prod"

    unsupported = ObjectCandidate(document.root, "CustomObject", "Custom")
    with pytest.raises(ValueError, match="Unsupported graph node type"):
        NodeFactory().build([unsupported], context)


def test_duplicate_group_marks_every_member_and_is_snapshot_scoped():
    document = load_xml_text(
        '<DATA_IMPORT><FORMULA ID="DUP" NAME="A"/><FORMULA ID="DUP" NAME="B"/></DATA_IMPORT>',
        "dupes.xml",
    )
    context = ExtractionContext("configuration", "configuration", document)
    batch = ExtractorRegistry([FormulaTestExtractor()]).extract(context)
    nodes = NodeFactory().build(batch.objects, context)
    assert len({node.id for node in nodes}) == 2
    assert {node.metadata["duplicateKey"] for node in nodes} == {"formula:dup"}
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests\test_object_extractors.py -q -p no:cacheprovider`

Expected: FAIL because the extractor framework modules do not exist.

- [ ] **Step 3: Implement candidate records and protocol**

Implement `base.py` with these exact public shapes:

```python
@dataclass(frozen=True)
class ExtractionContext:
    snapshot_id: str
    snapshot_role: str
    document: XmlDocument


@dataclass(frozen=True)
class ObjectCandidate:
    element: ET.Element
    node_type: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)
    identity_scope: str = ""


@dataclass(frozen=True)
class ReferenceCandidate:
    source_element: ET.Element
    value: str
    hint: str
    origin: str
    expected_type: str | None = None
    relationship: str | None = None
    reverse: bool = False


@dataclass
class ExtractionBatch:
    objects: list[ObjectCandidate] = field(default_factory=list)
    references: list[ReferenceCandidate] = field(default_factory=list)


class ObjectExtractor(Protocol):
    def matches(self, element: ET.Element) -> bool: ...
    def extract(self, element: ET.Element, context: ExtractionContext) -> ExtractionBatch: ...
```

- [ ] **Step 4: Implement ordered registry dispatch**

`ExtractorRegistry.extract(context)` iterates `context.document.root.iter()`, chooses the first registered extractor whose `matches()` returns true, merges its objects/references, and never creates a fallback object for unmatched XML. `register(extractor, prepend=False)` supports application-owned custom extractors while preserving deterministic order.

- [ ] **Step 5: Implement shared node construction**

`NodeFactory.build(candidates, context)` must:

1. Reject `candidate.node_type` outside `NODE_TYPES`.
2. Use `ID`, `OBJECT_ID`, then normalized label for canonical identity.
3. Normalize each identity segment independently, preserve colon separators, and build `canonicalKey` as lowercase `<type>:<identity_scope>:<identity>` with the empty scope omitted; `Formula` with source ID `F-1` must become `formula:f-1`.
4. Build stable instance IDs from snapshot ID, source file, canonical key, XML path, and deterministic occurrence.
5. Copy normalized metadata plus original tag, attributes, optional `sourceId`, and bounded raw XML.
6. Group by `(snapshotId, canonicalKey)` and set the same `duplicateKey` on every member of groups larger than one.

The factory retains identity counts and `node_id_by_element` across all documents in one build. `reset()` starts a graph build, `build()` may be called once per document, and `finalize(nodes)` marks every member of cross-file duplicate groups before resolution.

Expose `normalize_identity(value: str) -> str`, `infer_label(element) -> str`, `normalized_dates(element) -> dict[str, str]`, and `trim_raw_xml(element, limit=4000) -> str` from `common.py`.

- [ ] **Step 6: Run extractor-framework tests and verify GREEN**

Run: `.\.venv\Scripts\python -m pytest tests\test_object_extractors.py -q -p no:cacheprovider`

Expected: `2 passed`.

- [ ] **Step 7: Commit the framework**

```powershell
git add sap_im_config_graph_explorer/object_extractors tests/test_object_extractors.py
git commit -m "feat: add allowlisted extractor framework"
```

---

### Task 4: Primary and Auxiliary Object Extractors

**Files:**
- Create: `sap_im_config_graph_explorer/object_extractors/primary.py`
- Create: `sap_im_config_graph_explorer/object_extractors/auxiliary.py`
- Create: `tests/fixtures/extractor_families.xml`
- Modify: `tests/test_object_extractors.py`

**Interfaces:**
- Consumes: extractor protocol, `normalized_dates`, `infer_label`.
- Produces: `PRIMARY_EXTRACTORS`, `AUXILIARY_EXTRACTORS`; allowlisted candidates for 13 non-Rule/Plan/Formula categories.

- [ ] **Step 1: Add a representative fixture and failing parameterized test**

Create `extractor_families.xml` exactly as:

```xml
<DATA_IMPORT>
  <FIXED_VALUE_SET><FIXED_VALUE ID="FV-1" NAME="Fixed" EFFECTIVE_START_DATE="2026-01-01"/></FIXED_VALUE_SET>
  <MD_LOOKUP_TABLE_SET><MD_LOOKUP_TABLE ID="LT-1" NAME="Lookup"/></MD_LOOKUP_TABLE_SET>
  <QUOTA_SET><QUOTA ID="Q-1" NAME="Quota"/></QUOTA_SET>
  <RATE_TABLE_SET><RATE_TABLE ID="RT-1" NAME="Rate"/></RATE_TABLE_SET>
  <TERRITORY_SET><TERRITORY ID="T-1" NAME="Territory"/></TERRITORY_SET>
  <VARIABLE_SET><VARIABLE ID="V-1" NAME="Variable"/></VARIABLE_SET>
  <EVENT_TYPE_SET><EVENT_TYPE ID="EV-1" NAME="Event"/></EVENT_TYPE_SET>
  <CREDIT_TYPE_SET><CREDIT_TYPE ID="CR-1" NAME="Credit"/></CREDIT_TYPE_SET>
  <EARNING_CODE_SET><EARNING_CODE ID="EC-1" NAME="Earning Code"/></EARNING_CODE_SET>
  <EARNING_GROUP_SET><EARNING_GROUP ID="EG-1" NAME="Earning Group"/></EARNING_GROUP_SET>
  <BUSINESS_UNIT_SET><BUSINESS_UNIT ID="BU-1" NAME="Business"/></BUSINESS_UNIT_SET>
  <PROCESSING_UNIT_SET><PROCESSING_UNIT ID="PU-1" NAME="Processing"/></PROCESSING_UNIT_SET>
  <CALENDAR_SET><CALENDAR ID="CAL-1" NAME="Calendar"/></CALENDAR_SET>
</DATA_IMPORT>
```

Use this exact expected mapping:

```python
EXPECTED = {
    "Fixed": "FixedValue",
    "Lookup": "LookupTable",
    "Quota": "Quota",
    "Rate": "RateTable",
    "Territory": "Territory",
    "Variable": "Variable",
    "Event": "EventType",
    "Credit": "CreditType",
    "Earning Code": "EarningCode",
    "Earning Group": "EarningGroup",
    "Business": "BusinessUnit",
    "Processing": "ProcessingUnit",
    "Calendar": "Calendar",
}


def test_primary_and_auxiliary_extractors_emit_expected_allowlisted_types():
    document = load_xml_file(FIXTURES / "extractor_families.xml")
    context = ExtractionContext("configuration", "configuration", document)
    batch = ExtractorRegistry(PRIMARY_EXTRACTORS + AUXILIARY_EXTRACTORS).extract(context)
    nodes = NodeFactory().build(batch.objects, context)
    assert {node.label: node.type for node in nodes} == EXPECTED
    assert all(node.metadata.get("tag") for node in nodes)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests\test_object_extractors.py::test_primary_and_auxiliary_extractors_emit_expected_allowlisted_types -q -p no:cacheprovider`

Expected: FAIL importing the primary and auxiliary extractor collections.

- [ ] **Step 3: Implement exact tag families**

`primary.py` must recognize these aliases:

```python
PRIMARY_TAG_TYPES = {
    "FIXED_VALUE": "FixedValue",
    "MDLT": "LookupTable",
    "MD_LOOKUP_TABLE": "LookupTable",
    "LOOKUP_TABLE": "LookupTable",
    "LOOKUPTABLE": "LookupTable",
    "QUOTA": "Quota",
    "RATE_TABLE": "RateTable",
    "RATETABLE": "RateTable",
    "TERRITORY": "Territory",
    "VARIABLE": "Variable",
}
```

`auxiliary.py` must recognize Event Type, Credit Type, Earning Code, Earning Group, Business Unit, Processing Unit, and Calendar underscore/non-underscore aliases. Text-only definitions are accepted only for these auxiliary definition tags. Reference tags ending in `_REF` never match.

Each emitted candidate includes normalized effective dates and meaningful scalar attributes in metadata; nested expression/action XML is not copied into metadata beyond bounded `rawXml` created by the node factory.

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python -m pytest tests\test_object_extractors.py -q -p no:cacheprovider`

Expected: all extractor tests pass.

- [ ] **Step 5: Commit primary extractors**

```powershell
git add sap_im_config_graph_explorer/object_extractors/primary.py sap_im_config_graph_explorer/object_extractors/auxiliary.py tests
git commit -m "feat: extract primary graph object families"
```

---

### Task 5: Formula and Rule Family Extractors

**Files:**
- Create: `sap_im_config_graph_explorer/object_extractors/formula.py`
- Create: `sap_im_config_graph_explorer/object_extractors/rules.py`
- Create: `tests/fixtures/formula_dependencies.xml`
- Create: `tests/fixtures/rule_families.xml`
- Modify: `tests/test_object_extractors.py`

**Interfaces:**
- Consumes: object/reference candidate contracts and primary target types.
- Produces: `FormulaExtractor`, `CreditRuleExtractor`, `MeasurementRuleExtractor`, `IncentiveRuleExtractor`, `DepositRuleExtractor`, `FallbackRuleExtractor`.

- [ ] **Step 1: Write failing Formula and Rule tests**

Create `formula_dependencies.xml` exactly as:

```xml
<DATA_IMPORT>
  <FORMULA_SET>
    <FORMULA ID="F-1" NAME="Commission Gate" RETURN_TYPE="Boolean">
      <EXPRESSION><FUNCTION ID="ifThenElse"><VARIABLE_REF NAME="Gate"/><FIXED_VALUE_REF NAME="Cap"/></FUNCTION></EXPRESSION>
    </FORMULA>
  </FORMULA_SET>
  <VARIABLE_SET><VARIABLE ID="V-1" NAME="Gate"/></VARIABLE_SET>
  <FIXED_VALUE_SET><FIXED_VALUE ID="FV-1" NAME="Cap"/></FIXED_VALUE_SET>
</DATA_IMPORT>
```

Create `rule_families.xml` exactly as:

```xml
<DATA_IMPORT>
  <RULE_SET>
    <RULE ID="R-1" NAME="Credit Rule" TYPE="DIRECT_TRANSACTION_CREDIT"/>
    <RULE ID="R-2" NAME="Measurement Rule" TYPE="PRIMARY_MEASUREMENT"/>
    <RULE ID="R-3" NAME="Incentive Rule" TYPE="BULK_COMMISSION"/>
    <RULE ID="R-4" NAME="Deposit Rule" TYPE="DETAIL_DEPOSIT"/>
    <RULE ID="R-5" NAME="Other Rule" TYPE="CUSTOM_EXISTING_RULE"/>
  </RULE_SET>
</DATA_IMPORT>
```

```python
def test_formula_extracts_inputs_without_logic_nodes():
    document = load_xml_file(FIXTURES / "formula_dependencies.xml")
    batch = ExtractorRegistry([FormulaExtractor()]).extract(
        ExtractionContext("configuration", "configuration", document)
    )
    assert [candidate.node_type for candidate in batch.objects] == ["Formula"]
    assert {ref.expected_type for ref in batch.references} >= {"Variable", "FixedValue"}
    assert not any(candidate.label in {"ifThenElse", "isNull"} for candidate in batch.objects)


def test_four_rule_extractors_keep_rule_node_type_and_normalize_family():
    document = load_xml_file(FIXTURES / "rule_families.xml")
    batch = ExtractorRegistry(RULE_EXTRACTORS).extract(
        ExtractionContext("configuration", "configuration", document)
    )
    assert {obj.node_type for obj in batch.objects} == {"Rule"}
    assert {obj.metadata["ruleFamily"] for obj in batch.objects} == {
        "credit", "measurement", "incentive", "deposit", "other"
    }
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests\test_object_extractors.py -q -p no:cacheprovider`

Expected: FAIL importing Formula and Rule extractors.

- [ ] **Step 3: Implement shared reference scanning in `common.py`**

Implement `reference_candidates(source_element)` so each semantic reference is emitted once. `_REF`/`COMPONENT_REF` tags use `NAME`, then `ID`, then text and do not re-emit their `NAME` attribute. Other elements emit only recognized `*_NAME`, `*_REF`, and `*_PATH` attributes. Every candidate includes an origin XML subpath/tag and `preferred_type_for_hint(hint)`.

- [ ] **Step 4: Implement Formula extraction**

`FormulaExtractor` matches only `FORMULA`, emits one Formula object with `returnType`, normalized dates, and an ordered unique `expressionTags` list in metadata, and emits input references found below the Formula. It never emits expression children as objects.

- [ ] **Step 5: Implement four Rule family extractors plus fallback**

Use the legacy converter's subtype constants as input knowledge without importing or modifying the converter. Exact normalized families:

```python
CREDIT_TYPES = {"DIRECT_TRANSACTION_CREDIT", "ROLLUP_TRANSACTION_CREDIT"}
MEASUREMENT_TYPES = {"PRIMARY_MEASUREMENT", "SECONDARY_MEASUREMENT"}
INCENTIVE_TYPES = {"BULK_COMMISSION", "COMMISSION"}
DEPOSIT_TYPES = {"DEPOSIT", "DETAIL_DEPOSIT"}
```

Each dedicated class matches `RULE` plus its set. `FallbackRuleExtractor` matches remaining `RULE` elements last and uses `ruleFamily="other"`. Metadata includes `ruleSubtype` from the raw `TYPE`, normalized dates, and description when present. All emit references from their complete Rule subtree.

- [ ] **Step 6: Verify GREEN**

Run: `.\.venv\Scripts\python -m pytest tests\test_object_extractors.py -q -p no:cacheprovider`

Expected: all extractor tests pass with only Formula and Rule objects emitted for their fixtures.

- [ ] **Step 7: Commit Formula and Rule extraction**

```powershell
git add sap_im_config_graph_explorer/object_extractors tests
git commit -m "feat: extract formulas and rule families"
```

---

### Task 6: Plan and Plan Component Extractors

**Files:**
- Create: `sap_im_config_graph_explorer/object_extractors/plans.py`
- Modify: `tests/test_object_extractors.py`
- Modify: `tests/fixtures/minimal_plan.xml` only if an additional authoritative Plan/Component attribute is required.

**Interfaces:**
- Consumes: object/reference candidates and Rule objects.
- Produces: `PlanExtractor`, `PlanComponentExtractor`; reversed containment candidates for `belongs_to_plan` and `belongs_to_plan_component`.

- [ ] **Step 1: Write failing containment-candidate tests**

```python
def test_plan_extractors_emit_child_to_owner_containment_candidates():
    document = load_xml_file(FIXTURES / "minimal_plan.xml")
    batch = ExtractorRegistry([PlanExtractor(), PlanComponentExtractor()]).extract(
        ExtractionContext("configuration", "configuration", document)
    )
    assert {obj.node_type for obj in batch.objects} == {"Plan", "PlanComponent"}
    containment = {(ref.relationship, ref.expected_type, ref.reverse) for ref in batch.references}
    assert ("belongs_to_plan", "PlanComponent", True) in containment
    assert ("belongs_to_plan_component", "Rule", True) in containment
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests\test_object_extractors.py::test_plan_extractors_emit_child_to_owner_containment_candidates -q -p no:cacheprovider`

Expected: FAIL importing Plan extractors.

- [ ] **Step 3: Implement Plan and Plan Component extraction**

`PlanExtractor` matches `PLAN`, emits normalized description/effective-date metadata, and converts each descendant `COMPONENT_REF` into a `ReferenceCandidate` with `expected_type="PlanComponent"`, `relationship="belongs_to_plan"`, `reverse=True`.

`PlanComponentExtractor` matches `PLAN_COMPONENT` and `PLANCOMPONENT`, emits the same normalized metadata fields, and converts each descendant `RULE_REF` into a candidate with `expected_type="Rule"`, `relationship="belongs_to_plan_component"`, `reverse=True`.

The generic reference scanner must not emit duplicates for these explicitly owned containment references.

- [ ] **Step 4: Verify GREEN**

Run: `.\.venv\Scripts\python -m pytest tests\test_object_extractors.py -q -p no:cacheprovider`

Expected: all extractor tests pass.

- [ ] **Step 5: Commit hierarchy extractors**

```powershell
git add sap_im_config_graph_explorer/object_extractors/plans.py tests
git commit -m "feat: extract plan hierarchy"
```

---

### Task 7: Snapshot-Scoped Reference Resolution and GraphBuilder Integration

**Files:**
- Replace: `sap_im_config_graph_explorer/reference_resolver.py`
- Modify: `sap_im_config_graph_explorer/graph_builder.py`
- Modify: `sap_im_config_graph_explorer/object_extractors/__init__.py`
- Create: `tests/fixtures/reference_resolution.xml`
- Create: `tests/test_reference_resolution.py`

**Interfaces:**
- Consumes: nodes, `ReferenceCandidate` values, element-to-node IDs, snapshots.
- Produces: `ResolutionResult(links, findings)`, `SnapshotInput`, and `GraphBuilder.build_snapshots()` with unique real-node links and structured missing/ambiguous findings.

- [ ] **Step 1: Write failing resolver tests**

Create `reference_resolution.xml` exactly as:

```xml
<DATA_IMPORT>
  <FORMULA_SET>
    <FORMULA ID="F-1" NAME="Resolver Formula">
      <EXPRESSION>
        <VARIABLE_REF NAME="Missing"/>
        <VARIABLE_REF NAME="Shared"/>
      </EXPRESSION>
    </FORMULA>
  </FORMULA_SET>
  <VARIABLE_SET>
    <VARIABLE ID="V-1" NAME="Shared"/>
    <VARIABLE ID="V-2" NAME="Shared"/>
  </VARIABLE_SET>
</DATA_IMPORT>
```

```python
def test_resolver_emits_one_real_link_per_reference_and_no_unknown_endpoint():
    graph = GraphBuilder().build_from_paths([FIXTURES / "minimal_plan.xml"])
    node_ids = {node.id for node in graph.nodes}
    assert all(link.source in node_ids and link.target in node_ids for link in graph.links)
    assert len({link.id for link in graph.links}) == len(graph.links)
    assert sum(link.relationship == "uses_formula" for link in graph.links) == 1
    assert sum(link.relationship == "belongs_to_plan" for link in graph.links) == 1


def test_missing_and_ambiguous_references_become_findings_not_links():
    graph = GraphBuilder().build_from_paths([FIXTURES / "reference_resolution.xml"])
    assert {finding.code for finding in graph.findings} == {
        "missing_reference", "ambiguous_reference"
    }
    assert all(not link.target.startswith("unknown:") for link in graph.links)


def test_same_name_in_other_snapshot_is_not_a_resolution_candidate():
    np_xml = b'''<DATA_IMPORT><FORMULA NAME="Uses Gate"><VARIABLE_REF NAME="Gate"/></FORMULA><VARIABLE NAME="Gate"/></DATA_IMPORT>'''
    prod_xml = b'''<DATA_IMPORT><FORMULA NAME="Uses Gate"><VARIABLE_REF NAME="Gate"/></FORMULA><VARIABLE NAME="Gate"/></DATA_IMPORT>'''
    graph = GraphBuilder().build_snapshots([
        SnapshotInput("non-prod", "non_production", [("np.xml", np_xml)]),
        SnapshotInput("prod", "production", [("prod.xml", prod_xml)]),
    ])
    assert all(
        next(node for node in graph.nodes if node.id == link.source).snapshotId
        == next(node for node in graph.nodes if node.id == link.target).snapshotId
        for link in graph.links
    )
```

- [ ] **Step 2: Run resolver tests and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests\test_reference_resolution.py -q -p no:cacheprovider`

Expected: FAIL because current resolver has no candidate input, stable link IDs, findings, or snapshot scope.

- [ ] **Step 3: Implement explicit resolver result and scoped index**

```python
@dataclass
class ResolutionResult:
    links: list[GraphLink] = field(default_factory=list)
    findings: list[ValidationFinding] = field(default_factory=list)
```

Build indexes by `(snapshotId, normalize_identity(label_or_source_id))` and filter by `expected_type`. Resolve only within the source node's snapshot. Zero candidates creates `missing_reference`; multiple candidates creates `ambiguous_reference`; exactly one creates a link.

For `reverse=False`, link source is the reference owner and target is the resolved object. For `reverse=True`, swap them. Use the explicit relationship when present; otherwise call `relationship_for_hint(hint, target_type)`. Explicit Plan Component containment uses `belongs_to_plan_component`; ordinary resolved Rule references use `uses_rule`.

Stable link/finding IDs are lowercase SHA-256 prefixes over snapshot, source, target/reference, relationship/code, and origin. De-duplicate by semantic source/target/relationship/origin after reference scanning has eliminated tag/attribute duplication.

- [ ] **Step 4: Implement snapshot orchestration in GraphBuilder**

Add:

```python
@dataclass(frozen=True)
class SnapshotInput:
    id: str
    role: str
    uploads: list[tuple[str, bytes]]
```

`GraphBuilder.build_from_paths(paths, snapshot_id="configuration", role="configuration")` loads files and delegates to one snapshot context. `build_from_uploads()` does the same for bytes. `build_snapshots(inputs)` accepts multiple snapshot inputs. Each document is extracted by the ordered default registry:

1. Plan
2. Plan Component
3. four Rule families and fallback
4. Formula
5. primary objects
6. auxiliary objects

Call `NodeFactory.reset()` once, build nodes once per document, call `finalize(all_nodes)`, resolve the accumulated reference candidates using the factory's document-aware `node_id_by_element`, and return `GraphDocument` with snapshot metadata and findings.

- [ ] **Step 5: Verify resolver and builder GREEN**

Run: `.\.venv\Scripts\python -m pytest tests\test_reference_resolution.py -q -p no:cacheprovider`

Expected: all resolver tests pass; every link endpoint exists.

- [ ] **Step 6: Commit resolver and builder contract**

```powershell
git add sap_im_config_graph_explorer/reference_resolver.py sap_im_config_graph_explorer/graph_builder.py sap_im_config_graph_explorer/object_extractors tests
git commit -m "feat: resolve snapshot-scoped graph references"
```

---

### Task 8: FastAPI Versioned-Contract Integration

**Files:**
- Modify: `sap_im_config_graph_explorer/app.py`
- Modify: `tests/test_converter_and_graph.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: completed GraphBuilder, Snapshot, and versioned GraphDocument.
- Produces: backward-compatible default graph upload behavior with versioned output.

- [ ] **Step 1: Write failing builder/API integration tests**

Add/update assertions:

```python
def test_graph_builder_returns_versioned_allowlisted_document():
    payload = GraphBuilder().build_from_paths([FIXTURES / "minimal_plan.xml"]).to_dict()
    assert payload["schemaVersion"] == "1.0"
    assert payload["snapshots"] == [{
        "id": "configuration", "role": "configuration", "sourceFiles": ["minimal_plan.xml"]
    }]
    assert all(node["type"] in NODE_TYPES for node in payload["nodes"])
    assert all(not node["label"].startswith("ifThenElse") for node in payload["nodes"])


def test_graph_endpoint_returns_versioned_contract():
    client = TestClient(app)
    xml = (FIXTURES / "minimal_plan.xml").read_bytes()
    response = client.post("/api/graph", files=[("files", ("minimal_plan.xml", xml, "application/xml"))])
    assert response.status_code == 200
    assert set(response.json()) == {"schemaVersion", "snapshots", "nodes", "links", "findings"}
```

- [ ] **Step 2: Run integration tests and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests\test_converter_and_graph.py tests\test_app.py -q -p no:cacheprovider`

Expected: GraphBuilder assertion passes after Task 7; API assertion FAILS because route expectations still use the old document shape.

- [ ] **Step 3: Keep upload API default behavior**

`POST /api/graph` continues accepting `files` and calls `build_from_uploads()` with the default configuration snapshot. Do not change the HTML conversion route or JSON export route in this work group.

- [ ] **Step 4: Verify integration GREEN**

Run: `.\.venv\Scripts\python -m pytest tests\test_converter_and_graph.py tests\test_app.py -q -p no:cacheprovider`

Expected: all integration/API tests pass with the new versioned graph shape.

- [ ] **Step 5: Commit API integration**

```powershell
git add sap_im_config_graph_explorer tests
git commit -m "feat: return the versioned graph contract"
```

---

### Task 9: Documentation, Legacy Regression, and Phase 1 Acceptance

**Files:**
- Modify: `README.md`
- Modify: `tests/test_converter_and_graph.py`
- Modify: `tests/test_app.py` only if a final contract assertion is missing.

**Interfaces:**
- Consumes: completed versioned graph/extractor foundation.
- Produces: documented schema/relationship direction, exact run commands, Phase 1 acceptance evidence for issues #1-#5.

- [ ] **Step 1: Add failing acceptance assertions for every allowlisted category and legacy CLI**

The acceptance test must build the combined fixtures and assert the exact type set:

```python
assert {node.type for node in graph.nodes} == NODE_TYPES
assert all(link.source in node_ids and link.target in node_ids for link in graph.links)
assert not any(node.metadata.get("tag") in {"FUNCTION", "PARAMETER_LIST"} for node in graph.nodes)
```

Retain and run the existing `test_legacy_cli_still_accepts_old_argument_shape` and HTML-summary test unchanged.

- [ ] **Step 2: Run acceptance tests and verify RED if coverage is incomplete**

Run: `.\.venv\Scripts\python -m pytest tests\test_converter_and_graph.py -q -p no:cacheprovider`

Expected: FAIL until fixtures cover every allowlisted type; add missing definition elements to `extractor_families.xml`, never production fallbacks.

- [ ] **Step 3: Update README to the implemented contract**

Document:

- `schemaVersion`, `snapshots`, expanded node/link fields, and `findings`.
- Dependency direction (dependent to dependency) and containment direction (child to owner).
- Dedicated extractor families and restricted custom registry.
- Missing/ambiguous references as findings.
- Reproducible `.venv` PowerShell install/test/run commands.
- Exact node and relationship vocabularies from `models.py`.
- Legacy converter command unchanged.

- [ ] **Step 4: Run complete verification**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python sap_im_transformer.py tests\fixtures\minimal_plan.xml "$env:TEMP\minimal-plan-acceptance.html" --variant=A
git diff --check
git status --short
```

Expected: all tests pass, CLI exits 0 and writes the HTML file, `git diff --check` prints nothing, and status contains only intentional source/test/doc changes before commit.

- [ ] **Step 5: Commit Phase 1 acceptance**

```powershell
git add README.md tests
git commit -m "docs: complete extractor foundation acceptance"
```

- [ ] **Step 6: Prepare issue closure evidence**

Record test commands/results, commit range, and issue mapping in the task report. Do not close #1-#5 until the whole-work-group review is clean and the changes are integrated into a branch that can be published.
