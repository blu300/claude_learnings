#!/usr/bin/env python3
"""Append one line per hook decision to docs/hook-audit.log.

A guard's block message is seen only by the agent that triggered it, so a
live run leaves no record a later reader can check. This log is that record:
mechanical, append-only, and written by the scripts themselves — not by the
session under test. The live-fire test (`LLM as judge.md`) uses it to
cross-check the runner's quoted evidence, because a session cannot fabricate
lines it never caused.

An empty log after a run is itself evidence: the hooks never ran at all.
That distinction — "no blocks happened" versus "no guards were loaded" —
is invisible from the transcript and visible here.

Line format, one decision per line:

    2026-08-08T17:04:11+00:00 guard_output_path block docs/2/review.md

Decisions are `allow`, `block`, or `warn`. The log lives at
docs/hook-audit.log (gitignored — it is runtime evidence, not an artifact).

Logging must never break a guard: any failure to write is swallowed.
"""

import datetime
import os
from pathlib import Path

LOG_NAME = "hook-audit.log"


def record(script: str, decision: str, detail: str) -> None:
    """Append '<utc-time> <script> <decision> <detail>' to docs/hook-audit.log.

    Example:
        record("guard_output_path", "block", "docs/2/review.md")
    """
    try:
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
        log = root / "docs" / LOG_NAME
        log.parent.mkdir(exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        )
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {script} {decision} {detail}\n")
    except OSError:
        pass
