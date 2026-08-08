#!/usr/bin/env python3
"""Warn (never block) when an agent delegation prompt looks like pasted content.

A PreToolUse hook on the orchestrator's Agent delegation calls. The pipeline
rule is "pass file paths, never paste file contents into a prompt". That rule
is a heuristic — a long prompt is *probably* pasted content, but not always —
so this hook only warns. It prints to stderr and always exits 0, so a false
positive can never halt an unattended pipeline.
"""

import json
import re
import sys


def main() -> int:
    try:
        call = json.load(sys.stdin)
        prompt = call["tool_input"].get("prompt", "")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return 0

    warnings = []

    if len(prompt) > 2000:
        warnings.append(f"Prompt is {len(prompt)} chars (>2000) — may contain pasted file content.")

    header_count = len(re.findall(r"^#{1,3} ", prompt, re.MULTILINE))
    if header_count >= 3:
        warnings.append(f"Prompt contains {header_count} markdown headers — may contain pasted file content.")

    if "```" in prompt:
        warnings.append("Prompt contains fenced code blocks — may contain pasted file content.")

    if warnings:
        print("Warning: " + " ".join(warnings), file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
