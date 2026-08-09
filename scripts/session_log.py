#!/usr/bin/env python3
"""The flight recorder: one audit-log line per session event.

Usage:
    session_log.py <EventName>

The guards in this repo answer one question: "should this action be
allowed?" This script answers a different one: "what actually happened?"
It is wired in .claude/settings.json against a dozen session events —
session start and end, every delegation, compaction, tool failures,
notifications, config changes — and appends one line for each to the same
docs/hook-audit.log the guards write. It never blocks anything: a flight
recorder that could ground the plane would be a very different instrument.

Why bother? The case study (docs/learning/CASE-STUDY.md) in one line:
a protection that is silent when idle is indistinguishable from one that
never loaded. The same goes for a session. After an unattended run, the
questions are always "did it compact?", "which agents ran, in what order?",
"why did it stall?" — and the transcript answers none of them mechanically.
These lines do. The live-fire judge also uses them: SubagentStart lines
are a delegation record the session under test did not write itself.

The event name arrives as a command-line argument, so the wiring in
settings.json is self-documenting — you can read which event each entry
records without opening this file. The JSON payload on stdin differs per
event; DETAIL_FIELDS below picks the one or two fields worth keeping.
Unknown events still get a line (event name, no detail): a recorder that
drops what it does not recognise is quieter than it should be.

Two events get slightly more than a log line:

- SessionStart also *injects context*: if a pipeline run is mid-flight
  (docs/.current_iteration exists), the new session is told so, up front,
  via hookSpecificOutput.additionalContext — the same channel the warn
  hooks use. A fresh session that stumbles into half-finished pipeline
  state is exactly how stale-cursor accidents happen.
- FileChanged is wired (in settings.json) to watch docs/.current_iteration.
  The write guards only see the Write and Edit tools; a Bash redirect
  (`echo 2 > docs/.current_iteration`) walks straight past them — the
  documented B3b gap. This hook cannot *prevent* that either, but the file
  changing on disk is visible regardless of which tool changed it, so the
  bypass now at least leaves a line. Detection where prevention isn't
  available.

Everything is fail-open and silent on error: a broken recorder must never
break the session it records.
"""

import json
import sys

import docs_scope
import hook_audit

# Per event: which payload fields are worth keeping in the log line, in
# order. Field names are checked defensively — the payload shape can drift
# between Claude Code versions, and a missing field should cost us the
# detail, not the line.
DETAIL_FIELDS = {
    "SessionStart": ("source", "model"),
    "SessionEnd": ("end_reason", "reason"),
    "Stop": ("stop_reason",),
    "StopFailure": ("error_type", "error"),
    "SubagentStart": ("agent_type", "agent_id"),
    "SubagentStop": ("agent_type", "agent_id"),
    "PostToolUseFailure": ("tool_name", "error"),
    "Notification": ("notification_type", "message"),
    "PreCompact": ("compaction_reason", "trigger"),
    "PostCompact": (),
    "UserPromptExpansion": ("command", "command_name"),
    "InstructionsLoaded": ("file_path", "load_reason"),
    "ConfigChange": ("config_source", "source"),
    "FileChanged": ("file_path", "change_type"),
}


def clip(value) -> str:
    """One short, single-line fragment — the log is a record, not a dump."""
    text = " ".join(str(value).split())
    return text[:80] + "…" if len(text) > 80 else text


def pipeline_state_note(root) -> "str | None":
    """A one-liner about mid-flight pipeline state, or None when clean."""
    number = docs_scope.current_iteration(root)
    if number is None:
        return None
    folders = sorted(
        p.name for p in (root / "docs").iterdir()
        if p.is_dir() and p.name.isdigit()
    ) if (root / "docs").exists() else []
    return (
        f"Design-pipeline state: docs/.current_iteration says iteration "
        f"{number} is active (folders present: {', '.join(folders) or 'none'}). "
        f"If you are not running the /design-cycle skill, leave docs/<n>/ "
        f"and the cursor alone — see CLAUDE.md. A leftover cursor from an "
        f"aborted run can be deleted safely."
    )


def main(argv: list) -> int:
    event = argv[1] if len(argv) > 1 else ""
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            payload = {}
    except (json.JSONDecodeError, ValueError):
        payload = {}
    if not event:
        event = str(payload.get("hook_event_name") or "unknown-event")

    parts = [
        f"{field}={clip(payload[field])}"
        for field in DETAIL_FIELDS.get(event, ())
        if payload.get(field) not in (None, "")
    ]
    hook_audit.record("session_log", event, " ".join(parts) or "-")

    if event == "SessionStart":
        try:
            note = pipeline_state_note(docs_scope.project_root())
        except OSError:
            note = None
        if note:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": note,
                },
            }))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
