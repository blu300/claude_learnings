#!/usr/bin/env python3
"""Block an agent from writing anywhere except its own output file.

Claude Code runs this before a Write or Edit call and hands it the tool call
as JSON on standard input; the path being written sits at
`tool_input.file_path`. Exiting 0 lets the write through. Exiting 2 blocks it
and shows whatever this script printed to standard error to the agent, so the
agent learns why it was stopped and can correct itself.

The single argument is the filename this agent is allowed to write. A path
passes only if it looks like docs/<number>/<that filename>.

Example:

    $ echo '{"tool_input": {"file_path": "docs/2/review.md"}}' \
        | python3 scripts/guard_output_path.py review.md
    $ echo $?
    0

    $ echo '{"tool_input": {"file_path": "docs/2/definition.md"}}' \
        | python3 scripts/guard_output_path.py review.md
    Blocked: this agent may only write docs/<n>/review.md. Refused: docs/2/definition.md
    $ echo $?
    2
"""

import json
import sys
from pathlib import PurePosixPath

ALLOW = 0
BLOCK = 2


def is_allowed(path: str, filename: str) -> bool:
    """Return True if `path` is docs/<number>/<filename>.

    Backslashes are treated as separators so Windows paths behave the same.

    Example:
        is_allowed("docs/3/review.md", "review.md")        -> True
        is_allowed(r"docs\3\review.md", "review.md")       -> True
        is_allowed("/repo/docs/3/review.md", "review.md")  -> True
        is_allowed("docs/review.md", "review.md")          -> False
        is_allowed("docs/3/definition.md", "review.md")    -> False
        is_allowed("notes/3/review.md", "review.md")       -> False
    """
    parts = PurePosixPath(path.replace("\\", "/"))
    return (
        parts.name == filename
        and parts.parent.name.isdigit()
        and parts.parent.parent.name == "docs"
    )


def main(argv: list[str]) -> int:
    """Read the tool call from standard input and decide whether to allow it.

    Example:
        stdin '{"tool_input": {"file_path": "docs/1/review.md"}}', argv review.md -> 0
        stdin 'not json',                                          argv review.md -> 2
    """
    if len(argv) < 2:
        print("guard_output_path.py: no allowed filename given", file=sys.stderr)
        return BLOCK

    filename = argv[1]

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

    if is_allowed(path, filename):
        return ALLOW

    print(
        f"Blocked: this agent may only write docs/<n>/{filename}. "
        f"Refused: {path}",
        file=sys.stderr,
    )
    return BLOCK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))