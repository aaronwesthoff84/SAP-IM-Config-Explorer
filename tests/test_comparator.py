from __future__ import annotations

from pathlib import Path
import pytest

from sap_im_config_graph_explorer.comparator import ConfigComparator
from sap_im_config_graph_explorer.xml_loader import XmlLoadError

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def test_compare_two_xml_exports_identifies_all_change_categories():
    comparator = ConfigComparator(topology_mode="full")
    baseline_path = FIXTURES / "compare_baseline.xml"
    candidate_path = FIXTURES / "compare_candidate.xml"

    result = comparator.compare_files(baseline_path, candidate_path)

    assert result.ok is True
    assert result.baselineFile == "compare_baseline.xml"
    assert result.candidateFile == "compare_candidate.xml"

    # Added objects
    added_labels = {(item.type, item.label) for item in result.added}
    assert ("Plan", "New Regional Plan") in added_labels
    assert ("PlanComponent", "Bonus Component") in added_labels
    assert ("Rule", "Audit Rule") in added_labels
    assert ("Formula", "New Formula") in added_labels

    # Removed objects
    removed_labels = {(item.type, item.label) for item in result.removed}
    assert ("Plan", "Decommissioned Plan") in removed_labels
    assert ("PlanComponent", "Legacy Component") in removed_labels
    assert ("Rule", "Old Rule") in removed_labels
    assert ("Formula", "Eligibility Formula") in removed_labels

    # Changed objects
    changed_map = {item.label: item for item in result.changed}
    assert "Enterprise Plan" in changed_map
    assert "Core Component" in changed_map
    assert "Credit Rule" in changed_map

    # Check Enterprise Plan differences (containment added, description changed)
    plan_diffs = changed_map["Enterprise Plan"].differences
    diff_fields = {d.field for d in plan_diffs}
    assert "description" in diff_fields
    assert "containment:child" in diff_fields
    assert any("Added Plan Component containment: 'Bonus Component'" in d.description for d in plan_diffs)
    assert any("Description changed" in d.description for d in plan_diffs)

    # Check Core Component differences (containment added, description changed)
    comp_diffs = changed_map["Core Component"].differences
    assert any("Added Rule containment: 'Audit Rule'" in d.description for d in comp_diffs)

    # Check Credit Rule differences (effective dates, TYPE attribute, reference)
    rule_diffs = changed_map["Credit Rule"].differences
    rule_fields = {d.field for d in rule_diffs}
    assert "effectiveDates" in rule_fields
    assert "attribute:TYPE" in rule_fields
    assert any("Attribute 'TYPE' changed from 'DIRECT_TRANSACTION_CREDIT' to 'BONUS_CALCULATION'" in d.description for d in rule_diffs)
    assert any("Effective dates changed" in d.description for d in rule_diffs)
    assert any("Added reference" in d.description and "New Formula" in d.description for d in rule_diffs)

    # Unchanged objects
    unchanged_labels = {(item.type, item.label) for item in result.unchanged}
    assert ("LookupTable", "Rate Table") in unchanged_labels

    # Summary checks
    assert result.summary.totalAdded == len(result.added)
    assert result.summary.totalRemoved == len(result.removed)
    assert result.summary.totalChanged == len(result.changed)
    assert result.summary.totalUnchanged == len(result.unchanged)

    # By-type breakdowns
    assert "Plan" in result.summary.byType
    assert result.summary.byType["Plan"]["added"] == 1
    assert result.summary.byType["Plan"]["removed"] == 1
    assert result.summary.byType["Plan"]["changed"] == 1

    assert "Rule" in result.summary.byType
    assert result.summary.byType["Rule"]["added"] == 1
    assert result.summary.byType["Rule"]["removed"] == 1
    assert result.summary.byType["Rule"]["changed"] == 1


def test_compare_independent_of_file_names():
    comparator = ConfigComparator(topology_mode="full")
    baseline_bytes = (FIXTURES / "compare_baseline.xml").read_bytes()
    candidate_bytes = (FIXTURES / "compare_candidate.xml").read_bytes()

    # Pass arbitrary, non-standard names
    result = comparator.compare_xml_texts(
        baseline_content=baseline_bytes,
        candidate_content=candidate_bytes,
        baseline_filename="custom_random_export_99.xml",
        candidate_filename="production_snapshot_2026.xml",
    )

    assert result.ok is True
    assert result.baselineFile == "custom_random_export_99.xml"
    assert result.candidateFile == "production_snapshot_2026.xml"
    assert result.summary.totalAdded > 0
    assert result.summary.totalRemoved > 0
    assert result.summary.totalChanged > 0


def test_compare_identical_files_reports_zero_changes():
    comparator = ConfigComparator(topology_mode="full")
    content = (FIXTURES / "minimal_plan.xml").read_bytes()

    result = comparator.compare_xml_texts(
        baseline_content=content,
        candidate_content=content,
        baseline_filename="minimal_a.xml",
        candidate_filename="minimal_b.xml",
    )

    assert result.ok is True
    assert result.summary.totalAdded == 0
    assert result.summary.totalRemoved == 0
    assert result.summary.totalChanged == 0
    assert result.summary.totalUnchanged > 0
    assert len(result.unchanged) > 0


def test_compare_invalid_xml_raises_load_error():
    comparator = ConfigComparator()
    valid_content = (FIXTURES / "minimal_plan.xml").read_bytes()
    invalid_content = (FIXTURES / "compare_invalid.xml").read_bytes()

    with pytest.raises(XmlLoadError):
        comparator.compare_xml_texts(
            baseline_content=invalid_content,
            candidate_content=valid_content,
        )

    with pytest.raises(XmlLoadError):
        comparator.compare_xml_texts(
            baseline_content=valid_content,
            candidate_content=invalid_content,
        )


def test_compare_empty_xml_raises_load_error():
    comparator = ConfigComparator()
    valid_content = (FIXTURES / "minimal_plan.xml").read_bytes()

    with pytest.raises(XmlLoadError):
        comparator.compare_xml_texts(
            baseline_content=b"",
            candidate_content=valid_content,
        )
