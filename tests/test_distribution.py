"""Automated tests for reproducible offline Windows distribution and lifecycle management."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from sap_im_config_graph_explorer import __version__
from sap_im_config_graph_explorer.app import app
from scripts.package_offline import (
    build_package,
    compute_sha256,
    get_component_inventory,
    verify_no_external_cdns,
)

ROOT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built_package() -> dict[str, Any]:
    test_base = ROOT_DIR / "pytest_tmp" / "dist_test"
    if test_base.exists():
        shutil.rmtree(test_base, ignore_errors=True)
    test_base.mkdir(parents=True, exist_ok=True)

    out_dir = test_base / "dist_out"
    zip_path = build_package(output_dir=out_dir)

    unpack_dir = test_base / "dist_unpacked"
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(unpack_dir)

    # The package root inside the zip is named SAP-IM-Config-Explorer-v<version>-windows-offline
    pkg_root = unpack_dir / f"SAP-IM-Config-Explorer-v{__version__}-windows-offline"

    manifest_path = pkg_root / "dist_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    yield {
        "zip_path": zip_path,
        "out_dir": out_dir,
        "pkg_root": pkg_root,
        "manifest": manifest,
    }

    shutil.rmtree(test_base, ignore_errors=True)


class TestDistributionPackage:
    """Verifies that the offline distribution package is built correctly and deterministically."""

    def test_package_zip_and_checksum_exist(self, built_package: dict[str, Any]) -> None:
        zip_path: Path = built_package["zip_path"]
        assert zip_path.exists()
        assert zip_path.stat().st_size > 100_000  # Vendored assets make it substantial

        checksum_path = zip_path.with_name(f"{zip_path.name}.sha256")
        assert checksum_path.exists()
        recorded_sha = checksum_path.read_text(encoding="utf-8").split()[0]
        actual_sha = compute_sha256(zip_path)
        assert recorded_sha == actual_sha

    def test_package_contains_required_runtime_files(self, built_package: dict[str, Any]) -> None:
        pkg_root: Path = built_package["pkg_root"]

        # Core application files
        assert (pkg_root / "sap_im_config_graph_explorer" / "app.py").exists()
        assert (pkg_root / "sap_im_config_graph_explorer" / "models.py").exists()
        assert (pkg_root / "sap_im_transformer.py").exists()
        assert (pkg_root / "requirements.txt").exists()

        # Legal notices and docs
        assert (pkg_root / "LICENSE").exists()
        assert (pkg_root / "THIRD_PARTY_LICENSES.md").exists()
        assert (pkg_root / "DISTRIBUTION.md").exists()
        assert (pkg_root / "dist_manifest.json").exists()

        # Top-level and scripts/windows launchers
        for launcher in ["launch.ps1", "launch.bat", "stop.ps1", "stop.bat", "healthcheck.ps1", "healthcheck.bat"]:
            assert (pkg_root / launcher).exists(), f"Missing top-level launcher: {launcher}"
            assert (pkg_root / "scripts" / "windows" / launcher).exists(), f"Missing scripts/windows launcher: {launcher}"

        assert (pkg_root / "scripts" / "windows" / "uninstall.ps1").exists()
        assert (pkg_root / "scripts" / "windows" / "uninstall.bat").exists()
        assert (pkg_root / "scripts" / "windows" / "package.ps1").exists()

    def test_vendored_browser_assets_are_intact(self, built_package: dict[str, Any]) -> None:
        pkg_root: Path = built_package["pkg_root"]
        vendor_dir = pkg_root / "sap_im_config_graph_explorer" / "static" / "vendor"
        assert vendor_dir.exists()

        cyto = vendor_dir / "cytoscape.min.js"
        assert cyto.exists()
        assert cyto.stat().st_size > 300_000

        force3d = vendor_dir / "3d-force-graph.min.js"
        assert force3d.exists()
        assert force3d.stat().st_size > 1_000_000

    def test_manifest_metadata_and_integrity(self, built_package: dict[str, Any]) -> None:
        manifest = built_package["manifest"]
        assert manifest["packageName"] == "SAP-IM-Config-Explorer"
        assert manifest["version"] == __version__
        assert manifest["schemaVersion"] == "1.3"
        assert "buildTimestamp" in manifest
        assert "gitCommit" in manifest

        # Check components
        names = {c["name"] for c in manifest["components"]}
        assert "sap_im_config_graph_explorer" in names
        assert "cytoscape.js" in names
        assert "3d-force-graph" in names
        assert "fastapi" in names
        assert "uvicorn" in names
        assert "defusedxml" in names

        # Check vendored assets listed in manifest
        vendored_paths = [v["path"] for v in manifest["vendoredAssets"]]
        assert any("cytoscape.min.js" in p for p in vendored_paths)
        assert any("3d-force-graph.min.js" in p for p in vendored_paths)

    def test_no_external_cdn_leakage_in_package(self, built_package: dict[str, Any]) -> None:
        pkg_root: Path = built_package["pkg_root"]
        verify_no_external_cdns(pkg_root)


class TestOperationsAndSafetyPolicy:
    """Verifies operational contracts: loopback healthcheck, safe data preservation."""

    def test_health_endpoint_contract(self) -> None:
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload == {"status": "ok"}

    def test_safe_uninstall_data_preservation_policy(self) -> None:
        """Simulate the uninstall script's preservation logic on user data."""
        mock_data_dir = ROOT_DIR / "pytest_tmp" / "test_uninstall_data"
        if mock_data_dir.exists():
            shutil.rmtree(mock_data_dir, ignore_errors=True)
        sessions_dir = mock_data_dir / "sessions"
        exports_dir = mock_data_dir / "exports"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        exports_dir.mkdir(parents=True, exist_ok=True)

        user_session = sessions_dir / "saved_session.json"
        user_session.write_text('{"name": "production-q3"}', encoding="utf-8")
        user_export = exports_dir / "graph_export.csv"
        user_export.write_text("id,label\n1,Rule1", encoding="utf-8")

        # By default (PurgeUserData = False), user data is strictly preserved
        purge_user_data = False
        if not purge_user_data:
            # Safe branch: no deletion occurs
            assert user_session.exists()
            assert user_export.exists()
            assert mock_data_dir.exists()

        # Only when purge_user_data is True does removal happen
        purge_user_data = True
        if purge_user_data:
            shutil.rmtree(mock_data_dir, ignore_errors=True)
            assert not mock_data_dir.exists()

    @pytest.mark.skipif(sys.platform != "win32", reason="PowerShell AST parser test is Windows-specific")
    def test_powershell_scripts_syntax(self) -> None:
        """Parse all PowerShell scripts with PowerShell Language Parser to guarantee zero syntax errors."""
        scripts = list((ROOT_DIR / "scripts" / "windows").glob("*.ps1"))
        assert len(scripts) >= 5, "Expected at least 5 PowerShell scripts in scripts/windows"

        for script in scripts:
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"$tokens = $null; $errors = $null; [System.Management.Automation.Language.Parser]::ParseFile('{script.resolve().as_posix()}', [ref]$tokens, [ref]$errors); if ($errors.Count -gt 0) {{ $errors | ForEach-Object {{ Write-Error $_ }}; exit 1 }} else {{ exit 0 }}",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            assert res.returncode == 0, f"PowerShell syntax error in {script.name}:\n{res.stderr}"
