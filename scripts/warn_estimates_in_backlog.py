#!/usr/bin/env python3
"""Warn (never block) when a backlog contains effort estimates.

A PostToolUse hook on the backlog-writer's Write calls. The pipeline forbids
time/effort estimates in the backlog (they invite false precision), but this
is a heuristic — the word "effort" could appear innocently — so like the paste
hook it only warns and always exits 0.

Being a PostToolUse hook, it runs *after* the write has already landed, so it
cannot prevent the estimate being written; it can only flag it for a human to
notice. That is the right trade-off for a heuristic rule.
"""

import json
import re
import sys
from pathlib import Path

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
        print(
            f"Warning: backlog appears to contain effort estimates "
            f"(found: {', '.join(str(f) for f in findings[:5])}). "
            f"The spec says not to estimate.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
