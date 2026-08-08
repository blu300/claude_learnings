#!/usr/bin/env python3
"""Validate that review.md has the correct structured format.

A PostToolUse hook on the reviewer's Write calls. Unlike the warn-only hooks,
the review format is a *structural* rule, so this hard-blocks (exit 2) and
tells the reviewer exactly what to fix. Hard-blocking a PostToolUse means the
agent is prompted to rewrite the file until it validates.

Blocks if:
- First line is not a valid verdict
- Scoring table is missing or incomplete
- Verdict contradicts scoring (APPROVED with FAILs, or CHANGES REQUESTED with
  all PASS)
"""

import json
import re
import sys
from pathlib import Path

ALLOW = 0
BLOCK = 2
VALID_VERDICTS = {"APPROVED", "CHANGES REQUESTED", "QUESTIONS"}
REQUIRED_DIMENSIONS = {"coverage", "soundness", "decisions", "gaps", "over-reach"}


def validate(content: str) -> str | None:
    """Return an error string if the review is malformed, or None if valid."""
    lines = content.strip().splitlines()
    if not lines:
        return "File is empty — expected Verdict: line"

    first_line = lines[0].strip()
    match = re.match(r"^Verdict:\s*(.+)$", first_line)
    if not match:
        return f"First line must be 'Verdict: APPROVED|CHANGES REQUESTED|QUESTIONS', got: '{first_line}'"

    verdict = match.group(1).strip()
    if verdict not in VALID_VERDICTS:
        return f"Invalid verdict '{verdict}'. Must be one of: {', '.join(sorted(VALID_VERDICTS))}"

    # QUESTIONS means the reviewer could not score — no table required.
    if verdict == "QUESTIONS":
        return None

    scores = {}
    for line in lines:
        row_match = re.match(r"\|\s*(\w[\w\s-]*?)\s*\|\s*(PASS|FAIL)\s*\|", line)
        if row_match:
            dim = row_match.group(1).strip().lower()
            score = row_match.group(2).strip()
            scores[dim] = score

    missing = REQUIRED_DIMENSIONS - set(scores.keys())
    if missing:
        return f"Missing scored dimensions: {', '.join(sorted(missing))}"

    has_fail = any(v == "FAIL" for v in scores.values())
    all_pass = all(v == "PASS" for v in scores.values())

    if verdict == "APPROVED" and has_fail:
        failed = [d for d, v in scores.items() if v == "FAIL"]
        return f"Verdict is APPROVED but these dimensions are FAIL: {', '.join(sorted(failed))}"

    if verdict == "CHANGES REQUESTED" and all_pass:
        return "Verdict is CHANGES REQUESTED but all dimensions are PASS — contradiction"

    return None


def main() -> int:
    try:
        call = json.load(sys.stdin)
        path = call["tool_input"]["file_path"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        print("Blocked: could not read file path from tool call.", file=sys.stderr)
        return BLOCK

    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"Blocked: could not read review file: {e}", file=sys.stderr)
        return BLOCK

    error = validate(content)
    if error:
        print(f"Blocked: {error}", file=sys.stderr)
        return BLOCK

    return ALLOW


if __name__ == "__main__":
    raise SystemExit(main())
