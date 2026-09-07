from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from sap_im_config_graph_explorer.graph_builder import GraphBuilder, SnapshotInput
from sap_im_config_graph_explorer.migration import (
    MigrationRiskConfigError,
    MigrationRiskEngine,
    MigrationRiskWeights,
)


def _containment_xml(parent_rules: dict[str, tuple[str, ...]]) -> bytes:
    components = "".join(
        f'<PLAN_COMPONENT NAME="{parent}">'
        + "".join(f'<RULE_REF NAME="{rule}"/>' for rule in sorted(rules))
        + "</PLAN_COMPONENT>"
        for parent, rules in sorted(parent_rules.items())
    )
    rule_names = sorted({rule for rules in parent_rules.values() for rule in rules})
    rules = "".join(
        f'<RULE NAME="{rule}" TYPE="Direct_Transaction_Credit"/>'
        for rule in rule_names
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<DATA_IMPORT><PLAN_COMPONENT_SET>{components}</PLAN_COMPONENT_SET>"
        f"<RULE_SET>{rules}</RULE_SET></DATA_IMPORT>"
    ).encode()


def _containment_report(
    np_parent_rules: dict[str, tuple[str, ...]],
    p_parent_rules: dict[str, tuple[str, ...]],
):
    doc = GraphBuilder().build_snapshots(
        [
            SnapshotInput(
                id="np",
                role="non_production",
                uploads=[("np.xml", _containment_xml(np_parent_rules))],
            ),
            SnapshotInput(
                id="p",
                role="production",
                uploads=[("p.xml", _containment_xml(p_parent_rules))],
            ),
        ]
    )
    report = MigrationRiskEngine().analyze(doc)
    assert report is not None
    return report


def _factor_summaries(report) -> list[tuple[str, str, str, float]]:
    return [
        (factor.code, factor.severity, factor.message, factor.weight)
        for factor in report.factors
    ]


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


def test_shared_containment_is_identical_when_all_parents_match():
    shared = {"C1": ("R1",), "C2": ("R1",)}

    report = _containment_report(shared, shared)

    assert report.score == 0.0
    assert _factor_summaries(report) == []


def test_added_shared_containment_parent_has_exact_factor():
    report = _containment_report(
        {"C1": ("R1",), "C2": ("R1",)},
        {"C1": ("R1",), "C2": ()},
    )

    assert report.score == 10.0
    assert _factor_summaries(report) == [
        (
            "changed_containment",
            "medium",
            "Rule 'R1' containment via belongs_to_plan_component added parent 'C2'",
            10.0,
        )
    ]


def test_removed_shared_containment_parent_has_exact_factor():
    report = _containment_report(
        {"C1": ("R1",), "C2": ()},
        {"C1": ("R1",), "C2": ("R1",)},
    )

    assert report.score == 12.0
    assert _factor_summaries(report) == [
        (
            "changed_containment",
            "medium",
            "Rule 'R1' containment via belongs_to_plan_component removed parent 'C2'",
            10.0,
        ),
        (
            "orphaned_object",
            "low",
            "Orphaned PlanComponent object: C2",
            2.0,
        ),
    ]


def test_changed_shared_containment_parent_has_exact_factor():
    report = _containment_report(
        {"C1": ("R1",), "C2": (), "C3": ("R1",)},
        {"C1": ("R1",), "C2": ("R1",), "C3": ()},
    )

    assert report.score == 12.0
    assert _factor_summaries(report) == [
        (
            "changed_containment",
            "medium",
            "Rule 'R1' containment via belongs_to_plan_component moved from 'C2' to 'C3'",
            10.0,
        ),
        (
            "orphaned_object",
            "low",
            "Orphaned PlanComponent object: C2",
            2.0,
        ),
    ]


def test_shared_containment_output_is_identical_across_hash_seeds():
    test_file = Path(__file__).resolve()
    script = f"""
import json
import runpy

namespace = runpy.run_path({str(test_file)!r})
report = namespace['_containment_report'](
    {{'C1': ('R1', 'R2'), 'C2': (), 'C3': ('R1', 'R2')}},
    {{'C1': ('R1', 'R2'), 'C2': ('R1', 'R2'), 'C3': ()}},
)
payload = {{
    'score': report.score,
    'factors': namespace['_factor_summaries'](report),
}}
print(json.dumps(payload, sort_keys=True))
"""
    outputs = []
    for seed in range(1, 21):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = str(seed)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            cwd=test_file.parents[1],
            env=env,
            capture_output=True,
            text=True,
        )
        outputs.append(result.stdout.strip())

    expected = json.dumps(
        {
            "score": 22.0,
            "factors": [
                [
                    "changed_containment",
                    "medium",
                    "Rule 'R1' containment via belongs_to_plan_component moved from 'C2' to 'C3'",
                    10.0,
                ],
                [
                    "changed_containment",
                    "medium",
                    "Rule 'R2' containment via belongs_to_plan_component moved from 'C2' to 'C3'",
                    10.0,
                ],
                [
                    "orphaned_object",
                    "low",
                    "Orphaned PlanComponent object: C2",
                    2.0,
                ],
            ],
        },
        sort_keys=True,
    )
    assert outputs == [expected] * 20


