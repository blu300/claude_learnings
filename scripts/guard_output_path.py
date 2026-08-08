#!/usr/bin/env python3
"""Block an agent from writing anywhere except its allowed output file(s).

Usage:
    guard_output_path.py <filename> [filename2 ...]

The write is allowed only when the path points at docs/<n>/<filename> INSIDE
this project. Anchoring to the project root matters: a check that only looks
at how a path *ends* would pass a lookalike tree anywhere on disk
(/tmp/evil/docs/2/review.md) or a ../ escape. The root comes from
CLAUDE_PROJECT_DIR, which the hook harness exports; outside a harness the
working directory is the project.

Reads docs/.current_iteration to scope writes to the active iteration.
If that file does not exist, any iteration number is accepted.

Any option-looking argument is refused outright rather than ignored — a
silently dropped flag would corrupt the allowlist (`--iteration 3` must not
turn "3" into an allowed filename).

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
import os
import sys
from pathlib import Path

import hook_audit

ALLOW = 0
BLOCK = 2


def project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()


def get_current_iteration(root: Path) -> "str | None":
    marker = root / "docs" / ".current_iteration"
    if marker.exists():
        return marker.read_text().strip()
    return None


def is_allowed(path: str, filenames: list, required_iteration: "str | None",
               root: Path) -> bool:
    """Return True only for <root>/docs/<number>/<one-of-filenames>.

    When required_iteration is set, the number must match exactly.

    Example (root=/repo):
        is_allowed("docs/3/review.md", ["review.md"], None, root)      -> True
        is_allowed("/repo/docs/3/review.md", ["review.md"], "3", root) -> True
        is_allowed("docs/1/review.md", ["review.md"], "3", root)       -> False
        is_allowed("/tmp/evil/docs/3/review.md", ["review.md"], None, root)
                                                                       -> False
    """
    candidate = Path(path.replace("\\", "/"))
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.resolve().relative_to(root)
    except ValueError:
        return False  # points outside the project entirely
    parts = relative.parts
    if len(parts) != 3 or parts[0] != "docs":
        return False
    folder, name = parts[1], parts[2]
    if name not in filenames or not folder.isdigit():
        return False
    if required_iteration and folder != required_iteration:
        return False
    return True


def main(argv: list) -> int:
    flags = [a for a in argv[1:] if a.startswith("-")]
    if flags:
        print(
            f"guard_output_path.py: unknown option(s): {' '.join(flags)} — "
            f"refusing rather than guessing what was meant.",
            file=sys.stderr,
        )
        return BLOCK

    filenames = argv[1:]
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

    root = project_root()
    required_iteration = get_current_iteration(root)

    if is_allowed(path, filenames, required_iteration, root):
        hook_audit.record("guard_output_path", "allow", path)
        return ALLOW

    hook_audit.record("guard_output_path", "block", path)
    iteration_msg = f" in iteration {required_iteration}" if required_iteration else ""
    allowed_msg = " or ".join(filenames)
    print(
        f"Blocked: this agent may only write docs/<n>/{allowed_msg}{iteration_msg} "
        f"inside this project. Refused: {path}",
        file=sys.stderr,
    )
    return BLOCK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
