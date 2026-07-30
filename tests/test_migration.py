from __future__ import annotations

from sap_im_config_graph_explorer.graph_builder import GraphBuilder, SnapshotInput
from sap_im_config_graph_explorer.migration import MigrationRiskEngine


def test_no_risk_when_snapshots_identical():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT>
    <PLAN_SET><PLAN NAME="P1"><PLAN_COMPONENT_REF NAME="C1"/></PLAN></PLAN_SET>
    <PLAN_COMPONENT_SET><PLAN_COMPONENT NAME="C1"><RULE_REF NAME="R1"/></PLAN_COMPONENT></PLAN_COMPONENT_SET>
    <RULE_SET><RULE NAME="R1" TYPE="Direct_Transaction_Credit"/></RULE_SET>
</DATA_IMPORT>
"""
    builder = GraphBuilder()
    doc = builder.build_snapshots([
        SnapshotInput(id="np", role="non_production", uploads=[("np.xml", xml)]),
        SnapshotInput(id="p", role="production", uploads=[("p.xml", xml)]),
    ])

    report = MigrationRiskEngine().analyze(doc)
    assert report is not None
    assert report.score == 0.0
    assert len(report.factors) == 0


def test_low_risk_orphaned_object():
    np_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT>
    <RULE_SET><RULE NAME="Orphan" TYPE="Direct_Transaction_Credit"/></RULE_SET>
</DATA_IMPORT>
"""
    p_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT></DATA_IMPORT>
"""
    builder = GraphBuilder()
    doc = builder.build_snapshots([
        SnapshotInput(id="np", role="non_production", uploads=[("np.xml", np_xml)]),
        SnapshotInput(id="p", role="production", uploads=[("p.xml", p_xml)]),
    ])

    report = MigrationRiskEngine().analyze(doc)
    assert report is not None
    assert report.score > 0
    assert any(f.code == "orphaned_object" for f in report.factors)


def test_medium_risk_changed_containment():
    p_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT>
    <PLAN_COMPONENT_SET><PLAN_COMPONENT NAME="C1"><RULE_REF NAME="R1"/></PLAN_COMPONENT></PLAN_COMPONENT_SET>
    <RULE_SET><RULE NAME="R1" TYPE="Direct_Transaction_Credit"/></RULE_SET>
</DATA_IMPORT>
"""
    np_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT>
    <PLAN_COMPONENT_SET><PLAN_COMPONENT NAME="C2"><RULE_REF NAME="R1"/></PLAN_COMPONENT></PLAN_COMPONENT_SET>
    <RULE_SET><RULE NAME="R1" TYPE="Direct_Transaction_Credit"/></RULE_SET>
</DATA_IMPORT>
"""
    builder = GraphBuilder()
    doc = builder.build_snapshots([
        SnapshotInput(id="np", role="non_production", uploads=[("np.xml", np_xml)]),
        SnapshotInput(id="p", role="production", uploads=[("p.xml", p_xml)]),
    ])

    report = MigrationRiskEngine().analyze(doc)
    assert report is not None
    assert any(f.code == "changed_containment" for f in report.factors)


def test_high_risk_missing_reference():
    np_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT>
    <PLAN_COMPONENT_SET><PLAN_COMPONENT NAME="C1"><RULE_REF NAME="Missing"/></PLAN_COMPONENT></PLAN_COMPONENT_SET>
</DATA_IMPORT>
"""
    p_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT></DATA_IMPORT>
"""
    builder = GraphBuilder()
    doc = builder.build_snapshots([
        SnapshotInput(id="np", role="non_production", uploads=[("np.xml", np_xml)]),
        SnapshotInput(id="p", role="production", uploads=[("p.xml", p_xml)]),
    ])

    report = MigrationRiskEngine().analyze(doc)
    assert report is not None
    assert any(f.code == "missing_reference" for f in report.factors)
    assert any(f.severity == "high" for f in report.factors)
