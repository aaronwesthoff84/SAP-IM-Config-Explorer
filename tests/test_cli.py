from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sap_im_config_graph_explorer.cli import (
    EXIT_CLEAN,
    EXIT_PROCESSING_ERROR,
    EXIT_VALIDATION_ERROR,
    EXIT_VALIDATION_WARNING,
    discover_files,
    format_console,
    format_json,
    format_markdown,
    main,
    validate_batch,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_discover_files_explicit_and_deduplication():
    f1 = FIXTURES / "minimal_plan.xml"
    f2 = FIXTURES / "pipeline_known_order.xml"
    discovered = discover_files([f1, f2, f1])
    assert len(discovered) == 2
    assert f1.resolve() in discovered
    assert f2.resolve() in discovered


def test_discover_files_directory_flat_vs_recursive(tmp_path: Path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    (tmp_path / "root1.xml").write_text("<DATA_IMPORT/>", encoding="utf-8")
    (tmp_path / "root2.xml").write_text("<DATA_IMPORT/>", encoding="utf-8")
    (sub / "nested.xml").write_text("<DATA_IMPORT/>", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("not xml", encoding="utf-8")

    flat = discover_files([tmp_path], recursive=False)
    assert len(flat) == 2
    assert all(f.parent == tmp_path.resolve() for f in flat)

    recursive = discover_files([tmp_path], recursive=True)
    assert len(recursive) == 3
    assert (sub / "nested.xml").resolve() in recursive


def test_discover_files_nonexistent_and_bad_extension(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        discover_files([tmp_path / "does_not_exist.xml"])

    bad_ext = tmp_path / "file.csv"
    bad_ext.write_text("a,b,c", encoding="utf-8")
    with pytest.raises(ValueError, match="Only .xml files are supported"):
        discover_files([bad_ext])


def test_cli_single_clean_file_exit_zero(capsys):
    clean_file = FIXTURES / "minimal_plan.xml"
    code = main([str(clean_file)])
    assert code == EXIT_CLEAN
    captured = capsys.readouterr()
    assert "Files Scanned: 1" in captured.out
    assert "CLEAN" in captured.out


def test_cli_validation_warning_and_fail_on_warning(tmp_path: Path):
    # XML with an unused rule (warning)
    warn_xml = tmp_path / "warn.xml"
    warn_xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT VERSION="16.0">
  <RULE_SET>
    <RULE ID="R-UNUSED" NAME="Unused Standalone Rule" TYPE="COMMISSION" />
  </RULE_SET>
</DATA_IMPORT>""",
        encoding="utf-8",
    )

    # Without --fail-on-warning -> EXIT_CLEAN
    code_default = main([str(warn_xml)])
    assert code_default == EXIT_CLEAN

    # With --fail-on-warning -> EXIT_VALIDATION_WARNING
    code_warn = main([str(warn_xml), "--fail-on-warning"])
    assert code_warn == EXIT_VALIDATION_WARNING


def test_cli_validation_error_exit_code_one(tmp_path: Path):
    # XML with a broken reference (error)
    err_xml = tmp_path / "err.xml"
    err_xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<DATA_IMPORT VERSION="16.0">
  <PLAN_SET>
    <PLAN NAME="Broken Plan">
      <COMPONENT_REF NAME="NonExistentComponent" />
    </PLAN>
  </PLAN_SET>
</DATA_IMPORT>""",
        encoding="utf-8",
    )

    code = main([str(err_xml)])
    assert code == EXIT_VALIDATION_ERROR


def test_cli_partial_failure_does_not_hide_valid_results(tmp_path: Path, capsys):
    valid_xml = tmp_path / "valid.xml"
    valid_xml.write_text((FIXTURES / "minimal_plan.xml").read_text(encoding="utf-8"), encoding="utf-8")

    malformed_xml = tmp_path / "corrupt.xml"
    malformed_xml.write_text("<DATA_IMPORT>unclosed tag", encoding="utf-8")

    code = main([str(tmp_path), "--format=json"])
    assert code == EXIT_VALIDATION_ERROR

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["summary"]["totalFiles"] == 2
    assert payload["summary"]["cleanFiles"] == 1
    assert payload["summary"]["failedFiles"] == 1

    file_statuses = {f["sourceFile"]: f["status"] for f in payload["files"]}
    assert file_statuses["valid.xml"] == "clean"
    assert file_statuses["corrupt.xml"] == "failed"


def test_cli_json_and_markdown_output_to_file(tmp_path: Path):
    f1 = FIXTURES / "minimal_plan.xml"
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"

    code_json = main([str(f1), "--format=json", "--output", str(out_json)])
    assert code_json == EXIT_CLEAN
    assert out_json.exists()

    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert "summary" in data
    assert "files" in data
    assert data["summary"]["totalFiles"] == 1

    code_md = main([str(f1), "--format=markdown", "--output", str(out_md)])
    assert code_md == EXIT_CLEAN
    assert out_md.exists()
    md_text = out_md.read_text(encoding="utf-8")
    assert "# SAP IM Config Explorer: Batch Validation Report" in md_text
    assert "CLEAN" in md_text


def test_cli_combined_mode(tmp_path: Path, capsys):
    f1 = FIXTURES / "minimal_plan.xml"
    f2 = FIXTURES / "pipeline_known_order.xml"

    code = main([str(f1), str(f2), "--combined"])
    assert code == EXIT_CLEAN
    captured = capsys.readouterr()
    assert "Files Scanned: 2" in captured.out


def test_cli_module_execution_via_subprocess():
    f1 = FIXTURES / "minimal_plan.xml"
    cmd = [sys.executable, "-m", "sap_im_config_graph_explorer.cli", str(f1), "--format=json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == EXIT_CLEAN
    payload = json.loads(proc.stdout)
    assert payload["summary"]["totalFiles"] == 1


def test_sap_im_transformer_preserved(tmp_path: Path):
    # Verify sap_im_transformer.py continues to work unchanged
    out_html = tmp_path / "test.html"
    cmd = [
        sys.executable,
        "sap_im_transformer.py",
        str(FIXTURES / "minimal_plan.xml"),
        str(out_html),
        "--variant=A",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert out_html.exists()
    assert "Enterprise Plan" in out_html.read_text(encoding="utf-8")
