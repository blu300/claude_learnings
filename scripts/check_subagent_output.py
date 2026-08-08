#!/usr/bin/env python3
"""SubagentStop hook: when a delegated agent finishes, check that it left
some output in the current iteration folder.

This mechanises the prose rule in SKILL.md: "If an agent fails to write its
file, report the failure and stop."

Two things make this different from the guard_*.py scripts:

1. It runs on the SubagentStop event, not PreToolUse. It fires when a
   subagent finishes, not around a tool call. So it gets NO file_path in
   its input — it cannot know which file the agent was meant to write. The
   check is therefore coarse: did the agent leave *anything* in the current
   iteration folder? (See "What this does not catch" below.)

2. It reports back with JSON on stdout instead of exit code 2. Returning
   {"decision": "block", "reason": "..."} tells the orchestrator the
   subagent stopped without producing output and passes a message back,
   which is richer than a bare non-zero exit.
"""

import json
import sys
from pathlib import Path


def find_current_folder() -> Path | None:
    """The orchestrator writes the active iteration number to
    docs/.current_iteration before each delegation. Read it to know which
    folder the agent should have written into."""
    marker = Path("docs/.current_iteration")
    if not marker.exists():
        return None
    number = marker.read_text().strip()
    if not number.isdigit():
        return None
    return Path("docs") / number


def main() -> int:
    # We read stdin so the hook consumes its input cleanly, but we do not
    # need anything from it — SubagentStop carries no file path.
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        pass

    folder = find_current_folder()

    # If we cannot tell which folder to check, stay out of the way. Better
    # to allow than to false-block when run outside a pipeline.
    if folder is None or not folder.exists():
        return 0

    wrote_something = any(folder.glob("*.md"))
    if wrote_something:
        return 0

    # The agent finished but left the iteration folder empty. Block the stop
    # and tell the orchestrator why, using JSON rather than an exit code.
    print(json.dumps({
        "decision": "block",
        "reason": (
            f"A delegated agent finished but wrote no .md file in {folder}. "
            f"Re-run the agent or report the failure and stop, as the "
            f"pipeline rules require."
        ),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
