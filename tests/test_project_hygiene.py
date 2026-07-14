from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def _nonblank(path: str) -> list[str]:
    return [
        line.strip()
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_dependency_versions_are_reproducible():
    assert _nonblank("requirements.txt") == [
        "fastapi==0.139.0",
        "pydantic==2.13.4",
        "pydantic-core==2.46.4",
        "python-multipart==0.0.32",
        "starlette==1.3.1",
        "uvicorn==0.51.0",
    ]
    assert _nonblank("requirements-dev.txt") == [
        "-r requirements.txt",
        "httpx==0.28.1",
        "pytest==9.1.1",
    ]


def test_python_cache_files_are_ignored_and_untracked():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout.splitlines()
    assert not [path for path in tracked if "__pycache__" in path or path.endswith(".pyc")]
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"__pycache__/", "*.py[cod]", ".pytest_cache/", ".venv/", ".superpowers/"} <= set(ignored)


def test_jules_automation_contract_files_exist():
    required = [
        "AGENTS.md",
        ".github/ISSUE_TEMPLATE/feature.yml",
        ".github/ISSUE_TEMPLATE/bug.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/pull_request_template.md",
        "docs/JULES_AUTOMATION.md",
        "scripts/validate.py",
        ".github/workflows/ci.yml",
        ".github/workflows/codeql.yml",
        ".github/workflows/dependency-review.yml",
        "playwright.config.ts",
        "tests/e2e/app-smoke.spec.ts",
    ]
    assert not [path for path in required if not (ROOT / path).is_file()]

    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for required_text in (
        "local-first",
        "strict graph node allowlist",
        "snapshot-scoped",
        "one primary GitHub Issue per pull request",
        "Do not hide or suppress failures",
    ):
        assert required_text in agents


def test_workflows_use_safe_pull_request_permissions():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    codeql = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
    dependency = (ROOT / ".github/workflows/dependency-review.yml").read_text(encoding="utf-8")

    assert "pull_request:" in ci
    assert "branches: [master]" in ci
    assert "contents: read" in ci
    assert "python scripts/validate.py --mode ci" in ci
    assert "pull_request_target" not in ci + codeql + dependency
    assert "security-events: write" in codeql
    assert "fail-on-severity: high" in dependency
