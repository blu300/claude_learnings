import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "session_log.py")


def run_recorder(tmp_path, event, payload):
    """Run the recorder with tmp_path pinned as the project root."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    args = [sys.executable, SCRIPT] + ([event] if event else [])
    return subprocess.run(
        args, input=json.dumps(payload) if payload is not None else "not json",
        capture_output=True, text=True, cwd=str(tmp_path), env=env,
    )


def audit_log(tmp_path):
    log = tmp_path / "docs" / "hook-audit.log"
    return log.read_text() if log.exists() else ""


def test_logs_one_line_with_salient_detail(tmp_path):
    r = run_recorder(tmp_path, "SubagentStart",
                     {"agent_type": "reviewer", "agent_id": "abc123"})
    assert r.returncode == 0
    log = audit_log(tmp_path)
    assert "session_log SubagentStart" in log
    assert "agent_type=reviewer" in log


def test_unknown_event_still_leaves_a_line(tmp_path):
    # A recorder that drops what it does not recognise is quieter than it
    # should be — the event name alone is still evidence something happened.
    r = run_recorder(tmp_path, "SomeFutureEvent", {"whatever": 1})
    assert r.returncode == 0
    assert "session_log SomeFutureEvent -" in audit_log(tmp_path)


def test_missing_fields_cost_the_detail_not_the_line(tmp_path):
    # Payload shapes drift between Claude Code versions; the line survives.
    r = run_recorder(tmp_path, "SessionEnd", {})
    assert r.returncode == 0
    assert "session_log SessionEnd -" in audit_log(tmp_path)


def test_long_values_are_clipped_to_one_line(tmp_path):
    r = run_recorder(tmp_path, "Notification",
                     {"notification_type": "info", "message": "x\ny" * 200})
    assert r.returncode == 0
    log = audit_log(tmp_path)
    line = next(l for l in log.splitlines() if "Notification" in l)
    assert len(line) < 250
    assert "\\n" not in line


def test_malformed_stdin_never_breaks_the_session(tmp_path):
    r = run_recorder(tmp_path, "Stop", None)  # sends literal "not json"
    assert r.returncode == 0
    assert "session_log Stop -" in audit_log(tmp_path)


def test_session_start_injects_pipeline_state_when_mid_flight(tmp_path):
    # A fresh session opening onto half-finished pipeline state is how
    # stale-cursor accidents happen — SessionStart says so up front.
    (tmp_path / "docs" / "2").mkdir(parents=True)
    (tmp_path / "docs" / ".current_iteration").write_text("2")
    r = run_recorder(tmp_path, "SessionStart", {"source": "startup"})
    assert r.returncode == 0
    out = json.loads(r.stdout)
    context = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "iteration 2" in context
    assert "source=startup" in audit_log(tmp_path)


def test_session_start_stays_quiet_when_state_is_clean(tmp_path):
    r = run_recorder(tmp_path, "SessionStart", {"source": "startup"})
    assert r.returncode == 0
    assert r.stdout.strip() == ""  # no cursor -> nothing to warn about
    assert "session_log SessionStart" in audit_log(tmp_path)


def test_file_changed_records_the_cursor_bypass(tmp_path):
    # The B3b gap: a Bash redirect rewrites the cursor without any Write
    # tool call. The recorder cannot prevent it, but the change leaves a line.
    r = run_recorder(tmp_path, "FileChanged",
                     {"file_path": "docs/.current_iteration",
                      "change_type": "modified"})
    assert r.returncode == 0
    log = audit_log(tmp_path)
    assert "session_log FileChanged" in log
    assert "docs/.current_iteration" in log


def test_never_blocks(tmp_path):
    # A flight recorder that could ground the plane would be a different
    # instrument: every event, every payload, exit 0.
    for event, payload in [
        ("PreCompact", {"compaction_reason": "auto"}),
        ("PostCompact", {}),
        ("StopFailure", {"error_type": "api_error"}),
        ("ConfigChange", {"config_source": "project_settings"}),
        ("InstructionsLoaded", {"file_path": "CLAUDE.md",
                                "load_reason": "session_start"}),
        ("UserPromptExpansion", {"command": "design-cycle"}),
    ]:
        r = run_recorder(tmp_path, event, payload)
        assert r.returncode == 0, event
        assert f"session_log {event}" in audit_log(tmp_path), event
