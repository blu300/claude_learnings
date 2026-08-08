#!/usr/bin/env python3
"""Block the orchestrator from writing anything except clarification.md,
brief-snapshot.md, and .current_iteration."""

import json
import sys
from pathlib import PurePosixPath

ALLOW = 0
BLOCK = 2


def is_allowed(path: str) -> bool:
    normalized = PurePosixPath(path.replace("\\", "/"))

    if normalized.name == ".current_iteration" and normalized.parent.name == "docs":
        return True

    if normalized.name == "brief-snapshot.md":
        if normalized.parent.name == "1" and normalized.parent.parent.name == "docs":
            return True

    if normalized.name == "clarification.md":
        if normalized.parent.name.isdigit() and normalized.parent.parent.name == "docs":
            return True

    return False


def main() -> int:
    try:
        call = json.load(sys.stdin)
        path = call["tool_input"]["file_path"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("Blocked: could not read file path from tool call.", file=sys.stderr)
        return BLOCK

    if is_allowed(path):
        return ALLOW

    print(
        f"Blocked: orchestrator may only write clarification.md, "
        f"brief-snapshot.md, or .current_iteration. Refused: {path}",
        file=sys.stderr,
    )
    return BLOCK


if __name__ == "__main__":
    raise SystemExit(main())
