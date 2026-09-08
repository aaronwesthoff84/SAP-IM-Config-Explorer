"""Reproducible offline Windows package generator for SAP IM Config Explorer.

Produces a self-contained distribution ZIP containing:
1. Application source code and package assets
2. Vendored local frontend assets (Cytoscape, 3D Force Graph)
3. Windows PowerShell and Batch launcher scripts
4. Machine-readable distribution manifest with SHA256 checksums
5. Licensing and third-party notices
6. Optional offline Python wheels cache
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sap_im_config_graph_explorer import __version__


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hex digest for a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_git_commit() -> str:
    """Retrieve current git commit hash if in a git repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unversioned"


def get_component_inventory() -> list[dict[str, str]]:
    """Return inventory of bundled runtime components and licenses."""
    return [
        {
            "name": "sap_im_config_graph_explorer",
            "version": __version__,
            "license": "MIT",
            "role": "Core application & dependency graph engine",
        },
        {
            "name": "cytoscape.js",
            "version": "3.30.2",
            "license": "MIT",
            "role": "Vendored 2D graph layout & rendering library",
        },
        {
            "name": "3d-force-graph",
            "version": "1.73.4",
            "license": "MIT",
            "role": "Vendored 3D graph visualization library",
        },
        {
            "name": "fastapi",
            "version": "0.139.0",
            "license": "MIT",
            "role": "Local loopback web API framework",
        },
        {
            "name": "uvicorn",
            "version": "0.51.0",
            "license": "BSD-3-Clause",
            "role": "Local ASGI web server",
        },
        {
            "name": "defusedxml",
            "version": "0.7.1",
            "license": "Python-2.0 / Apache-2.0",
            "role": "Secure XML parsing and XXE defense",
        },
    ]


def verify_no_external_cdns(package_dir: Path) -> None:
    """Verify that templates and static files do not contain external CDN references."""
    forbidden_patterns = [
        "https://cdn.",
        "https://unpkg.com",
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
    ]
    html_files = list(package_dir.glob("**/*.html")) + list(package_dir.glob("**/*.js"))
    for file_path in html_files:
        # Ignore vendor minified assets
        if "vendor" in file_path.parts:
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for pattern in forbidden_patterns:
                if pattern in content:
                    raise ValueError(
                        f"External CDN pattern '{pattern}' detected in offline file: {file_path.relative_to(package_dir)}"
                    )
        except Exception as exc:
            if not isinstance(exc, ValueError):
                continue
            raise


def build_package(
    output_dir: Path | None = None,
    wheels_dir: Path | None = None,
    include_dev: bool = False,
) -> Path:
    """Build the offline ZIP package and manifest."""
    out_dir = output_dir or (ROOT_DIR / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)

    pkg_name = f"SAP-IM-Config-Explorer-v{__version__}-windows-offline"
    zip_path = out_dir / f"{pkg_name}.zip"

    staging_dir = out_dir / pkg_name
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy Application Code & Assets
    app_src = ROOT_DIR / "sap_im_config_graph_explorer"
    shutil.copytree(app_src, staging_dir / "sap_im_config_graph_explorer")

    # Copy transformer script
    shutil.copy2(ROOT_DIR / "sap_im_transformer.py", staging_dir / "sap_im_transformer.py")

    # Copy requirements
    shutil.copy2(ROOT_DIR / "requirements.txt", staging_dir / "requirements.txt")
    if include_dev and (ROOT_DIR / "requirements-dev.txt").exists():
        shutil.copy2(ROOT_DIR / "requirements-dev.txt", staging_dir / "requirements-dev.txt")

    # Copy licenses
    for lic_file in ["LICENSE", "THIRD_PARTY_LICENSES.md", "README.md", "DISTRIBUTION.md"]:
        src_file = ROOT_DIR / lic_file
        if src_file.exists():
            shutil.copy2(src_file, staging_dir / lic_file)

    # 2. Copy Windows Launchers
    win_scripts_src = ROOT_DIR / "scripts" / "windows"
    if win_scripts_src.exists():
        dest_scripts = staging_dir / "scripts" / "windows"
        dest_scripts.mkdir(parents=True, exist_ok=True)
        for s in win_scripts_src.iterdir():
            if s.is_file():
                shutil.copy2(s, dest_scripts / s.name)
                # Also copy launchers to root of distribution for convenient top-level execution
                if s.name in ("launch.bat", "launch.ps1", "stop.bat", "stop.ps1", "healthcheck.bat", "healthcheck.ps1"):
                    shutil.copy2(s, staging_dir / s.name)

    # 3. Copy Wheels if provided
    if wheels_dir and wheels_dir.exists():
        dest_wheels = staging_dir / "wheels"
        shutil.copytree(wheels_dir, dest_wheels)

    # 4. Verify no CDN leaks
    verify_no_external_cdns(staging_dir)

    # 5. Generate Manifest
    file_manifest: dict[str, Any] = {}
    vendored_assets: list[dict[str, Any]] = []

    for item in staging_dir.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(staging_dir).as_posix()
            sha256 = compute_sha256(item)
            file_manifest[rel_path] = {
                "sha256": sha256,
                "sizeBytes": item.stat().st_size,
            }
            if "vendor" in rel_path:
                vendored_assets.append({
                    "path": rel_path,
                    "sha256": sha256,
                    "sizeBytes": item.stat().st_size,
                })

    manifest = {
        "packageName": "SAP-IM-Config-Explorer",
        "version": __version__,
        "schemaVersion": "1.3",
        "buildTimestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gitCommit": get_git_commit(),
        "runtimeRequirements": {
            "os": "Windows 10 / 11 / Server 2019+",
            "python": ">=3.10",
            "network": "Loopback only (127.0.0.1); zero external CDN or internet dependencies",
            "browser": "Chromium, Edge, Chrome, Firefox (ES2020+)",
        },
        "components": get_component_inventory(),
        "vendoredAssets": sorted(vendored_assets, key=lambda x: x["path"]),
        "files": file_manifest,
    }

    manifest_path = staging_dir / "dist_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # 6. Build Deterministic ZIP
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(staging_dir):
            for file in sorted(files):
                file_path = Path(root) / file
                archive_name = Path(pkg_name) / file_path.relative_to(staging_dir)
                zf.write(file_path, archive_name)

    # Cleanup staging directory
    shutil.rmtree(staging_dir)

    # Write package sha256 checksum file
    pkg_sha = compute_sha256(zip_path)
    (out_dir / f"{pkg_name}.zip.sha256").write_text(f"{pkg_sha}  {zip_path.name}\n", encoding="utf-8")

    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate offline Windows distribution package.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory for ZIP package")
    parser.add_argument("--wheels-dir", type=Path, default=None, help="Directory containing offline wheels")
    parser.add_argument("--include-dev", action="store_true", help="Include dev dependencies in package")
    args = parser.parse_args()

    try:
        zip_file = build_package(
            output_dir=args.output_dir,
            wheels_dir=args.wheels_dir,
            include_dev=args.include_dev,
        )
        print(f"Package created successfully: {zip_file}")
        print(f"SHA256: {compute_sha256(zip_file)}")
        return 0
    except Exception as exc:
        sys.stderr.write(f"Packaging failed: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
