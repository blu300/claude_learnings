#!/usr/bin/env python3
"""Project-wide floor under the pipeline's write rules (.claude/settings.json).

WHY THIS EXISTS
---------------
The precise guards live in frontmatter: guard_output_path.py in each agent's
file, guard_orchestrator_write.py in SKILL.md. hook_error.md documents the
day both agent-frontmatter guards silently failed to load (a workspace-trust
lookup miss on VS Code panel launches), and a designer overwrote an older
iteration with no guard, no message, and no audit line. This guard is the
defense-in-depth answer: wired in .claude/settings.json, it runs on every
Write/Edit in every session of this project, whichever way the session was
launched.

WHAT IT ENFORCES — AND, DELIBERATELY, WHAT IT DOES NOT
------------------------------------------------------
Settings-level hooks cannot know WHICH agent is writing: agent identity
exists only in the frontmatter command lines attached to specific agents; it
is not in the hook's stdin payload and cannot be recovered from the path. So
this guard enforces only the agent-independent rules:

  - docs/.current_iteration, docs/hook-audit.log and the preflight's
    rotated docs/hook-audit.pre-test.log are pipeline state, written by
    scripts/iteration.py and scripts/hook_audit.py — never via Write/Edit.
    Blocking them here also means a misbehaving agent cannot repoint the
    iteration cursor or rewrite the audit trail the live-fire judge treats
    as ground truth. Names are matched case-insensitively and colon/stream
    forms are refused, because the production filesystem (NTFS) would
    happily alias .Current_Iteration or name::$DATA onto the real file.
  - brief-snapshot.md and clarification.md live in docs/1 only, at any
    iteration (clarification.md is carried forward; the orchestrator appends
    answers to it during later iterations).
  - definition.md, dispositions.md, review.md and backlog.md may be written
    only into the CURRENT iteration folder (docs/.current_iteration). With
    no cursor file, any iteration folder is accepted — same fail-open as
    guard_output_path.py.
  - Nothing else belongs directly in an iteration folder.

Everything not directly inside docs/<n>/ — README.md, docs/learning/,
scripts/, paths outside the project — passes through silently. This is a
guard on the pipeline's output tree, not a general write lock.

What it cannot catch: cross-writes (the reviewer writing definition.md into
the current iteration) pass, because they are only wrong for a particular
agent. Per-agent ownership stays with guard_output_path.py in the agents'
frontmatter; this layer is the floor, not a replacement.

KNOWN LIMITS
------------
- Bash writes bypass it (matcher is Write|Edit) — the same documented,
  deliberately kept gap as the other guards; see "The coordinator's shell"
  in docs/learning/GUIDE.md.
- A stale cursor left by an aborted run makes this guard refuse interactive
  maintenance edits to older iteration folders. The block message names the
  escape: delete the stale docs/.current_iteration.
"""

import json
import sys

import docs_scope
import hook_audit

ALLOW = 0
BLOCK = 2

PIPELINE_FILES = ("definition.md", "dispositions.md", "review.md", "backlog.md")
DOCS1_ONLY = ("clarification.md", "brief-snapshot.md")
# The cursor, the audit log, and the preflight's rotated copy of the audit
# log (LLM as judge.md step 0). Matched case-insensitively: NTFS is
# case-insensitive, and Path.resolve() canonicalizes case only for
# components that already exist — so docs/.Current_Iteration written while
# the real cursor is absent (the normal state between runs) IS the cursor.
STATE_NAMES = (".current_iteration", "hook-audit.log", "hook-audit.pre-test.log")


def main() -> int:
    try:
        call = json.load(sys.stdin)
        path = call["tool_input"]["file_path"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print(
            "Blocked: could not read the file path from this tool call, "
            "so the write was refused rather than allowed unchecked.",
            file=sys.stderr,
        )
        return BLOCK

    root = docs_scope.project_root()

    candidate = docs_scope.Path(path.replace("\\", "/"))
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.resolve().relative_to(root)
    except ValueError:
        return ALLOW  # outside the project — not this guard's business

    parts = relative.parts
    if not parts or parts[0].casefold() != "docs":
        return ALLOW  # not under docs/ — not this guard's business

    # NTFS alternate data streams (name::$DATA and friends) alias a file
    # under a name no allowlist matches. Colons cannot appear in legitimate
    # NTFS filenames, so refusing them costs nothing real.
    if any(":" in part for part in parts):
        hook_audit.record("guard_docs_writes", "block", path)
        print(
            f"Blocked by the project docs guard: path component contains "
            f"':' (an NTFS stream alias form). Refused: {path}",
            file=sys.stderr,
        )
        return BLOCK

    if len(parts) == 2 and parts[1].casefold() in STATE_NAMES:
        hook_audit.record("guard_docs_writes", "block", path)
        print(
            f"Blocked by the project docs guard: {relative.as_posix()} is "
            f"pipeline state, written only by its own script "
            f"(scripts/iteration.py or scripts/hook_audit.py) — never via "
            f"Write or Edit.",
            file=sys.stderr,
        )
        return BLOCK

    target = docs_scope.iteration_target(path, root)
    if target is None:
        return ALLOW  # not directly inside an iteration folder
    folder, name = target

    if name in DOCS1_ONLY:
        if folder == "1":
            hook_audit.record("guard_docs_writes", "allow", path)
            return ALLOW
        hook_audit.record("guard_docs_writes", "block", path)
        print(
            f"Blocked by the project docs guard: {name} lives in docs/1 "
            f"only. Refused: {path}",
            file=sys.stderr,
        )
        return BLOCK

    if name in PIPELINE_FILES:
        current = docs_scope.current_iteration(root)
        if current is None:
            hook_audit.record("guard_docs_writes", "allow", f"{path} (no cursor)")
            return ALLOW
        if folder == current:
            hook_audit.record("guard_docs_writes", "allow", path)
            return ALLOW
        hook_audit.record("guard_docs_writes", "block", path)
        print(
            f"Blocked by the project docs guard: docs/.current_iteration "
            f"says the active iteration is {current}, so docs/{folder}/ is "
            f"not writable. Refused: {path}. If this is deliberate "
            f"maintenance outside a pipeline run, delete the stale "
            f"docs/.current_iteration cursor first.",
            file=sys.stderr,
        )
        return BLOCK

    hook_audit.record("guard_docs_writes", "block", path)
    print(
        f"Blocked by the project docs guard: only the pipeline files "
        f"({', '.join(PIPELINE_FILES + DOCS1_ONLY)}) belong directly in an "
        f"iteration folder. Refused: {path}",
        file=sys.stderr,
    )
    return BLOCK


if __name__ == "__main__":
    raise SystemExit(main())
