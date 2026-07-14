from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_commands(mode: str) -> list[list[str]]:
    python = sys.executable
    commands = [
        [python, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        ["node", "--check", "sap_im_config_graph_explorer/static/app.js"],
        [
            python,
            "sap_im_transformer.py",
            "tests/fixtures/minimal_plan.xml",
            str(ROOT / ".validation-output" / "minimal-plan-acceptance.html"),
            "--variant=A",
        ],
    ]
    if mode == "full":
        commands.extend([["npm", "ci"], ["npm", "run", "test:e2e"]])
    return commands


def run_commands(commands: list[list[str]]) -> int:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    (ROOT / ".validation-output").mkdir(exist_ok=True)
    first_failure = 0
    for command in commands:
        print("+", " ".join(command), flush=True)
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        if result.returncode and not first_failure:
            first_failure = result.returncode
            break
    return first_failure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("ci", "full"), default="ci")
    args = parser.parse_args()
    return run_commands(build_commands(args.mode))


if __name__ == "__main__":
    raise SystemExit(main())
