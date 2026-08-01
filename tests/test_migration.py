from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from sap_im_config_graph_explorer.graph_builder import GraphBuilder, SnapshotInput
from sap_im_config_graph_explorer.migration import MigrationRiskEngine


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
