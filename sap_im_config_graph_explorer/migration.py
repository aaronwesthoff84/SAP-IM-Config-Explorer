import json
import math
import os
from dataclasses import dataclass
from typing import Any

from sap_im_config_graph_explorer.models import (
    GraphDocument,
    GraphNode,
    MigrationRiskFactor,
    MigrationRiskReport,
)


class MigrationRiskConfigError(ValueError):
    """Raised when migration risk weight configuration is invalid."""


@dataclass(frozen=True)
class MigrationRiskWeights:
    """Configurable weights for migration risk calculation."""

    high: float = 40.0
    medium: float = 10.0
    low: float = 2.0
    missing_relationship: float = 5.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MigrationRiskWeights:
        if not isinstance(data, dict):
            raise MigrationRiskConfigError(
                "Migration risk weights configuration must be a dictionary."
            )

        valid_keys = {"high", "medium", "low", "missing_relationship"}
        invalid_keys = set(data.keys()) - valid_keys
        if invalid_keys:
            raise MigrationRiskConfigError(
                f"Unknown migration risk weight configuration key(s): {', '.join(sorted(invalid_keys))}"
            )

        parsed_values: dict[str, float] = {}
        for key in valid_keys:
            if key in data:
                val = data[key]
                if (
                    not isinstance(val, (int, float))
                    or isinstance(val, bool)
                    or not math.isfinite(val)
                ):
                    raise MigrationRiskConfigError(
                        f"Migration risk weight '{key}' must be a finite number."
                    )
                if val < 0.0:
                    raise MigrationRiskConfigError(
                        f"Migration risk weight '{key}' must be non-negative (>= 0.0)."
                    )
                parsed_values[key] = float(val)

        return cls(
            high=parsed_values.get("high", 40.0),
            medium=parsed_values.get("medium", 10.0),
            low=parsed_values.get("low", 2.0),
            missing_relationship=parsed_values.get("missing_relationship", 5.0),
        )

    @classmethod
    def from_env(cls) -> MigrationRiskWeights:
        env_val = os.getenv("MIGRATION_RISK_WEIGHTS")
        if not env_val or not env_val.strip():
            return cls()

        trimmed = env_val.strip()
        if os.path.isfile(trimmed):
            try:
                with open(trimmed, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                raise MigrationRiskConfigError(
                    f"Failed to read migration risk weights file '{trimmed}': {e}"
                ) from e
        else:
            try:
                data = json.loads(trimmed)
            except Exception as e:
                raise MigrationRiskConfigError(
                    f"Failed to parse MIGRATION_RISK_WEIGHTS JSON: {e}"
                ) from e

        return cls.from_dict(data)

    def to_dict(self) -> dict[str, float]:
        return {
            "high": self.high,
            "medium": self.medium,
            "low": self.low,
            "missing_relationship": self.missing_relationship,
        }


DEFAULT_WEIGHTS = MigrationRiskWeights()
HIGH_RISK_WEIGHT = DEFAULT_WEIGHTS.high
MEDIUM_RISK_WEIGHT = DEFAULT_WEIGHTS.medium
LOW_RISK_WEIGHT = DEFAULT_WEIGHTS.low
CONTAINMENT_RELATIONS = {
    "belongs_to_plan",
    "belongs_to_plan_component",
    "parent_child",
}


class MigrationRiskEngine:
    """Analyze a graph document for migration risks by comparing snapshots."""

    def __init__(
        self, weights: MigrationRiskWeights | dict[str, Any] | None = None
    ):
        if weights is None:
            self.weights = MigrationRiskWeights.from_env()
        elif isinstance(weights, MigrationRiskWeights):
            self.weights = weights
        elif isinstance(weights, dict):
            self.weights = MigrationRiskWeights.from_dict(weights)
        else:
            raise MigrationRiskConfigError(
                f"weights must be MigrationRiskWeights or dict, got {type(weights).__name__}"
            )

    def analyze(self, doc: GraphDocument) -> MigrationRiskReport | None:
        np_snapshot = next(
            (s for s in doc.snapshots if s.role == "non_production"), None
        )
        p_snapshot = next(
            (s for s in doc.snapshots if s.role == "production"), None
        )

        if not np_snapshot or not p_snapshot:
            return None

        factors: list[MigrationRiskFactor] = []

        # 1. Findings-based risk (Deterministic Findings)
        # We only care about findings that exist in NP but NOT in P for the same objects
        nodes_by_id = {node.id: node for node in doc.nodes}
        p_findings_by_key = {
            (f.code, tuple(sorted(nodes_by_id[nid].canonicalKey for nid in f.nodeIds if nid in nodes_by_id and nodes_by_id[nid].snapshotId == p_snapshot.id)))
            for f in doc.findings if f.snapshotId == p_snapshot.id
        }

        for finding in doc.findings:
            if finding.snapshotId != np_snapshot.id:
                continue

            finding_objects_keys = tuple(sorted(nodes_by_id[nid].canonicalKey for nid in finding.nodeIds if nid in nodes_by_id))
            if (finding.code, finding_objects_keys) in p_findings_by_key:
                continue

            if finding.code in ("duplicate_object", "missing_reference", "ambiguous_reference"):
                factors.append(
                    MigrationRiskFactor(
                        code=finding.code,
                        severity="high",
                        message=finding.message,
                        weight=self.weights.high,
                        nodeIds=finding.nodeIds,
                    )
                )
            elif finding.code in ("orphaned_object", "unused_object"):
                factors.append(
                    MigrationRiskFactor(
                        code=finding.code,
                        severity="low",
                        message=finding.message,
                        weight=self.weights.low,
                        nodeIds=finding.nodeIds,
                    )
                )

        # 2. Comparison-based risk (Structural Changes)
        factors.extend(self._analyze_structural_changes(doc, np_snapshot.id, p_snapshot.id))

        # Sort factors by weight descending, then by message
        factors.sort(key=lambda f: (-f.weight, f.message))

        total_weight = sum(f.weight for f in factors)
        score = min(100.0, total_weight)

        return MigrationRiskReport(score=score, factors=factors)

    def _analyze_structural_changes(
        self, doc: GraphDocument, np_id: str, p_id: str
    ) -> list[MigrationRiskFactor]:
        nodes_by_id = {node.id: node for node in doc.nodes}
        np_nodes_by_key = {
            node.canonicalKey: node for node in doc.nodes if node.snapshotId == np_id
        }
        p_nodes_by_key = {
            node.canonicalKey: node for node in doc.nodes if node.snapshotId == p_id
        }

        np_link_set, p_link_set = self._extract_link_sets(doc, np_id, p_id, nodes_by_id)

        factors: list[MigrationRiskFactor] = []
        factors.extend(
            self._analyze_containment_changes(
                np_link_set, p_link_set, np_nodes_by_key, p_nodes_by_key
            )
        )
        factors.extend(
            self._analyze_missing_relationships(
                np_link_set, p_link_set, np_nodes_by_key, p_nodes_by_key
            )
        )

        return factors

    def _extract_link_sets(
        self,
        doc: GraphDocument,
        np_id: str,
        p_id: str,
        nodes_by_id: dict[str, GraphNode],
    ) -> tuple[set[tuple[str, str, str]], set[tuple[str, str, str]]]:
        def link_key(link):
            src = nodes_by_id.get(link.source)
            tgt = nodes_by_id.get(link.target)
            if not src or not tgt:
                return None
            return (src.canonicalKey, tgt.canonicalKey, link.relationship)

        np_links = [
            l
            for l in doc.links
            if nodes_by_id.get(l.source)
            and nodes_by_id[l.source].snapshotId == np_id
        ]
        p_links = [
            l
            for l in doc.links
            if nodes_by_id.get(l.source)
            and nodes_by_id[l.source].snapshotId == p_id
        ]

        np_link_set = {link_key(l) for l in np_links} - {None}
        p_link_set = {link_key(l) for l in p_links} - {None}

        return np_link_set, p_link_set

    def _group_containment_targets(
        self, link_keys: set[tuple[str, str, str]]
    ) -> dict[tuple[str, str], set[str]]:
        grouped: dict[tuple[str, str], set[str]] = {}
        for source_key, target_key, relationship in link_keys:
            if relationship in CONTAINMENT_RELATIONS:
                grouped.setdefault((source_key, relationship), set()).add(
                    target_key
                )
        return grouped

    def _format_containment_change(
        self, added_labels: list[str], removed_labels: list[str]
    ) -> str:
        if len(removed_labels) == 1 and len(added_labels) == 1:
            return f"moved from '{removed_labels[0]}' to '{added_labels[0]}'"
        if added_labels and not removed_labels:
            noun = "parent" if len(added_labels) == 1 else "parents"
            labels = ", ".join(f"'{label}'" for label in added_labels)
            return f"added {noun} {labels}"
        if removed_labels and not added_labels:
            noun = "parent" if len(removed_labels) == 1 else "parents"
            labels = ", ".join(f"'{label}'" for label in removed_labels)
            return f"removed {noun} {labels}"

        removed = ", ".join(f"'{label}'" for label in removed_labels)
        added = ", ".join(f"'{label}'" for label in added_labels)
        return f"changed parents: removed {removed}; added {added}"

    def _analyze_containment_changes(
        self,
        np_link_set: set[tuple[str, str, str]],
        p_link_set: set[tuple[str, str, str]],
        np_nodes_by_key: dict[str, GraphNode],
        p_nodes_by_key: dict[str, GraphNode],
    ) -> list[MigrationRiskFactor]:
        factors: list[MigrationRiskFactor] = []
        np_containment = self._group_containment_targets(np_link_set)
        p_containment = self._group_containment_targets(p_link_set)
        containment_keys = sorted(set(np_containment) | set(p_containment))

        for sk, relationship in containment_keys:
            if sk not in np_nodes_by_key or sk not in p_nodes_by_key:
                continue

            np_targets = np_containment.get((sk, relationship), set())
            p_targets = p_containment.get((sk, relationship), set())
            if np_targets == p_targets:
                continue

            added_keys = sorted(np_targets - p_targets)
            removed_keys = sorted(p_targets - np_targets)
            added_labels = [
                np_nodes_by_key[key].label if key in np_nodes_by_key else key
                for key in added_keys
            ]
            removed_labels = [
                p_nodes_by_key[key].label if key in p_nodes_by_key else key
                for key in removed_keys
            ]
            child_node = np_nodes_by_key[sk]
            message_prefix = (
                f"{child_node.type} '{child_node.label}' containment via {relationship}"
            )
            change = self._format_containment_change(added_labels, removed_labels)

            factors.append(
                MigrationRiskFactor(
                    code="changed_containment",
                    severity="medium",
                    message=f"{message_prefix} {change}",
                    weight=self.weights.medium,
                    nodeIds=(child_node.id,),
                )
            )

        return factors

    def _analyze_missing_relationships(
        self,
        np_link_set: set[tuple[str, str, str]],
        p_link_set: set[tuple[str, str, str]],
        np_nodes_by_key: dict[str, GraphNode],
        p_nodes_by_key: dict[str, GraphNode],
    ) -> list[MigrationRiskFactor]:
        factors: list[MigrationRiskFactor] = []
        for (sk, tk, r) in p_link_set:
            if r in CONTAINMENT_RELATIONS:
                continue

            if sk in np_nodes_by_key and (sk, tk, r) not in np_link_set:
                source_node = np_nodes_by_key[sk]
                target_label = p_nodes_by_key[tk].label if tk in p_nodes_by_key else tk

                factors.append(
                    MigrationRiskFactor(
                        code="missing_relationship",
                        severity="medium",
                        message=f"{source_node.type} '{source_node.label}' no longer uses {r.replace('uses_', '')} '{target_label}'",
                        weight=self.weights.missing_relationship,
                        nodeIds=(source_node.id,),
                    )
                )

        return factors
