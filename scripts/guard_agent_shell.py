#!/usr/bin/env python3
"""Scope an agent's shell to an allowlist of command prefixes.

Usage:
    guard_agent_shell.py <allowed-prefix> [allowed-prefix ...]

A PreToolUse hook on Bash, wired in an agent's frontmatter. An agent's
`tools:` list can grant or withhold Bash, but only as all-or-nothing —
the documented list takes bare tool names, no patterns. So "this agent
may run exactly one script" is built from two parts: grant `Bash` in
`tools:`, then let this hook narrow it. The clarifier uses exactly that
pair to get scripts/brief_stats.py and nothing else; the designer has no
Bash at all. (See "Giving an agent a tool" in docs/learning/MECHANICS.md.)

A command is allowed only if it starts with one of the given prefixes
AND contains no shell control characters. The second condition matters:
`python3 scripts/brief_stats.py x; rm -rf ~` starts with the blessed
prefix, and without the metacharacter check a prefix allowlist is a
doormat. Refused characters: ; & | ` $ ( ) < > and newlines.

HONEST LIMIT: this is a command-line allowlist, not a sandbox. It stops
an agent drifting into other commands; it does not stop everything a
determined adversary could encode into arguments. The narrow grant plus
the audit line per decision is the point — the same posture as every
other guard here.

Like guard_output_path.py, option-looking arguments are refused outright:
a typo'd flag must not silently become an allowed prefix.
"""

import json
import sys

import hook_audit

ALLOW = 0
BLOCK = 2

FORBIDDEN = set(";&|`$()<>\n\r")


def is_allowed(command: str, prefixes: list) -> bool:
    """True only for a clean command starting with an allowed prefix.

    Example:
        is_allowed("python3 scripts/brief_stats.py b.md",
                   ["python3 scripts/brief_stats.py"])      -> True
        is_allowed("python3 scripts/brief_stats.py b; ls",
                   ["python3 scripts/brief_stats.py"])      -> False
    """
    stripped = command.strip()
    if any(ch in FORBIDDEN for ch in stripped):
        return False
    return any(stripped.startswith(prefix) for prefix in prefixes)


def main(argv: list) -> int:
    flags = [a for a in argv[1:] if a.startswith("-")]
    if flags:
        print(
            f"guard_agent_shell.py: unknown option(s): {' '.join(flags)} — "
            f"refusing rather than guessing what was meant.",
            file=sys.stderr,
        )
        return BLOCK

    prefixes = argv[1:]
    if not prefixes:
        print("guard_agent_shell.py: no allowed command prefix given",
              file=sys.stderr)
        return BLOCK

    try:
        call = json.load(sys.stdin)
        command = call["tool_input"]["command"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print(
            "Blocked: could not read the command from this tool call, "
            "so it was refused rather than allowed unchecked.",
            file=sys.stderr,
        )
        return BLOCK

    shown = " ".join(str(command).split())[:120]
    if isinstance(command, str) and is_allowed(command, prefixes):
        hook_audit.record("guard_agent_shell", "allow", shown)
        return ALLOW

    hook_audit.record("guard_agent_shell", "block", shown)
    print(
        f"Blocked: this agent's shell is scoped to: "
        f"{' / '.join(prefixes)} (plain arguments only, no shell "
        f"operators). Refused: {shown}",
        file=sys.stderr,
    )
    return BLOCK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
