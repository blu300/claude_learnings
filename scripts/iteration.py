#!/usr/bin/env python3
"""Manage the numbered iteration folders under docs/.

Each round of design and review gets its own folder: docs/1, docs/2, and so
on. This script is the only thing that decides which number comes next, so
that no agent has to guess. Creating a folder also records it as the active
iteration in docs/.current_iteration, so the write guards always scope to
the folder that was just created — the cursor cannot be forgotten or drift
out of step, because no one else writes it.

The iteration cap lives HERE, as a constant, not in a prompt and not behind
a flag the orchestrator chooses to pass. `--max` may lower the cap for a
single call; it can never raise it. To change the real cap, a human edits
this file. That is what makes "stop after 4 iterations" a rule rather than
a request.

Commands:
    list     Print every existing iteration folder, oldest first.
    current  Print the highest existing folder. Prints nothing if there are none.
    next     Create the next folder (cap permitting) and print its path.

Example:

    $ python3 scripts/iteration.py list
    docs/1
    docs/2

    $ python3 scripts/iteration.py next
    docs/3

    $ cat docs/.current_iteration
    3

With no docs/ folder at all, "list" and "current" print nothing and exit 0,
and "next" creates docs/1 and prints it. At the cap, "next" exits 1 and
creates nothing.
"""

import sys
from pathlib import Path

DOCS = Path("docs")

# The hard cap on design iterations. Edit this file to change it — there is
# deliberately no way to raise it from the command line.
DEFAULT_MAX = 4


def iterations() -> list:
    """Return the numbers of the existing iteration folders, ascending.

    Example:
        docs/ containing "1", "2" and "README.md"  ->  [1, 2]
        no docs/ folder at all                     ->  []
    """
    if not DOCS.is_dir():
        return []
    return sorted(
        int(child.name)
        for child in DOCS.iterdir()
        if child.is_dir() and child.name.isdigit()
    )


def main(argv: list) -> int:
    """Run one command and print its result.

    Example:
        main(["next"])  ->  prints "docs/3", returns 0
        main(["wat"])   ->  prints usage to stderr, returns 2
    """
    command = argv[1] if len(argv) > 1 else "current"
    found = iterations()

    if command == "list":
        for number in found:
            print(DOCS / str(number))
        return 0

    if command == "current":
        if found:
            print(DOCS / str(found[-1]))
        return 0

    if command == "next":
        cap = DEFAULT_MAX
        if "--max" in argv:
            max_idx = argv.index("--max")
            value = argv[max_idx + 1] if max_idx + 1 < len(argv) else None
            if value is None or not value.isdigit() or int(value) < 1:
                # Fail loudly. Silently ignoring a bad value would mean a typo
                # quietly removed the cap.
                print(f"--max needs a positive integer, got: {value!r}",
                      file=sys.stderr)
                return 2
            cap = min(cap, int(value))  # may lower the cap, never raise it

        if found and found[-1] >= cap:
            print(
                f"Maximum of {cap} iterations reached. "
                f"Current highest: docs/{found[-1]}",
                file=sys.stderr,
            )
            return 1

        number = (found[-1] + 1) if found else 1
        folder = DOCS / str(number)
        folder.mkdir(parents=True)
        (DOCS / ".current_iteration").write_text(f"{number}\n")
        print(folder)
        return 0

    print(f"unknown command: {command}", file=sys.stderr)
    print("usage: iteration.py [list|current|next]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
