#!/usr/bin/env python3
"""A tiny tool: quick statistics about a brief. Given to ONE agent.

Usage:
    brief_stats.py <path-to-brief>

Prints word count, heading count, how many questions the brief already
asks, and a thin/normal/detailed verdict. The clarifier runs this before
interrogating a brief — a 40-word brief and a 400-word brief deserve
different questioning, and "the brief is thin" is worth knowing *before*
writing questions rather than discovering halfway through.

The script itself is ordinary Python — nothing here makes it a "tool".
What makes it one is the wiring in .claude/agents/clarifier.md: the
clarifier's `tools:` list includes Bash, and a PreToolUse hook
(guard_agent_shell.py) scopes that shell to exactly this command. The
designer has no Bash at all, so it cannot run this even though the file
sits in the same repo. That contrast — capability granted to one agent,
absent for another — is the demonstration. See "Giving an agent a tool"
in docs/learning/MECHANICS.md.
"""

import re
import sys
from pathlib import Path


def stats(text: str) -> dict:
    """Compute the numbers. Example: stats("# A\\nIs it?") ->
    {'words': 3, 'headings': 1, 'questions': 1, 'verdict': 'thin'}"""
    words = len(text.split())
    headings = len(re.findall(r"^#{1,6} ", text, re.MULTILINE))
    questions = text.count("?")
    if words < 80:
        verdict = "thin"
    elif words < 400:
        verdict = "normal"
    else:
        verdict = "detailed"
    return {"words": words, "headings": headings,
            "questions": questions, "verdict": verdict}


def main(argv: list) -> int:
    if len(argv) != 2 or argv[1].startswith("-"):
        print("usage: brief_stats.py <path-to-brief>", file=sys.stderr)
        return 2
    try:
        text = Path(argv[1]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"brief_stats.py: cannot read {argv[1]}: {error}", file=sys.stderr)
        return 1
    result = stats(text)
    print(f"words: {result['words']}")
    print(f"headings: {result['headings']}")
    print(f"questions already in the brief: {result['questions']}")
    print(f"verdict: {result['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
