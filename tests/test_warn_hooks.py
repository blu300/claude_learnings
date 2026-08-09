"""Tests for the two warn-only hooks.

These hooks warn via JSON on stdout, not stderr. Stderr from a hook that exits
0 goes to the debug log only and Claude never sees it, so a stderr warning
would be inert — see the note in each script and
https://code.claude.com/docs/en/hooks
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PASTE = str(SCRIPTS / "warn_paste_in_prompt.py")
ESTIMATES = str(SCRIPTS / "warn_estimates_in_backlog.py")


def run(script, payload, project_dir=None):
    """Run a warn hook with CLAUDE_PROJECT_DIR pinned to a scratch tree.

    Without the pin, hook_audit falls back to the working directory and a
    plain pytest run appends its artifacts to the real docs/hook-audit.log —
    the file the live-fire judge treats as ground truth.
    """
    root = str(project_dir) if project_dir else tempfile.mkdtemp()
    env = {**os.environ, "CLAUDE_PROJECT_DIR": root}
    return subprocess.run(
        [sys.executable, script],
        input=json.dumps(payload), capture_output=True, text=True, env=env,
    )


def make_backlog(tmp_path, content):
    # The estimates hook only scans <root>/docs/<n>/backlog.md — anything
    # else is out of scope by design — so fixtures live where a real one does.
    backlog = tmp_path / "docs" / "2" / "backlog.md"
    backlog.parent.mkdir(parents=True, exist_ok=True)
    backlog.write_text(content)
    return backlog


def warning_of(proc):
    """Parse the hook's JSON reply, or None when it stayed silent."""
    if not proc.stdout.strip():
        return None
    return json.loads(proc.stdout)


# --- warn_paste_in_prompt.py ---

def test_paste_warns_on_long_prompt():
    r = run(PASTE, {"tool_input": {"prompt": "x" * 2001}})
    assert r.returncode == 0
    w = warning_of(r)
    assert "2001" in w["systemMessage"]
    assert w["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_paste_warns_on_markdown_headers():
    prompt = "# Header 1\ntext\n## Header 2\ntext\n### Header 3\ntext"
    r = run(PASTE, {"tool_input": {"prompt": prompt}})
    assert r.returncode == 0
    assert "headers" in warning_of(r)["systemMessage"]


def test_paste_warns_on_fenced_code():
    prompt = "here is code\n```\nx = 1\n```\n"
    r = run(PASTE, {"tool_input": {"prompt": prompt}})
    assert r.returncode == 0
    assert "code blocks" in warning_of(r)["systemMessage"]


def test_paste_reaches_both_audiences():
    """A warning must reach the user (systemMessage) and Claude
    (additionalContext) — they are separate channels."""
    r = run(PASTE, {"tool_input": {"prompt": "x" * 2001}})
    w = warning_of(r)
    assert w["systemMessage"]
    assert w["hookSpecificOutput"]["additionalContext"]


def test_paste_silent_on_normal_prompt():
    r = run(PASTE, {"tool_input": {"prompt": "Read docs/1/brief.md and write docs/1/clarification.md"}})
    assert r.returncode == 0
    assert warning_of(r) is None


def test_paste_never_blocks():
    """Heuristic rules must never halt an unattended pipeline."""
    for prompt in ["x" * 5000, "# a\n## b\n### c", "```\ncode\n```"]:
        assert run(PASTE, {"tool_input": {"prompt": prompt}}).returncode == 0


# --- warn_estimates_in_backlog.py ---

def test_estimates_warns_on_time_units(tmp_path):
    backlog = make_backlog(tmp_path, "# Backlog\n\n### Story 1.1\nEstimate: 3 days\n")
    r = run(ESTIMATES, {"tool_input": {"file_path": str(backlog)}}, project_dir=tmp_path)
    assert r.returncode == 0
    w = warning_of(r)
    assert "estimates" in w["systemMessage"]
    assert w["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


def test_estimates_warns_on_story_points(tmp_path):
    backlog = make_backlog(tmp_path, "# Backlog\n\n### Story 1.1\n5 points\n")
    r = run(ESTIMATES, {"tool_input": {"file_path": str(backlog)}}, project_dir=tmp_path)
    assert r.returncode == 0
    assert warning_of(r)["systemMessage"]


def test_estimates_silent_on_clean_backlog(tmp_path):
    backlog = make_backlog(tmp_path, "# Backlog\n\n### Story 1.1\nAcceptance criteria:\n- works\n")
    r = run(ESTIMATES, {"tool_input": {"file_path": str(backlog)}}, project_dir=tmp_path)
    assert r.returncode == 0
    assert warning_of(r) is None


def test_estimates_silent_on_missing_file(tmp_path):
    missing = tmp_path / "docs" / "2" / "backlog.md"
    (tmp_path / "docs" / "2").mkdir(parents=True)
    r = run(ESTIMATES, {"tool_input": {"file_path": str(missing)}}, project_dir=tmp_path)
    assert r.returncode == 0
    assert warning_of(r) is None


def test_estimates_silent_outside_pipeline_backlog(tmp_path):
    # Wired in .claude/settings.json, this hook fires on EVERY Write in the
    # project. A file that mentions estimates but is not docs/<n>/backlog.md
    # (hook_error.md, a README, a design doc) must not be nagged.
    for relative in ("notes.md", "docs/plan.md", "docs/2/definition.md"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("The estimate is 3 days of effort, about 5 points.")
        r = run(ESTIMATES, {"tool_input": {"file_path": str(target)}},
                project_dir=tmp_path)
        assert r.returncode == 0, relative
        assert warning_of(r) is None, relative
