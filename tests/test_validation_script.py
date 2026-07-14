from scripts.validate import build_commands, run_commands


def test_ci_mode_contains_required_checks():
    rendered = [" ".join(command) for command in build_commands("ci")]
    assert any("pytest" in command for command in rendered)
    assert any("node --check sap_im_config_graph_explorer/static/app.js" in command for command in rendered)
    assert any("sap_im_transformer.py" in command for command in rendered)
    assert not any("test:e2e" in command for command in rendered)


def test_full_mode_contains_browser_checks():
    rendered = [" ".join(command) for command in build_commands("full")]
    assert any(command == "npm ci" for command in rendered)
    assert any("npm run test:e2e" in command for command in rendered)


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
