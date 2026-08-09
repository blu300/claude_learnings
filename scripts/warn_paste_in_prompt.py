#!/usr/bin/env python3
"""Warn (never block) when an agent delegation prompt looks like pasted content.

A PreToolUse hook on the orchestrator's Agent delegation calls. The pipeline
rule is "pass file paths, never paste file contents into a prompt". That rule
is a heuristic — a long prompt is *probably* pasted content, but not always —
so this hook only warns and never blocks.

HOW A WARNING ACTUALLY REACHES SOMEONE
--------------------------------------
Printing to stderr and exiting 0 does NOT work. Per the hooks reference:

    "Stderr from a hook that exits 0 goes to the debug log only, never the
     transcript, and Claude never sees it."
    -- https://code.claude.com/docs/en/hooks

So a warn-only hook must speak through JSON on stdout instead. Two channels,
two audiences:

    systemMessage                     -> shown to the USER, action proceeds
    hookSpecificOutput.additionalContext -> given to CLAUDE next to the tool
                                            result, so it can self-correct

This hook emits both: the human watching the pipeline sees the warning, and
the orchestrator gets told so it can stop pasting on the next delegation.
Exit stays 0 — the tool call goes ahead either way.
"""

import json
import re
import sys

import hook_audit


def paste_warnings(prompt: str) -> list:
    """The three tells that a prompt is carrying pasted file content.

    Shared with warn_paste_in_user_prompt.py, which applies the same rule
    to the HUMAN's prompt — the rule is about what travels through a
    prompt, not about who wrote it.
    """
    warnings = []

    if len(prompt) > 2000:
        warnings.append(f"Prompt is {len(prompt)} chars (>2000) — may contain pasted file content.")

    header_count = len(re.findall(r"^#{1,3} ", prompt, re.MULTILINE))
    if header_count >= 3:
        warnings.append(f"Prompt contains {header_count} markdown headers — may contain pasted file content.")

    if "```" in prompt:
        warnings.append("Prompt contains fenced code blocks — may contain pasted file content.")

    return warnings


def main() -> int:
    try:
        call = json.load(sys.stdin)
        prompt = call["tool_input"].get("prompt", "")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 0

    warnings = paste_warnings(prompt)

    if warnings:
        detail = " ".join(warnings)
        hook_audit.record("warn_paste_in_prompt", "warn",
                          f"prompt of {len(prompt)} chars")
        print(json.dumps({
            "systemMessage": f"Warning: {detail}",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": (
                    f"Delegation prompt may contain pasted file content. {detail} "
                    f"The pipeline rule is to pass file paths only — the agents "
                    f"read and write files themselves."
                ),
            },
        }))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
