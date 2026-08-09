#!/usr/bin/env python3
"""Warn (never block) when the HUMAN's prompt looks like pasted content.

A UserPromptSubmit hook, wired in .claude/settings.json. It is the twin of
warn_paste_in_prompt.py, which watches the orchestrator's delegation
prompts. For months this repo enforced "pass file paths, not file
contents" on the orchestrator — and never noticed that nobody applied the
same rule to the human at the top of the chain. Pasting a whole brief into
the chat works, but it leaves no file for the agents to read, nothing for
brief-snapshot.md to freeze, and no record of what the pipeline was
actually asked to build.

UserPromptSubmit fires when the human submits a prompt, before Claude
processes it. It CAN block (exit 2 rejects the prompt) — this hook never
does. The pipeline's rule of thumb holds: structural rules block,
heuristics warn. "This looks pasted" is a guess, and a wrong guess must
not eat someone's prompt.

The heuristics are imported from warn_paste_in_prompt.py — same three
tells, one place to tune them. Like every warn hook here, it speaks JSON
on stdout (systemMessage for the human, additionalContext for Claude) and
logs one line so the audit trail shows it was alive.
"""

import json
import sys

import hook_audit
from warn_paste_in_prompt import paste_warnings


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    # The docs name this field prompt_text; older builds used prompt.
    # Check both rather than betting the warning on a rename.
    prompt = payload.get("prompt_text") or payload.get("prompt") or ""
    if not isinstance(prompt, str):
        return 0

    warnings = paste_warnings(prompt)
    if warnings:
        detail = " ".join(warnings)
        hook_audit.record("warn_paste_in_user_prompt", "warn",
                          f"prompt of {len(prompt)} chars")
        print(json.dumps({
            "systemMessage": (
                f"Warning: {detail} Consider saving it to a file and giving "
                f"the pipeline the path instead — agents read files, and the "
                f"brief snapshot can only freeze a file."
            ),
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    f"The user's prompt may contain pasted file content. "
                    f"{detail} If they are starting a design-cycle run, "
                    f"suggest saving the content to a file and passing the "
                    f"path — the pipeline's agents work from files."
                ),
            },
        }))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