def test_migration_risk_weights_defaults():
    weights = MigrationRiskWeights()
    assert weights.high == 40.0
    assert weights.medium == 10.0
    assert weights.low == 2.0
    assert weights.missing_relationship == 5.0
    assert weights.to_dict() == {
        "high": 40.0,
        "medium": 10.0,
        "low": 2.0,
        "missing_relationship": 5.0,
    }


def test_migration_risk_weights_custom_and_env(monkeypatch, tmp_path):
    custom = MigrationRiskWeights.from_dict({
        "high": 50.0,
        "medium": 15.0,
        "low": 3.0,
        "missing_relationship": 7.5,
    })
    assert custom.high == 50.0
    assert custom.medium == 15.0
    assert custom.low == 3.0
    assert custom.missing_relationship == 7.5

    # Test loading from env JSON string
    monkeypatch.setenv("MIGRATION_RISK_WEIGHTS", '{"high": 35.0, "low": 1.0}')
    from_env = MigrationRiskWeights.from_env()
    assert from_env.high == 35.0
    assert from_env.medium == 10.0  # default
    assert from_env.low == 1.0

    # Test loading from env file path
    config_file = tmp_path / "risk_weights.json"
    config_file.write_text('{"medium": 12.5, "missing_relationship": 6.0}', encoding="utf-8")
    monkeypatch.setenv("MIGRATION_RISK_WEIGHTS", str(config_file))
    from_file = MigrationRiskWeights.from_env()
    assert from_file.medium == 12.5
    assert from_file.missing_relationship == 6.0
    assert from_file.high == 40.0


def test_migration_risk_weights_validation_errors():
    import pytest

    # Negative weight
    with pytest.raises(MigrationRiskConfigError, match="must be non-negative"):
        MigrationRiskWeights.from_dict({"high": -1.0})

    # Non-finite weight
    with pytest.raises(MigrationRiskConfigError, match="must be a finite number"):
        MigrationRiskWeights.from_dict({"high": float("inf")})

    with pytest.raises(MigrationRiskConfigError, match="must be a finite number"):
        MigrationRiskWeights.from_dict({"high": float("nan")})

    # Invalid type
    with pytest.raises(MigrationRiskConfigError, match="must be a finite number"):
        MigrationRiskWeights.from_dict({"low": "invalid"})

    with pytest.raises(MigrationRiskConfigError, match="must be a finite number"):
        MigrationRiskWeights.from_dict({"medium": True})

    # Unknown key
    with pytest.raises(MigrationRiskConfigError, match="Unknown migration risk weight configuration key"):
        MigrationRiskWeights.from_dict({"extra_field": 10.0})

    # Non-dict
    with pytest.raises(MigrationRiskConfigError, match="must be a dictionary"):
        MigrationRiskWeights.from_dict(["not", "a", "dict"])


def test_migration_risk_engine_uses_configured_weights():
    # Report using default weights
    default_report = _containment_report(
        {"C1": ("R1",), "C2": ("R1",), "C3": ()},
        {"C1": ("R1",), "C2": ("R1",), "C3": ()},
    )
    assert default_report.score == 0.0

    # Test with custom weights engine on a diff
    doc = GraphBuilder().build_snapshots([
        SnapshotInput(
            id="np",
            role="non_production",
            uploads=[("np.xml", _containment_xml({"C1": ("R1",), "C2": (), "C3": ("R1",)}))],
        ),
        SnapshotInput(
            id="p",
            role="production",
            uploads=[("p.xml", _containment_xml({"C1": ("R1",), "C2": ("R1",), "C3": ()}))],
        ),
    ])

    custom_engine = MigrationRiskEngine(weights={"medium": 20.0, "low": 5.0})
    custom_report = custom_engine.analyze(doc)
    assert custom_report is not None

    # Containment changed was medium (now 20.0), orphaned object was low (now 5.0)
    # Total score should be 20.0 + 5.0 = 25.0
    assert custom_report.score == 25.0
    weights_in_factors = {f.code: f.weight for f in custom_report.factors}
    assert weights_in_factors["changed_containment"] == 20.0
    assert weights_in_factors["orphaned_object"] == 5.0


def test_migration_risk_factor_ordering_and_multi_factors_on_single_object():
    # NP has an orphaned Rule that also has another finding
    np_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT>
    <RULE_SET>
        <RULE NAME="DuplicateOrphan" TYPE="Direct_Transaction_Credit"/>
        <RULE NAME="DuplicateOrphan" TYPE="Direct_Transaction_Credit"/>
    </RULE_SET>
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

    engine = MigrationRiskEngine()
    report = engine.analyze(doc)
    assert report is not None
    assert len(report.factors) >= 2

    # Check descending weight order
    for i in range(len(report.factors) - 1):
        assert report.factors[i].weight >= report.factors[i + 1].weight

    # Check that the duplicate orphan nodes have multiple associated factors
    node_id_counts: dict[str, int] = {}
    for factor in report.factors:
        for nid in factor.nodeIds:
            node_id_counts[nid] = node_id_counts.get(nid, 0) + 1

    # At least one node is associated with both duplicate_object (high risk) and orphaned_object (low risk)
    multi_factor_nodes = [nid for nid, count in node_id_counts.items() if count > 1]
    assert len(multi_factor_nodes) > 0

