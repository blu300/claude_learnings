#!/usr/bin/env python3
"""Warn (never block) when a backlog contains effort estimates.

A PostToolUse hook on the backlog-writer's Write calls. The pipeline forbids
time/effort estimates in the backlog (they invite false precision), but this
is a heuristic — the word "effort" could appear innocently — so this hook only
warns.

WHY PostToolUse
---------------
It reads the file's *content*, which does not exist until the write has
happened. No PreToolUse hook can inspect a file that has not been written yet.
PostToolUse cannot block ("Can block? No — Shows stderr to Claude; the tool
already ran"), which is fine here: flagging a heuristic is all we want.

HOW THE WARNING REACHES SOMEONE
-------------------------------
Not via stderr — stderr from a hook that exits 0 goes to the debug log only
and Claude never sees it. Warnings travel as JSON on stdout:

    systemMessage                        -> shown to the USER
    hookSpecificOutput.additionalContext -> given to CLAUDE next to the tool
                                            result, so it can fix the file

See https://code.claude.com/docs/en/hooks for both fields.
"""

import json
import re
import sys
from pathlib import Path

import hook_audit

ESTIMATE_PATTERNS = [
    r"\b\d+\s*(hours?|days?|weeks?|points?|sp)\b",
    r"\b(estimate|effort|sizing)\b",
]


def main() -> int:
    try:
        call = json.load(sys.stdin)
        path = call["tool_input"]["file_path"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 0

    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    findings = []
    for pattern in ESTIMATE_PATTERNS:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            findings.extend(matches)

    if findings:
        sample = ", ".join(str(f) for f in findings[:5])
        hook_audit.record("warn_estimates_in_backlog", "warn", path)
        print(json.dumps({
            "systemMessage": (
                f"Warning: backlog appears to contain effort estimates "
                f"(found: {sample})."
            ),
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    f"The backlog you just wrote appears to contain effort "
                    f"estimates (found: {sample}). The spec says not to "
                    f"estimate — you have no basis for them. Remove them."
                ),
            },
        }))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
