from __future__ import annotations

from sap_im_config_graph_explorer.models import (
    GraphDocument,
    MigrationRiskFactor,
    MigrationRiskReport,
)


HIGH_RISK_WEIGHT = 40.0
MEDIUM_RISK_WEIGHT = 10.0
LOW_RISK_WEIGHT = 2.0


class MigrationRiskEngine:
    """Analyze a graph document for migration risks by comparing snapshots."""

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
                        weight=HIGH_RISK_WEIGHT,
                        nodeIds=finding.nodeIds,
                    )
                )
            elif finding.code in ("orphaned_object", "unused_object"):
                factors.append(
                    MigrationRiskFactor(
                        code=finding.code,
                        severity="low",
                        message=finding.message,
                        weight=LOW_RISK_WEIGHT,
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
        factors: list[MigrationRiskFactor] = []
        nodes_by_id = {node.id: node for node in doc.nodes}
        np_nodes_by_key = {
            node.canonicalKey: node for node in doc.nodes if node.snapshotId == np_id
        }
        p_nodes_by_key = {
            node.canonicalKey: node for node in doc.nodes if node.snapshotId == p_id
        }

        np_links = [l for l in doc.links if nodes_by_id.get(l.source) and nodes_by_id[l.source].snapshotId == np_id]
        p_links = [l for l in doc.links if nodes_by_id.get(l.source) and nodes_by_id[l.source].snapshotId == p_id]

        def link_key(link):
            src = nodes_by_id.get(link.source)
            tgt = nodes_by_id.get(link.target)
            if not src or not tgt:
                return None
            return (src.canonicalKey, tgt.canonicalKey, link.relationship)

        np_link_set = {link_key(l) for l in np_links} - {None}
        p_link_set = {link_key(l) for l in p_links} - {None}

        containment_rels = {"belongs_to_plan", "belongs_to_plan_component", "parent_child"}

        # Changed Containment
        np_containment = {(sk, r): tk for (sk, tk, r) in np_link_set if r in containment_rels}
        p_containment = {(sk, r): tk for (sk, tk, r) in p_link_set if r in containment_rels}

        for (sk, r), tk_np in np_containment.items():
            if (sk, r) in p_containment:
                tk_p = p_containment[(sk, r)]
                if tk_np != tk_p:
                    child_node = np_nodes_by_key[sk]
                    p_parent_label = p_nodes_by_key[tk_p].label if tk_p in p_nodes_by_key else tk_p
                    np_parent_label = np_nodes_by_key[tk_np].label if tk_np in np_nodes_by_key else tk_np

                    factors.append(
                        MigrationRiskFactor(
                            code="changed_containment",
                            severity="medium",
                            message=f"{child_node.type} '{child_node.label}' moved from '{p_parent_label}' to '{np_parent_label}'",
                            weight=MEDIUM_RISK_WEIGHT,
                            nodeIds=(child_node.id,),
                        )
                    )

        # Missing Relationships (existed in P, gone in NP for an existing object)
        for (sk, tk, r) in p_link_set:
            if r in containment_rels:
                continue

            if sk in np_nodes_by_key and (sk, tk, r) not in np_link_set:
                source_node = np_nodes_by_key[sk]
                target_label = p_nodes_by_key[tk].label if tk in p_nodes_by_key else tk

                factors.append(
                    MigrationRiskFactor(
                        code="missing_relationship",
                        severity="medium",
                        message=f"{source_node.type} '{source_node.label}' no longer uses {r.replace('uses_', '')} '{target_label}'",
                        weight=5.0,
                        nodeIds=(source_node.id,),
                    )
                )

        return factors
