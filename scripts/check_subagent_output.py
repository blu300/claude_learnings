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

2. It replies with JSON on stdout instead of exit code 2.

WHAT "block" MEANS HERE — IT DOES NOT MEAN STOP
-----------------------------------------------
On SubagentStop, {"decision": "block", "reason": "..."} does the opposite of
what the word suggests. Per the hooks reference, SubagentStop exit 2 / block
"Prevents the subagent from stopping" — it *keeps the subagent running* and
hands it the reason as its next instruction.

    https://code.claude.com/docs/en/hooks

Two consequences for how this script is written:

  - The reason is addressed to the SUBAGENT, not to the orchestrator. It is
    an instruction to the agent that just tried to finish ("write your output
    file now"), not a report to its parent.
  - To reach the PARENT session after a subagent returns, you would use a
    PostToolUse hook on the Agent tool instead. That is a different channel
    and this hook is not it.

In practice keep-going-and-fix-it is better than stop here: the agent gets a
chance to write the file it forgot. But it is not what SKILL.md's prose rule
("report the failure and stop") describes, and the difference matters.
"""

import json
import sys
from pathlib import Path

import hook_audit


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
        hook_audit.record("check_subagent_output", "allow", str(folder))
        return 0

    # The agent finished but left the iteration folder empty. Keep it running
    # and instruct it to write its file. The reason goes to the SUBAGENT, so
    # it is phrased as an instruction to that agent — not as a report to the
    # orchestrator, which never sees this.
    hook_audit.record("check_subagent_output", "block",
                      f"{folder} empty at SubagentStop")
    print(json.dumps({
        "decision": "block",
        "reason": (
            f"You finished without writing any .md file in {folder}. Write "
            f"your output file to that folder now, at exactly the path you "
            f"were given. If you cannot, say why in your final message."
        ),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
