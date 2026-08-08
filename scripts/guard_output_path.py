#!/usr/bin/env python3
"""Block an agent from writing anywhere except its allowed output file(s).

Usage:
    guard_output_path.py <filename> [filename2 ...]

Reads docs/.current_iteration to scope writes to the active iteration.
If that file does not exist, any iteration number is accepted.

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
from pathlib import Path, PurePosixPath

ALLOW = 0
BLOCK = 2
CURRENT_ITERATION_FILE = Path("docs/.current_iteration")


def get_current_iteration() -> "str | None":
    if CURRENT_ITERATION_FILE.exists():
        return CURRENT_ITERATION_FILE.read_text().strip()
    return None


def is_allowed(path: str, filenames: list, required_iteration: "str | None") -> bool:
    """Return True if path matches docs/<number>/<one-of-filenames>.

    When required_iteration is set, the number must match exactly.

    Example:
        is_allowed("docs/3/review.md", ["review.md"], None)      -> True
        is_allowed("docs/3/review.md", ["review.md"], "3")       -> True
        is_allowed("docs/1/review.md", ["review.md"], "3")       -> False
        is_allowed("docs/3/def.md", ["def.md", "disp.md"], "3")  -> True
    """
    parts = PurePosixPath(path.replace("\\", "/"))
    if parts.name not in filenames:
        return False
    if not parts.parent.name.isdigit():
        return False
    if parts.parent.parent.name != "docs":
        return False
    if required_iteration and parts.parent.name != required_iteration:
        return False
    return True


def main(argv: list) -> int:
    if len(argv) < 2:
        print("guard_output_path.py: no allowed filename given", file=sys.stderr)
        return BLOCK

    filenames = [a for a in argv[1:] if not a.startswith("-")]
    if not filenames:
        print("guard_output_path.py: no allowed filename given", file=sys.stderr)
        return BLOCK

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

    required_iteration = get_current_iteration()

    if is_allowed(path, filenames, required_iteration):
        return ALLOW

    iteration_msg = f" in iteration {required_iteration}" if required_iteration else ""
    allowed_msg = " or ".join(filenames)
    print(
        f"Blocked: this agent may only write docs/<n>/{allowed_msg}{iteration_msg}. "
        f"Refused: {path}",
        file=sys.stderr,
    )
    return BLOCK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
