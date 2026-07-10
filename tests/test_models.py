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
