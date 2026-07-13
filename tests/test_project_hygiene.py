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
