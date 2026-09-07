import datetime
from pathlib import Path

from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.models import GraphNode
from sap_im_config_graph_explorer.temporal import (
    detect_temporal_findings,
    get_temporal_status,
    parse_iso_date,
    validate_date_string,
)
from sap_im_config_graph_explorer.validation import ValidationEngine

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_iso_date_valid_and_invalid():
    assert parse_iso_date("2026-01-01") == datetime.date(2026, 1, 1)
    assert parse_iso_date("2026-06-30T12:00:00") == datetime.date(2026, 6, 30)
    assert parse_iso_date("2026-12-31 23:59:59") == datetime.date(2026, 12, 31)
    assert parse_iso_date("  2026-07-01  ") == datetime.date(2026, 7, 1)
    assert parse_iso_date("") is None
    assert parse_iso_date(None) is None
    assert parse_iso_date("not-a-date") is None
    assert parse_iso_date("2026-99-99") is None


def test_validate_date_string():
    valid, err = validate_date_string("2026-01-01")
    assert valid is True
    assert err is None

    valid, err = validate_date_string("invalid")
    assert valid is False
    assert "not a valid ISO date" in err

    valid, err = validate_date_string("")
    assert valid is False
    assert "empty" in err


def test_get_temporal_status_undated():
    res = get_temporal_status(None, None, "2026-06-01")
    assert res.status == "undated"
    assert "does not define effective date" in res.explanation

    res = get_temporal_status("", "  ", "2026-06-01")
    assert res.status == "undated"


def test_get_temporal_status_unknown_invalid_dates():
    res = get_temporal_status("bad-start", "2026-12-31", "2026-06-01")
    assert res.status == "unknown"
    assert "Unsupported or invalid effective start date" in res.explanation

    res = get_temporal_status("2026-01-01", "bad-end", "2026-06-01")
    assert res.status == "unknown"
    assert "Unsupported or invalid effective end date" in res.explanation

    # Inverted range
    res = get_temporal_status("2026-12-31", "2026-01-01", "2026-06-01")
    assert res.status == "unknown"
    assert "Invalid date range: effective start date" in res.explanation

    # Bad as-of date
    res = get_temporal_status("2026-01-01", "2026-12-31", "invalid-as-of")
    assert res.status == "unknown"
    assert "Unsupported or invalid as-of date filter" in res.explanation


def test_get_temporal_status_relative_to_as_of_date():
    # Active
    res = get_temporal_status("2026-01-01", "2026-12-31", "2026-06-15")
    assert res.status == "active"
    assert "Active on 2026-06-15" in res.explanation

    # Boundary exact start
    res = get_temporal_status("2026-01-01", "2026-12-31", "2026-01-01")
    assert res.status == "active"

    # Boundary exact end
    res = get_temporal_status("2026-01-01", "2026-12-31", "2026-12-31")
    assert res.status == "active"

    # Future
    res = get_temporal_status("2026-07-01", "2026-12-31", "2026-06-15")
    assert res.status == "future"
    assert "Future: effective starting '2026-07-01'" in res.explanation

    # Expired
    res = get_temporal_status("2026-01-01", "2026-05-31", "2026-06-15")
    assert res.status == "expired"
    assert "Expired: effective ended on '2026-05-31'" in res.explanation

    # Open-ended future and active
    res = get_temporal_status("2026-07-01", None, "2026-06-01")
    assert res.status == "future"

    res = get_temporal_status("2026-07-01", None, "2026-08-01")
    assert res.status == "active"

    # No as-of date provided
    res = get_temporal_status("2026-01-01", "2026-12-31", None)
    assert res.status == "active"
    assert "Effective from 2026-01-01 to 2026-12-31." in res.explanation


def test_temporal_boundary_fixture_loads_without_temporal_defects():
    graph = GraphBuilder().build_from_paths([FIXTURES / "temporal_boundary.xml"])
    # There should be no temporal defects in temporal_boundary.xml
    temporal_codes = {
        "invalid_effective_date",
        "invalid_effective_date_range",
        "temporal_overlap",
        "temporal_gap",
        "missing_effective_date",
    }
    present_temporal = [f for f in graph.findings if f.code in temporal_codes]
    assert not present_temporal


def test_temporal_overlap_fixture_detects_overlap():
    graph = GraphBuilder().build_from_paths([FIXTURES / "temporal_overlap.xml"])
    overlap_findings = [f for f in graph.findings if f.code == "temporal_overlap"]
    assert len(overlap_findings) == 1
    finding = overlap_findings[0]
    assert finding.severity == "warning"
    assert "Overlapping effective dates" in finding.message
    assert "Overlapping Rule" in finding.message
    assert finding.details["overlapStart"] == "2026-07-01"
    assert finding.details["overlapEnd"] == "2026-08-31"
    assert len(finding.nodeIds) == 2


def test_temporal_gap_fixture_detects_gap():
    graph = GraphBuilder().build_from_paths([FIXTURES / "temporal_gap.xml"])
    gap_findings = [f for f in graph.findings if f.code == "temporal_gap"]
    assert len(gap_findings) == 1
    finding = gap_findings[0]
    assert finding.severity == "warning"
    assert "Effective date coverage gap" in finding.message
    assert "Gap Rule" in finding.message
    assert finding.details["gapStart"] == "2026-04-01"
    assert finding.details["gapEnd"] == "2026-05-31"
    assert len(finding.nodeIds) == 2


def test_temporal_missing_date_fixture_detects_errors_and_missing_dates():
    graph = GraphBuilder().build_from_paths([FIXTURES / "temporal_missing_date.xml"])
    codes = {f.code for f in graph.findings}
    assert "invalid_effective_date" in codes
    assert "invalid_effective_date_range" in codes
    assert "missing_effective_date" in codes

    invalid_date_finding = next(f for f in graph.findings if f.code == "invalid_effective_date")
    assert invalid_date_finding.severity == "error"
    assert "not-a-date" in invalid_date_finding.message

    inverted_range_finding = next(f for f in graph.findings if f.code == "invalid_effective_date_range")
    assert inverted_range_finding.severity == "error"
    assert "start '2026-12-31' is after end '2026-01-01'" in inverted_range_finding.message

    missing_date_finding = next(f for f in graph.findings if f.code == "missing_effective_date")
    assert missing_date_finding.severity == "warning"
    assert "Missing effective dates for versioned PlanComponent 'Missing Date Component'" in missing_date_finding.message
