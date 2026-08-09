#!/usr/bin/env python3
"""Shared path scoping for hooks that only care about pipeline files.

The hooks wired in .claude/settings.json run on EVERY Write in EVERY session
of this project — not just on pipeline agents. Each of them must therefore
decide, first, whether the written path is a pipeline file at all: a file
directly inside an iteration folder, <root>/docs/<n>/<name>.

Anchoring to the project root matters for the same reason it does in
guard_output_path.py: a check on how a path *ends* would match a lookalike
tree anywhere on disk (/tmp/evil/docs/2/review.md) or a ../ escape.

The root comes from CLAUDE_PROJECT_DIR, which the hook harness exports;
outside a harness the working directory is the project.
"""

import os
from pathlib import Path


def project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()


def iteration_target(path: str, root: Path) -> "tuple[str, str] | None":
    """Return (folder_number, filename) for <root>/docs/<n>/<filename>.

    Anything else — outside the project, not under docs/, deeper or shallower
    than one iteration folder, or a non-numeric folder — returns None.

    The filename comes back casefolded, and "docs" is matched
    case-insensitively: the production machine's filesystem (NTFS) is
    case-insensitive, so DOCS/2/Review.md IS docs/2/review.md there, and a
    case-sensitive comparison would let a case-twiddled path slip past every
    caller. (Path.resolve() canonicalizes case only for components that
    already exist on disk — a not-yet-created file keeps the caller's
    spelling, which is exactly when a guard most needs to match it.)

    Example (root=/repo):
        iteration_target("docs/2/review.md", root)        -> ("2", "review.md")
        iteration_target("/repo/docs/2/Review.md", root)  -> ("2", "review.md")
        iteration_target("docs/learning/GUIDE.md", root)  -> None
        iteration_target("/tmp/evil/docs/2/review.md", root) -> None
    """
    candidate = Path(path.replace("\\", "/"))
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.resolve().relative_to(root)
    except ValueError:
        return None  # outside the project entirely
    parts = relative.parts
    if len(parts) != 3 or parts[0].casefold() != "docs" or not parts[1].isdigit():
        return None
    return parts[1], parts[2].casefold()


def current_iteration(root: Path) -> "str | None":
    """The active iteration number from docs/.current_iteration, or None."""
    marker = root / "docs" / ".current_iteration"
    if not marker.exists():
        return None
    number = marker.read_text().strip()
    return number if number.isdigit() else None
