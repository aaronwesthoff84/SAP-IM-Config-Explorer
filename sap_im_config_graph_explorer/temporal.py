from __future__ import annotations

import datetime
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sap_im_config_graph_explorer.models import GraphNode, ValidationFinding
from sap_im_config_graph_explorer.object_extractors.common import normalize_identity


def parse_iso_date(date_str: str | None) -> datetime.date | None:
    """Parse an ISO date or datetime string into a datetime.date."""
    if not date_str:
        return None
    cleaned = date_str.strip()
    if not cleaned:
        return None
    # Handle YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS
    if "T" in cleaned:
        cleaned = cleaned.split("T", 1)[0]
    elif " " in cleaned:
        cleaned = cleaned.split(" ", 1)[0]
    try:
        return datetime.date.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None


def validate_date_string(date_str: str | None) -> tuple[bool, str | None]:
    """Validate if a string can be parsed as a valid ISO date."""
    if not date_str or not date_str.strip():
        return False, "Date string is empty."
    parsed = parse_iso_date(date_str)
    if parsed is None:
        return False, f"'{date_str}' is not a valid ISO date (expected YYYY-MM-DD)."
    return True, None


@dataclass(frozen=True)
class TemporalStatusResult:
    status: str  # "active" | "future" | "expired" | "undated" | "unknown"
    effectiveStartDate: str | None
    effectiveEndDate: str | None
    asOfDate: str | None
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "effectiveStartDate": self.effectiveStartDate,
            "effectiveEndDate": self.effectiveEndDate,
            "asOfDate": self.asOfDate,
            "explanation": self.explanation,
        }


def get_temporal_status(
    start_str: str | None,
    end_str: str | None,
    as_of_date_str: str | None = None,
) -> TemporalStatusResult:
    """Compute temporal status and explanation for an object relative to an optional as-of date."""
    raw_start = (start_str or "").strip() or None
    raw_end = (end_str or "").strip() or None
    raw_as_of = (as_of_date_str or "").strip() or None

    if not raw_start and not raw_end:
        return TemporalStatusResult(
            status="undated",
            effectiveStartDate=None,
            effectiveEndDate=None,
            asOfDate=raw_as_of,
            explanation="Object does not define effective date metadata in configuration source.",
        )

    start_date = parse_iso_date(raw_start) if raw_start else None
    if raw_start and start_date is None:
        return TemporalStatusResult(
            status="unknown",
            effectiveStartDate=raw_start,
            effectiveEndDate=raw_end,
            asOfDate=raw_as_of,
            explanation=f"Unsupported or invalid effective start date format: '{raw_start}'.",
        )

    end_date = parse_iso_date(raw_end) if raw_end else None
    if raw_end and end_date is None:
        return TemporalStatusResult(
            status="unknown",
            effectiveStartDate=raw_start,
            effectiveEndDate=raw_end,
            asOfDate=raw_as_of,
            explanation=f"Unsupported or invalid effective end date format: '{raw_end}'.",
        )

    if start_date and end_date and start_date > end_date:
        return TemporalStatusResult(
            status="unknown",
            effectiveStartDate=raw_start,
            effectiveEndDate=raw_end,
            asOfDate=raw_as_of,
            explanation=(
                f"Invalid date range: effective start date '{raw_start}' "
                f"is after effective end date '{raw_end}'."
            ),
        )

    if not raw_as_of:
        range_desc = (
            f"{raw_start or 'beginning'} to {raw_end or 'indefinite'}"
        )
        return TemporalStatusResult(
            status="active",
            effectiveStartDate=raw_start,
            effectiveEndDate=raw_end,
            asOfDate=None,
            explanation=f"Effective from {range_desc}.",
        )

    as_of_date = parse_iso_date(raw_as_of)
    if as_of_date is None:
        return TemporalStatusResult(
            status="unknown",
            effectiveStartDate=raw_start,
            effectiveEndDate=raw_end,
            asOfDate=raw_as_of,
            explanation=f"Unsupported or invalid as-of date filter: '{raw_as_of}'.",
        )

    if start_date and as_of_date < start_date:
        return TemporalStatusResult(
            status="future",
            effectiveStartDate=raw_start,
            effectiveEndDate=raw_end,
            asOfDate=raw_as_of,
            explanation=(
                f"Future: effective starting '{raw_start}' "
                f"(after selected as-of date {raw_as_of})."
            ),
        )

    if end_date and as_of_date > end_date:
        return TemporalStatusResult(
            status="expired",
            effectiveStartDate=raw_start,
            effectiveEndDate=raw_end,
            asOfDate=raw_as_of,
            explanation=(
                f"Expired: effective ended on '{raw_end}' "
                f"(prior to selected as-of date {raw_as_of})."
            ),
        )

    range_desc = f"{raw_start or 'beginning'} to {raw_end or 'indefinite'}"
    return TemporalStatusResult(
        status="active",
        effectiveStartDate=raw_start,
        effectiveEndDate=raw_end,
        asOfDate=raw_as_of,
        explanation=f"Active on {raw_as_of} (effective {range_desc}).",
    )


