import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PASTE = str(SCRIPTS / "warn_paste_in_prompt.py")
ESTIMATES = str(SCRIPTS / "warn_estimates_in_backlog.py")


def run(script, payload):
    return subprocess.run(
        [sys.executable, script],
        input=json.dumps(payload), capture_output=True, text=True,
    )


# --- warn_paste_in_prompt.py ---

def test_paste_warns_on_long_prompt():
    r = run(PASTE, {"tool_input": {"prompt": "x" * 2001}})
    assert r.returncode == 0
    assert "warning" in r.stderr.lower()


def test_paste_warns_on_markdown_headers():
    prompt = "# Header 1\ntext\n## Header 2\ntext\n### Header 3\ntext"
    r = run(PASTE, {"tool_input": {"prompt": prompt}})
    assert r.returncode == 0
    assert "warning" in r.stderr.lower()


def test_paste_warns_on_fenced_code():
    prompt = "here is code\n```\nx = 1\n```\n"
    r = run(PASTE, {"tool_input": {"prompt": prompt}})
    assert r.returncode == 0
    assert "warning" in r.stderr.lower()


def test_paste_silent_on_normal_prompt():
    r = run(PASTE, {"tool_input": {"prompt": "Read docs/1/brief.md and write docs/1/clarification.md"}})
    assert r.returncode == 0
    assert r.stderr == ""


# --- warn_estimates_in_backlog.py ---

def test_estimates_warns_on_time_units(tmp_path):
    backlog = tmp_path / "backlog.md"
    backlog.write_text("# Backlog\n\n### Story 1.1\nEstimate: 3 days\n")
    r = run(ESTIMATES, {"tool_input": {"file_path": str(backlog)}})
    assert r.returncode == 0
    assert "warning" in r.stderr.lower()


def test_estimates_warns_on_story_points(tmp_path):
    backlog = tmp_path / "backlog.md"
    backlog.write_text("# Backlog\n\n### Story 1.1\n5 points\n")
    r = run(ESTIMATES, {"tool_input": {"file_path": str(backlog)}})
    assert r.returncode == 0
    assert "warning" in r.stderr.lower()


def test_estimates_silent_on_clean_backlog(tmp_path):
    backlog = tmp_path / "backlog.md"
    backlog.write_text("# Backlog\n\n### Story 1.1\nAcceptance criteria:\n- works\n")
    r = run(ESTIMATES, {"tool_input": {"file_path": str(backlog)}})
    assert r.returncode == 0
    assert r.stderr == ""
