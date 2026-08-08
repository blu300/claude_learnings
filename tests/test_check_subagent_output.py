import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "check_subagent_output.py")


def run_hook(cwd):
    # SubagentStop payloads carry no file path; an empty object is enough.
    return subprocess.run(
        [sys.executable, SCRIPT],
        input="{}", capture_output=True, text=True, cwd=str(cwd),
    )


def make_iteration(tmp_path, number, files):
    folder = tmp_path / "docs" / str(number)
    folder.mkdir(parents=True)
    for name in files:
        (folder / name).write_text("x")
    (tmp_path / "docs" / ".current_iteration").write_text(str(number))
    return folder


def test_allows_when_folder_has_output(tmp_path):
    make_iteration(tmp_path, 2, ["definition.md"])
    result = run_hook(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_blocks_when_folder_is_empty(tmp_path):
    make_iteration(tmp_path, 2, [])  # agent wrote nothing
    result = run_hook(tmp_path)
    assert result.returncode == 0  # JSON hooks exit 0 and speak via stdout
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert "docs/2" in payload["reason"] or "docs\\2" in payload["reason"]
    # The reason is delivered to the SUBAGENT, so it must be phrased as an
    # instruction to that agent rather than a report to the orchestrator.
    assert "You finished" in payload["reason"]


def test_allows_when_no_marker(tmp_path):
    # No docs/.current_iteration — run outside a pipeline. Stay out of the way.
    (tmp_path / "docs").mkdir()
    result = run_hook(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_allows_when_marker_points_at_missing_folder(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / ".current_iteration").write_text("9")  # folder 9 does not exist
    result = run_hook(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
