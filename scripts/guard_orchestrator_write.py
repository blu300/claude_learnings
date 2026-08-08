#!/usr/bin/env python3
"""Block the orchestrator from writing anything except its two files.

The orchestrator may write exactly:

    docs/1/clarification.md    (the Answers section, after asking the human)
    docs/1/brief-snapshot.md   (the frozen copy of the brief, once, at start)

Both live in docs/1 only — clarification never moves to a later iteration,
and the snapshot is taken once. `docs/.current_iteration` is written by
scripts/iteration.py itself, so the orchestrator has no reason to touch it.

Paths are anchored to the project root (CLAUDE_PROJECT_DIR, or the working
directory outside a harness): a lookalike path elsewhere on disk that merely
ends in docs/1/clarification.md is refused.

KNOWN LIMIT: this guard watches the Write and Edit tools. The orchestrator is
a skill running in the main session, which also has Bash — a route this guard
does not see. That gap is documented and deliberately kept; see "The
coordinator's shell" in docs/learning/GUIDE.md.
"""

import json
import os
import sys
from pathlib import Path

import hook_audit

ALLOW = 0
BLOCK = 2

ALLOWED = ("clarification.md", "brief-snapshot.md")


def project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()


def is_allowed(path: str, root: Path) -> bool:
    """True only for <root>/docs/1/clarification.md or brief-snapshot.md."""
    candidate = Path(path.replace("\\", "/"))
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.resolve().relative_to(root)
    except ValueError:
        return False  # outside the project
    return relative.parts[:2] == ("docs", "1") and (
        len(relative.parts) == 3 and relative.parts[2] in ALLOWED
    )


def main() -> int:
    try:
        call = json.load(sys.stdin)
        path = call["tool_input"]["file_path"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("Blocked: could not read file path from tool call.", file=sys.stderr)
        return BLOCK

    root = project_root()
    if is_allowed(path, root):
        hook_audit.record("guard_orchestrator_write", "allow", path)
        return ALLOW

    hook_audit.record("guard_orchestrator_write", "block", path)
    print(
        f"Blocked: orchestrator may only write docs/1/clarification.md or "
        f"docs/1/brief-snapshot.md. Refused: {path}",
        file=sys.stderr,
    )
    return BLOCK


if __name__ == "__main__":
    raise SystemExit(main())
