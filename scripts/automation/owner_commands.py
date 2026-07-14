from __future__ import annotations

from dataclasses import dataclass

OWNER = "aaronwesthoff84"
COMMANDS = {"approve", "request-changes", "retry", "block", "cancel", "needs-details", "ready", "pause", "resume"}


@dataclass(frozen=True)
class OwnerCommand:
    name: str
    argument: str = ""


def parse_owner_command(author: str, body: str) -> OwnerCommand | None:
    if author != OWNER:
        return None
    line = body.strip().splitlines()[0] if body.strip() else ""
    if not line.startswith("/"):
        return None
    name, _, argument = line[1:].partition(" ")
    if name not in COMMANDS:
        return None
    if name in {"request-changes", "block"} and not argument.strip():
        return None
    return OwnerCommand(name, argument.strip())
