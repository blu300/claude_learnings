#!/usr/bin/env python3
"""Manage the numbered iteration folders under docs/.

Each round of design and review gets its own folder: docs/1, docs/2, and so
on. This script is the only thing that decides which number comes next, so
that no agent has to guess.

Commands:
    list     Print every existing iteration folder, oldest first.
    current  Print the highest existing folder. Prints nothing if there are none.
    next     Create the next folder and print its path.

Example:

    $ python3 scripts/iteration.py list
    docs/1
    docs/2

    $ python3 scripts/iteration.py current
    docs/2

    $ python3 scripts/iteration.py next
    docs/3

    $ python3 scripts/iteration.py list
    docs/1
    docs/2
    docs/3

With no docs/ folder at all, "list" and "current" print nothing and exit 0,
and "next" creates docs/1 and prints it.
"""

import sys
from pathlib import Path

DOCS = Path("docs")


def iterations() -> list[int]:
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


def main(argv: list[str]) -> int:
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
        number = (found[-1] + 1) if found else 1
        folder = DOCS / str(number)
        folder.mkdir(parents=True)
        print(folder)
        return 0

    print(f"unknown command: {command}", file=sys.stderr)
    print("usage: iteration.py [list|current|next]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))