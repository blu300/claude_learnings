#!/usr/bin/env python3
"""SubagentStop hook: when a delegated agent finishes, check that it left
its output in the current iteration folder.

This mechanises the prose rule in SKILL.md: "If an agent fails to write its
file, report the failure and stop."

Usage:
    check_subagent_output.py [expected-filename ...]

Each agent's frontmatter passes the filename that agent owns (the reviewer
passes review.md, and so on), the same way guard_output_path.py takes its
allowlist. With filenames given, the check is precise: the agent's own file
must exist in the current iteration folder when the agent stops — a folder
already populated by earlier agents no longer masks an agent that wrote
nothing. With no filenames (the legacy wiring in SKILL.md), the check falls
back to the coarse form: did *anyone* leave a .md file in the folder?

Two things make this different from the guard_*.py scripts:

1. It runs on the SubagentStop event, not PreToolUse. It fires when a
   subagent finishes, not around a tool call, so it gets NO file_path in
   its input — what it knows about the agent comes from the frontmatter
   arguments. (See "What this does not catch" below.)

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

The nudge happens ONCE. The payload's stop_hook_active field is true when
the agent is already continuing because a stop hook blocked it; blocking
again on that pass would trap an agent that legitimately has nothing to
write ("read README.md and reply, write nothing") in an endless loop — its
own escape hatch ("say why in your final message") would re-trigger the
block that offered it. Second stop, the hook lets go and logs that it did.

WHAT THIS DOES NOT CATCH
------------------------
- Staleness. A file left by an earlier round of the same iteration (the
  QUESTIONS redo-in-place path overwrites files in the same folder)
  satisfies the existence check even if the agent wrote nothing this round.
- Content. The file may exist and be empty, wrong, or malformed — format
  checking belongs to validate_review_format.py and the reviewer.
- Coarse mode catches only the FIRST writer into a fresh folder; once any
  .md exists, later agents pass. That is why the frontmatter passes
  per-agent filenames.

Every outcome — including the stay-out-of-the-way ones — writes an audit
line. An earlier version returned silently when the cursor file was missing,
which made "hook never ran" and "hook ran, nothing to check" identical in
the audit log: exactly the ambiguity the log exists to remove.
"""

import json
import sys
from pathlib import Path

import docs_scope
import hook_audit


def find_current_folder(root: Path) -> "Path | None":
    """The active iteration folder, from docs/.current_iteration."""
    number = docs_scope.current_iteration(root)
    if number is None:
        return None
    return root / "docs" / number


def main(argv: list) -> int:
    # SubagentStop carries no file path, but it does carry stop_hook_active:
    # true when the agent is already continuing because a stop hook blocked
    # it. Without this check the hook re-blocks on every stop attempt — an
    # agent that legitimately cannot write the file ("read README and write
    # nothing") would be kept running forever. One nudge, then let go.
    stop_hook_active = False
    try:
        payload = json.load(sys.stdin)
        stop_hook_active = bool(payload.get("stop_hook_active"))
    except (json.JSONDecodeError, ValueError, AttributeError):
        pass

    # Option-looking arguments are refused rather than guessed at, like
    # guard_output_path.py — but a Stop hook has no useful way to fail the
    # run, so refusal here means: drop ALL arguments, fall back to the
    # coarse check, and say so in the audit log.
    options = [a for a in argv[1:] if a.startswith("-")]
    expected = [] if options else list(argv[1:])
    if options:
        hook_audit.record(
            "check_subagent_output", "warn",
            f"refused option(s): {' '.join(options)} — using coarse check",
        )

    root = docs_scope.project_root()
    folder = find_current_folder(root)

    # Outside a pipeline run there is nothing to check — but say so, or the
    # audit log cannot tell this from a hook that never loaded.
    if folder is None:
        hook_audit.record("check_subagent_output", "allow",
                          "no docs/.current_iteration cursor — nothing to check")
        return 0
    display = folder.relative_to(root).as_posix()
    if not folder.exists():
        hook_audit.record("check_subagent_output", "allow",
                          f"{display} does not exist — nothing to check")
        return 0
    if stop_hook_active:
        hook_audit.record("check_subagent_output", "allow",
                          f"{display} — already nudged once, letting the agent go")
        return 0

    if expected:
        missing = [name for name in expected if not (folder / name).exists()]
        if not missing:
            hook_audit.record("check_subagent_output", "allow",
                              f"{display} (checked: {', '.join(expected)})")
            return 0
        hook_audit.record("check_subagent_output", "block",
                          f"{display} missing {', '.join(missing)} at SubagentStop")
        reason = (
            f"You finished without writing {', '.join(missing)} in {display}. "
            f"Write your output file to that folder now, at exactly the path "
            f"you were given. If you cannot, say why in your final message."
        )
    else:
        if any(folder.glob("*.md")):
            hook_audit.record("check_subagent_output", "allow", display)
            return 0
        hook_audit.record("check_subagent_output", "block",
                          f"{display} empty at SubagentStop")
        reason = (
            f"You finished without writing any .md file in {display}. Write "
            f"your output file to that folder now, at exactly the path you "
            f"were given. If you cannot, say why in your final message."
        )

    # The agent finished but its output is not there. Keep it running and
    # instruct it to write its file. The reason goes to the SUBAGENT, so it
    # is phrased as an instruction to that agent — not as a report to the
    # orchestrator, which never sees this.
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
