from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from sap_im_config_graph_explorer.models import (
    GraphLink,
    GraphNode,
    ValidationFinding,
)
from sap_im_config_graph_explorer.object_extractors.base import ReferenceCandidate
from sap_im_config_graph_explorer.object_extractors.common import (
    expected_type_for_hint,
    normalize_identity,
    relationship_for_reference,
)


@dataclass
class ResolutionResult:
    links: list[GraphLink] = field(default_factory=list)
    findings: list[ValidationFinding] = field(default_factory=list)


@dataclass
class ReferenceResolver:
    nodes: list[GraphNode]
    references: list[ReferenceCandidate]
    node_id_by_element: dict[int, str]

    def resolve(self) -> ResolutionResult:
        result = ResolutionResult()
        index = self._build_index()
        node_by_id = {node.id: node for node in self.nodes}
        seen_links: set[tuple[str, str, str, str]] = set()
        seen_findings: set[tuple[str, str, str, str]] = set()

        for reference in self.references:
            source_id = self.node_id_by_element.get(id(reference.source_element))
            source = node_by_id.get(source_id or "")
            if source is None:
                continue

            candidates = self._candidates(reference, source.snapshotId, index)
            if not candidates:
                self._append_finding(
                    result,
                    seen_findings,
                    "missing_reference",
                    source,
                    reference,
                    (),
                )
                continue
            if len(candidates) > 1:
                self._append_finding(
                    result,
                    seen_findings,
                    "ambiguous_reference",
                    source,
                    reference,
                    tuple(candidates),
                )
                continue

            target = candidates[0]
            relationship = reference.relationship or relationship_for_reference(
                reference.hint,
                target.type,
            )
            link_source, link_target = (
                (target.id, source.id)
                if reference.reverse
                else (source.id, target.id)
            )
            semantic_key = (
                link_source,
                link_target,
                relationship,
                reference.origin,
            )
            if semantic_key in seen_links:
                continue
            seen_links.add(semantic_key)
            result.links.append(
                GraphLink(
                    id=_stable_id(
                        "link",
                        source.snapshotId,
                        link_source,
                        link_target,
                        relationship,
                        reference.origin,
                    ),
                    source=link_source,
                    target=link_target,
                    relationship=relationship,
                    confidence="high",
                    metadata={
                        "reference": reference.value,
                        "hint": reference.hint,
                        "origin": reference.origin,
                        **(
                            {"expectedType": reference.expected_type}
                            if reference.expected_type
                            else {}
                        ),
                    },
                )
            )

        return result

    def build_links(self) -> list[GraphLink]:
        """Compatibility helper for callers that only need resolved links."""

        return self.resolve().links

    def _build_index(self) -> dict[tuple[str, str], list[GraphNode]]:
        index: dict[tuple[str, str], list[GraphNode]] = {}
        for node in self.nodes:
            values = [node.label]
            source_id = node.metadata.get("sourceId")
            if source_id:
                values.append(str(source_id))
            for value in values:
                key = (node.snapshotId, normalize_identity(value))
                bucket = index.setdefault(key, [])
                if not any(existing.id == node.id for existing in bucket):
                    bucket.append(node)
        return index

    @staticmethod
    def _candidates(
        reference: ReferenceCandidate,
        snapshot_id: str,
        index: dict[tuple[str, str], list[GraphNode]],
    ) -> list[GraphNode]:
        candidates = index.get(
            (snapshot_id, normalize_identity(reference.value)),
            [],
        )
        if reference.expected_type:
            candidates = [
                candidate
                for candidate in candidates
                if candidate.type == reference.expected_type
            ]
        return sorted(candidates, key=lambda candidate: candidate.id)

    @staticmethod
    def _append_finding(
        result: ResolutionResult,
        seen: set[tuple[str, str, str, str]],
        code: str,
        source: GraphNode,
        reference: ReferenceCandidate,
        candidates: tuple[GraphNode, ...],
    ) -> None:
        semantic_key = (
            code,
            source.id,
            reference.value.casefold(),
            reference.origin,
        )
        if semantic_key in seen:
            return
        seen.add(semantic_key)

        candidate_ids = tuple(candidate.id for candidate in candidates)
        expected = reference.expected_type or "graph object"
        if code == "missing_reference":
            message = f"Missing {expected} reference: {reference.value}"
        else:
            message = f"Ambiguous {expected} reference: {reference.value}"
        result.findings.append(
            ValidationFinding(
                id=_stable_id(
                    "finding",
                    source.snapshotId,
                    source.id,
                    code,
                    reference.value,
                    reference.origin,
                    *candidate_ids,
                ),
                code=code,
                severity="error",
                snapshotId=source.snapshotId,
                nodeIds=(source.id, *candidate_ids),
                message=message,
                details={
                    "reference": reference.value,
                    "hint": reference.hint,
                    "origin": reference.origin,
                    **(
                        {"expectedType": reference.expected_type}
                        if reference.expected_type
                        else {}
                    ),
                    **(
                        {"candidateNodeIds": list(candidate_ids)}
                        if candidate_ids
                        else {}
                    ),
                },
            )
        )


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def normalize_ref(value: str) -> str:
    return normalize_identity(value)


def preferred_type_for_hint(hint: str) -> str | None:
    return expected_type_for_hint(hint)


def relationship_for_hint(hint: str, target_type: str) -> str:
    return relationship_for_reference(hint, target_type)
