"""Reusable command-line workflow for batch validating SAP Incentive Management XML exports."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.models import ValidationFinding
from sap_im_config_graph_explorer.xml_loader import XmlLoadError

# Deterministic Exit Codes
EXIT_CLEAN = 0
EXIT_VALIDATION_ERROR = 1
EXIT_VALIDATION_WARNING = 2
EXIT_PROCESSING_ERROR = 3


@dataclass
class FileValidationResult:
    source_file: str
    relative_path: str
    status: str  # "clean", "warnings", "errors", "failed"
    node_count: int = 0
    link_count: int = 0
    findings: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceFile": self.source_file,
            "relativePath": self.relative_path,
            "status": self.status,
            "nodeCount": self.node_count,
            "linkCount": self.link_count,
            "findings": self.findings,
            "errorMessage": self.error_message,
        }


@dataclass
class BatchValidationSummary:
    total_files: int = 0
    clean_files: int = 0
    warning_files: int = 0
    error_files: int = 0
    failed_files: int = 0
    total_findings: int = 0
    errors_count: int = 0
    warnings_count: int = 0
    info_count: int = 0
    exit_code: int = EXIT_CLEAN

    def to_dict(self) -> dict[str, Any]:
        return {
            "totalFiles": self.total_files,
            "cleanFiles": self.clean_files,
            "warningFiles": self.warning_files,
            "errorFiles": self.error_files,
            "failedFiles": self.failed_files,
            "totalFindings": self.total_findings,
            "errorsCount": self.errors_count,
            "warningsCount": self.warnings_count,
            "infoCount": self.info_count,
            "exitCode": self.exit_code,
        }


def discover_files(targets: list[str | Path], recursive: bool = False) -> list[Path]:
    """Discover XML files from explicit paths and directories deterministically.

    Recursion Policy:
    - If a path points to an individual file, it is included if it has a .xml extension.
    - If a path points to a directory:
        - recursive=False: inspects only direct child .xml files in that directory.
        - recursive=True: walks all subdirectories recursively finding all .xml files.
    - Files are returned sorted deterministically by normalized resolved path.
    - Duplicate paths are deduplicated.
    """
    found: set[Path] = set()
    for target in targets:
        p = Path(target)
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {target}")
        if p.is_file():
            if p.suffix.lower() == ".xml":
                found.add(p.resolve())
            else:
                raise ValueError(f"Unsupported file type: {p.name}. Only .xml files are supported.")
        elif p.is_dir():
            pattern = "**/*.xml" if recursive else "*.xml"
            for match in p.glob(pattern):
                if match.is_file():
                    found.add(match.resolve())
    return sorted(found, key=lambda f: f.as_posix().casefold())


def validate_batch(
    files: list[Path],
    topology_mode: str = "core",
    fail_on_warning: bool = False,
    combined: bool = False,
    base_dir: Path | None = None,
) -> tuple[list[FileValidationResult], BatchValidationSummary]:
    """Validate a batch of discovered XML files with deterministic reporting."""
    builder = GraphBuilder(topology_mode=topology_mode)
    results: list[FileValidationResult] = []

    clean_files = 0
    warning_files = 0
    error_files = 0
    failed_files = 0
    total_errors = 0
    total_warnings = 0
    total_info = 0

    if combined:
        # Build unified multi-file graph
        try:
            doc = builder.build_from_paths(files)
            findings_dicts = [f.to_dict() for f in doc.findings]
            errors = sum(1 for f in doc.findings if f.severity == "error")
            warnings = sum(1 for f in doc.findings if f.severity == "warning")
            info = sum(1 for f in doc.findings if f.severity == "info")

            status = "clean"
            if errors > 0:
                status = "errors"
                error_files = len(files)
            elif warnings > 0:
                status = "warnings"
                warning_files = len(files)
            else:
                clean_files = len(files)

            total_errors += errors
            total_warnings += warnings
            total_info += info

            for file_path in files:
                rel_path = (
                    file_path.relative_to(base_dir).as_posix()
                    if base_dir and file_path.is_relative_to(base_dir)
                    else file_path.name
                )
                file_findings = [f for f in findings_dicts if f.get("sourceFile") == file_path.name]
                results.append(
                    FileValidationResult(
                        source_file=file_path.name,
                        relative_path=rel_path,
                        status=status,
                        node_count=len(doc.nodes),
                        link_count=len(doc.links),
                        findings=file_findings,
                    )
                )
        except Exception as exc:
            failed_files = len(files)
            for file_path in files:
                rel_path = (
                    file_path.relative_to(base_dir).as_posix()
                    if base_dir and file_path.is_relative_to(base_dir)
                    else file_path.name
                )
                results.append(
                    FileValidationResult(
                        source_file=file_path.name,
                        relative_path=rel_path,
                        status="failed",
                        error_message=str(exc),
                    )
                )
    else:
        # Per-file isolated validation
        for file_path in files:
            rel_path = (
                file_path.relative_to(base_dir).as_posix()
                if base_dir and file_path.is_relative_to(base_dir)
                else file_path.name
            )
            try:
                doc = builder.build_from_paths([file_path])
                findings_dicts = [f.to_dict() for f in doc.findings]
                errors = sum(1 for f in doc.findings if f.severity == "error")
                warnings = sum(1 for f in doc.findings if f.severity == "warning")
                info = sum(1 for f in doc.findings if f.severity == "info")

                total_errors += errors
                total_warnings += warnings
                total_info += info

                if errors > 0:
                    status = "errors"
                    error_files += 1
                elif warnings > 0:
                    status = "warnings"
                    warning_files += 1
                else:
                    status = "clean"
                    clean_files += 1

                results.append(
                    FileValidationResult(
                        source_file=file_path.name,
                        relative_path=rel_path,
                        status=status,
                        node_count=len(doc.nodes),
                        link_count=len(doc.links),
                        findings=findings_dicts,
                    )
                )
            except Exception as exc:
                failed_files += 1
                error_msg = str(exc)
                finding_err = {
                    "id": f"processing-err-{file_path.name}",
                    "code": "XML_PARSE_ERROR",
                    "severity": "error",
                    "snapshotId": "configuration",
                    "nodeIds": [],
                    "message": f"Processing failure: {error_msg}",
                    "details": {"exception": type(exc).__name__},
                    "sourceFile": file_path.name,
                }
                total_errors += 1
                results.append(
                    FileValidationResult(
                        source_file=file_path.name,
                        relative_path=rel_path,
                        status="failed",
                        error_message=error_msg,
                        findings=[finding_err],
                    )
                )

    total_findings = total_errors + total_warnings + total_info

    # Determine exit code
    if failed_files > 0 and clean_files == 0 and warning_files == 0 and error_files == 0 and total_errors == failed_files:
        exit_code = EXIT_PROCESSING_ERROR
    elif total_errors > 0 or failed_files > 0:
        exit_code = EXIT_VALIDATION_ERROR
    elif total_warnings > 0 and fail_on_warning:
        exit_code = EXIT_VALIDATION_WARNING
    else:
        exit_code = EXIT_CLEAN

    summary = BatchValidationSummary(
        total_files=len(files),
        clean_files=clean_files,
        warning_files=warning_files,
        error_files=error_files,
        failed_files=failed_files,
        total_findings=total_findings,
        errors_count=total_errors,
        warnings_count=total_warnings,
        info_count=total_info,
        exit_code=exit_code,
    )

    return results, summary


def format_console(results: list[FileValidationResult], summary: BatchValidationSummary) -> str:
    lines: list[str] = []
    lines.append("=======================================================")
    lines.append("       SAP IM Config Explorer - Batch Validation       ")
    lines.append("=======================================================")
    lines.append(
        f"Files Scanned: {summary.total_files} | "
        f"Clean: {summary.clean_files} | "
        f"Warnings: {summary.warning_files} | "
        f"Errors: {summary.error_files} | "
        f"Failed: {summary.failed_files}"
    )
    lines.append(
        f"Findings Breakdown: {summary.errors_count} error(s), "
        f"{summary.warnings_count} warning(s), "
        f"{summary.info_count} info"
    )
    lines.append("-------------------------------------------------------")

    for res in results:
        status_tag = res.status.upper()
        if res.status == "clean":
            status_line = f"[PASS] {res.relative_path} ({res.node_count} nodes, {res.link_count} links)"
        elif res.status == "failed":
            status_line = f"[FAIL] {res.relative_path}: {res.error_message}"
        else:
            status_line = f"[{status_tag}] {res.relative_path} ({len(res.findings)} finding(s))"
        lines.append(status_line)

        for finding in res.findings:
            sev = finding.get("severity", "info").upper()
            code = finding.get("code", "FINDING")
            msg = finding.get("message", "")
            node_ids = finding.get("nodeIds", [])
            node_str = f" [Objects: {', '.join(node_ids)}]" if node_ids else ""
            lines.append(f"   -> [{sev}] {code}: {msg}{node_str}")

    lines.append("-------------------------------------------------------")
    outcome_str = {
        EXIT_CLEAN: "CLEAN - No validation errors detected.",
        EXIT_VALIDATION_ERROR: "FAILED - Validation errors detected.",
        EXIT_VALIDATION_WARNING: "WARNING - Validation warnings detected.",
        EXIT_PROCESSING_ERROR: "ERROR - File processing or I/O failure.",
    }.get(summary.exit_code, "UNKNOWN")
    lines.append(f"Outcome: {outcome_str} (Exit Code: {summary.exit_code})")
    lines.append("=======================================================")
    return "\n".join(lines)


def format_json(results: list[FileValidationResult], summary: BatchValidationSummary) -> str:
    all_findings = []
    for r in results:
        for f in r.findings:
            f_copy = dict(f)
            if "sourceFile" not in f_copy:
                f_copy["sourceFile"] = r.source_file
            all_findings.append(f_copy)

    payload = {
        "summary": summary.to_dict(),
        "files": [r.to_dict() for r in results],
        "findings": all_findings,
    }
    return json.dumps(payload, indent=2)


def format_markdown(results: list[FileValidationResult], summary: BatchValidationSummary) -> str:
    lines: list[str] = []
    lines.append("# SAP IM Config Explorer: Batch Validation Report\n")
    lines.append("## Summary\n")
    lines.append("| Metric | Count |")
    lines.append("|---|---|")
    lines.append(f"| **Total Files** | {summary.total_files} |")
    lines.append(f"| **Clean Files** | {summary.clean_files} |")
    lines.append(f"| **Files with Warnings** | {summary.warning_files} |")
    lines.append(f"| **Files with Errors** | {summary.error_files} |")
    lines.append(f"| **Failed / Corrupt Files** | {summary.failed_files} |")
    lines.append(f"| **Total Errors** | {summary.errors_count} |")
    lines.append(f"| **Total Warnings** | {summary.warnings_count} |")
    lines.append(f"| **Exit Code** | {summary.exit_code} |\n")

    lines.append("## File Details\n")
    for res in results:
        status_badge = {
            "clean": "✅ `CLEAN`",
            "warnings": "⚠️ `WARNING`",
            "errors": "❌ `ERROR`",
            "failed": "⛔ `FAILED`",
        }.get(res.status, res.status)

        lines.append(f"### {res.relative_path} — {status_badge}\n")
        if res.status == "failed":
            lines.append(f"> **Processing Error:** {res.error_message}\n")
        else:
            lines.append(f"- **Nodes:** {res.node_count}")
            lines.append(f"- **Links:** {res.link_count}")
            lines.append(f"- **Findings:** {len(res.findings)}\n")

        if res.findings:
            lines.append("| Severity | Code | Message | Objects |")
            lines.append("|---|---|---|---|")
            for f in res.findings:
                sev = f.get("severity", "").upper()
                code = f.get("code", "")
                msg = f.get("message", "").replace("|", "\\|")
                nodes = ", ".join(f.get("nodeIds", []))
                lines.append(f"| `{sev}` | `{code}` | {msg} | {nodes} |")
            lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m sap_im_config_graph_explorer.cli",
        description="Deterministic command-line batch validation and reporting for SAP IM XML exports.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more XML file paths or directories to validate.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively discover .xml files in specified directories.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["console", "json", "markdown"],
        default="console",
        help="Report format: console (default), json, or markdown.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Write report output to specified file instead of stdout.",
    )
    parser.add_argument(
        "-w",
        "--fail-on-warning",
        action="store_true",
        help="Exit with code 2 if validation warnings are present.",
    )
    parser.add_argument(
        "-t",
        "--topology",
        choices=["core", "full"],
        default="core",
        help="Graph topology mode (default: core).",
    )
    parser.add_argument(
        "-c",
        "--combined",
        action="store_true",
        help="Validate all input files together in a unified multi-file graph.",
    )
    return parser


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    try:
        files = discover_files(parsed.paths, recursive=parsed.recursive)
    except FileNotFoundError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return EXIT_PROCESSING_ERROR
    except ValueError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return EXIT_PROCESSING_ERROR

    if not files:
        sys.stderr.write("Error: No XML files found matching specified paths.\n")
        return EXIT_PROCESSING_ERROR

    base_dir = Path(parsed.paths[0]) if len(parsed.paths) == 1 and Path(parsed.paths[0]).is_dir() else None

    results, summary = validate_batch(
        files,
        topology_mode=parsed.topology,
        fail_on_warning=parsed.fail_on_warning,
        combined=parsed.combined,
        base_dir=base_dir,
    )

    if parsed.format == "json":
        output_text = format_json(results, summary)
    elif parsed.format == "markdown":
        output_text = format_markdown(results, summary)
    else:
        output_text = format_console(results, summary)

    if parsed.output:
        out_path = Path(parsed.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
    else:
        print(output_text)

    return summary.exit_code


if __name__ == "__main__":
    sys.exit(main())