def _finding_id(snapshot_id: str, code: str, *parts: str) -> str:
    payload = "\x1f".join((snapshot_id, code, *parts))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"finding-{digest}"


def detect_temporal_findings(nodes: list[GraphNode]) -> list[ValidationFinding]:
    """Detect temporal defects: invalid date formats, inverted ranges, overlaps, gaps, and missing dates."""
    findings: list[ValidationFinding] = []

    # 1. Per-node date validation (invalid date format or inverted range)
    for node in sorted(nodes, key=lambda n: (n.snapshotId, n.canonicalKey, n.id)):
        raw_start = (node.metadata.get("effectiveStartDate") or "").strip()
        raw_end = (node.metadata.get("effectiveEndDate") or "").strip()

        if raw_start:
            parsed_start = parse_iso_date(raw_start)
            if parsed_start is None:
                findings.append(
                    ValidationFinding(
                        id=_finding_id(node.snapshotId, "invalid_effective_date", node.id, "start"),
                        code="invalid_effective_date",
                        severity="error",
                        snapshotId=node.snapshotId,
                        nodeIds=(node.id,),
                        message=f"Invalid effective start date format for {node.type} '{node.label}': '{raw_start}'",
                        details={
                            "nodeId": node.id,
                            "canonicalKey": node.canonicalKey,
                            "dateField": "effectiveStartDate",
                            "dateValue": raw_start,
                            "sourceFile": node.sourceFile,
                            "xmlPath": node.xmlPath,
                        },
                    )
                )

        if raw_end:
            parsed_end = parse_iso_date(raw_end)
            if parsed_end is None:
                findings.append(
                    ValidationFinding(
                        id=_finding_id(node.snapshotId, "invalid_effective_date", node.id, "end"),
                        code="invalid_effective_date",
                        severity="error",
                        snapshotId=node.snapshotId,
                        nodeIds=(node.id,),
                        message=f"Invalid effective end date format for {node.type} '{node.label}': '{raw_end}'",
                        details={
                            "nodeId": node.id,
                            "canonicalKey": node.canonicalKey,
                            "dateField": "effectiveEndDate",
                            "dateValue": raw_end,
                            "sourceFile": node.sourceFile,
                            "xmlPath": node.xmlPath,
                        },
                    )
                )

        if raw_start and raw_end:
            parsed_start = parse_iso_date(raw_start)
            parsed_end = parse_iso_date(raw_end)
            if parsed_start is not None and parsed_end is not None and parsed_start > parsed_end:
                findings.append(
                    ValidationFinding(
                        id=_finding_id(node.snapshotId, "invalid_effective_date_range", node.id),
                        code="invalid_effective_date_range",
                        severity="error",
                        snapshotId=node.snapshotId,
                        nodeIds=(node.id,),
                        message=(
                            f"Invalid effective date range for {node.type} '{node.label}': "
                            f"start '{raw_start}' is after end '{raw_end}'"
                        ),
                        details={
                            "nodeId": node.id,
                            "canonicalKey": node.canonicalKey,
                            "effectiveStartDate": raw_start,
                            "effectiveEndDate": raw_end,
                            "sourceFile": node.sourceFile,
                            "xmlPath": node.xmlPath,
                        },
                    )
                )

    # 2. Multi-version group validation (overlaps, gaps, missing dates in versioned series)
    groups: dict[tuple[str, str, str], list[GraphNode]] = defaultdict(list)
    for node in nodes:
        norm_label = normalize_identity(node.label)
        if norm_label:
            groups[(node.snapshotId, node.type, norm_label)].append(node)

    for (snapshot_id, node_type, _), group_nodes in sorted(groups.items(), key=lambda item: item[0]):
        if len(group_nodes) < 2:
            continue

        dated_nodes: list[tuple[GraphNode, datetime.date, datetime.date]] = []
        has_any_dates = False
        has_undated_nodes = False

        for node in sorted(group_nodes, key=lambda n: n.id):
            raw_start = (node.metadata.get("effectiveStartDate") or "").strip()
            raw_end = (node.metadata.get("effectiveEndDate") or "").strip()

            if not raw_start and not raw_end:
                has_undated_nodes = True
                continue

            has_any_dates = True
            parsed_start = parse_iso_date(raw_start) if raw_start else None
            parsed_end = parse_iso_date(raw_end) if raw_end else None

            # Skip invalid ranges/dates from overlap/gap calculation (already reported above)
            if (raw_start and parsed_start is None) or (raw_end and parsed_end is None):
                continue
            if parsed_start and parsed_end and parsed_start > parsed_end:
                continue

            eff_start = parsed_start if parsed_start is not None else datetime.date.min
            eff_end = parsed_end if parsed_end is not None else datetime.date.max
            dated_nodes.append((node, eff_start, eff_end))

        # If some nodes in the versioned group have dates and others have NO dates, flag missing_effective_date
        if has_any_dates and has_undated_nodes:
            for node in sorted(group_nodes, key=lambda n: n.id):
                raw_start = (node.metadata.get("effectiveStartDate") or "").strip()
                raw_end = (node.metadata.get("effectiveEndDate") or "").strip()
                if not raw_start and not raw_end:
                    findings.append(
                        ValidationFinding(
                            id=_finding_id(snapshot_id, "missing_effective_date", node.id),
                            code="missing_effective_date",
                            severity="warning",
                            snapshotId=snapshot_id,
                            nodeIds=(node.id,),
                            message=f"Missing effective dates for versioned {node.type} '{node.label}'",
                            details={
                                "nodeId": node.id,
                                "canonicalKey": node.canonicalKey,
                                "sourceFile": node.sourceFile,
                                "xmlPath": node.xmlPath,
                            },
                        )
                    )

        # Check for overlaps between pairs
        has_overlaps = False
        for i in range(len(dated_nodes)):
            node_a, start_a, end_a = dated_nodes[i]
            for j in range(i + 1, len(dated_nodes)):
                node_b, start_b, end_b = dated_nodes[j]
                overlap_start = max(start_a, start_b)
                overlap_end = min(end_a, end_b)

                if overlap_start <= overlap_end:
                    has_overlaps = True
                    pair_ids = tuple(sorted([node_a.id, node_b.id]))
                    range_a_str = (
                        f"{node_a.metadata.get('effectiveStartDate') or 'open'} to "
                        f"{node_a.metadata.get('effectiveEndDate') or 'open'}"
                    )
                    range_b_str = (
                        f"{node_b.metadata.get('effectiveStartDate') or 'open'} to "
                        f"{node_b.metadata.get('effectiveEndDate') or 'open'}"
                    )
                    findings.append(
                        ValidationFinding(
                            id=_finding_id(snapshot_id, "temporal_overlap", *pair_ids),
                            code="temporal_overlap",
                            severity="warning",
                            snapshotId=snapshot_id,
                            nodeIds=pair_ids,
                            message=(
                                f"Overlapping effective dates for {node_a.type} '{node_a.label}': "
                                f"[{range_a_str}] overlaps with [{range_b_str}]"
                            ),
                            details={
                                "canonicalKey": node_a.canonicalKey or node_b.canonicalKey,
                                "nodeIds": list(pair_ids),
                                "rangeA": range_a_str,
                                "rangeB": range_b_str,
                                "overlapStart": overlap_start.isoformat() if overlap_start != datetime.date.min else "open",
                                "overlapEnd": overlap_end.isoformat() if overlap_end != datetime.date.max else "open",
                                "sourceFiles": sorted({node_a.sourceFile, node_b.sourceFile}),
                            },
                        )
                    )

        # Check for coverage gaps if there are no overlaps in this group
        if not has_overlaps and len(dated_nodes) >= 2:
            sorted_dated = sorted(dated_nodes, key=lambda item: (item[1], item[2], item[0].id))
            for i in range(len(sorted_dated) - 1):
                node_curr, _, end_curr = sorted_dated[i]
                node_next, start_next, _ = sorted_dated[i + 1]

                if end_curr != datetime.date.max and start_next != datetime.date.min:
                    gap_days = (start_next - end_curr).days
                    if gap_days > 1:
                        gap_start = end_curr + datetime.timedelta(days=1)
                        gap_end = start_next - datetime.timedelta(days=1)
                        pair_ids = tuple(sorted([node_curr.id, node_next.id]))
                        findings.append(
                            ValidationFinding(
                                id=_finding_id(snapshot_id, "temporal_gap", *pair_ids),
                                code="temporal_gap",
                                severity="warning",
                                snapshotId=snapshot_id,
                                nodeIds=pair_ids,
                                message=(
                                    f"Effective date coverage gap for {node_curr.type} '{node_curr.label}' "
                                    f"between {end_curr.isoformat()} and {start_next.isoformat()}"
                                ),
                                details={
                                    "canonicalKey": node_curr.canonicalKey or node_next.canonicalKey,
                                    "nodeIds": list(pair_ids),
                                    "gapStart": gap_start.isoformat(),
                                    "gapEnd": gap_end.isoformat(),
                                    "sourceFiles": sorted({node_curr.sourceFile, node_next.sourceFile}),
                                },
                            )
                        )

    return findings
