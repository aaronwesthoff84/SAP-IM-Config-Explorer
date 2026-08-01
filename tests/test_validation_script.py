import os
import sys
from pathlib import Path

from scripts.validate import ROOT, build_commands, run_commands


def test_ci_mode_contains_required_checks():
    rendered = [" ".join(command) for command in build_commands("ci")]
    assert any("pytest" in command for command in rendered)
    assert any("node --check sap_im_config_graph_explorer/static/app.js" in command for command in rendered)
    assert any("sap_im_transformer.py" in command for command in rendered)
    assert not any("test:e2e" in command for command in rendered)


def test_pytest_uses_repository_local_base_temp():
    pytest_command = build_commands("ci")[0]

    option_index = pytest_command.index("--basetemp")
    assert pytest_command[option_index + 1] == str(
        ROOT / ".validation-output" / "pytest-temp"
    )


def test_full_mode_contains_browser_checks():
    rendered = [
        " ".join(command)
        for command in build_commands("full", platform_name="posix")
    ]
    assert any(command == "npm ci" for command in rendered)
    assert any("npm run test:e2e" in command for command in rendered)


def test_full_mode_uses_directly_executable_npm_shim_on_windows():
    rendered = [
        " ".join(command) for command in build_commands("full", platform_name="nt")
    ]

    assert "npm.cmd ci" in rendered
    assert "npm.cmd run test:e2e" in rendered


def test_runner_returns_first_failure(monkeypatch):
    calls = []

    class Result:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(command, **kwargs):
        calls.append(command)
        return Result(7)

    monkeypatch.setattr("scripts.validate.subprocess.run", fake_run)
    assert run_commands([["first"], ["second"]]) == 7
    assert calls == [["first"]]


def test_runner_puts_its_python_environment_first_on_path(monkeypatch):
    child_environments = []

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        child_environments.append(kwargs["env"])
        return Result()

    monkeypatch.setattr("scripts.validate.subprocess.run", fake_run)

    assert run_commands([["child"]]) == 0
    child_path = child_environments[0]["PATH"].split(os.pathsep)
    assert child_path[0] == str(Path(sys.executable).parent)
