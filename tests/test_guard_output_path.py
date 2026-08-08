import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "guard_output_path.py")


def run_guard(tool_input_path, *args, cwd=None):
    input_json = json.dumps({"tool_input": {"file_path": tool_input_path}})
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        input=input_json, capture_output=True, text=True,
        cwd=cwd or "."
    )


def test_multiple_filenames_first_matches():
    r = run_guard("docs/2/definition.md", "definition.md", "dispositions.md")
    assert r.returncode == 0


def test_multiple_filenames_second_matches():
    r = run_guard("docs/2/dispositions.md", "definition.md", "dispositions.md")
    assert r.returncode == 0


def test_multiple_filenames_none_match():
    r = run_guard("docs/2/review.md", "definition.md", "dispositions.md")
    assert r.returncode == 2


def test_iteration_scoping_correct(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / ".current_iteration").write_text("3")
    r = run_guard("docs/3/review.md", "review.md", cwd=str(tmp_path))
    assert r.returncode == 0


def test_iteration_scoping_wrong_number(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / ".current_iteration").write_text("3")
    r = run_guard("docs/1/review.md", "review.md", cwd=str(tmp_path))
    assert r.returncode == 2
    assert "iteration" in r.stderr.lower()


def test_no_iteration_file_allows_any(tmp_path):
    r = run_guard("docs/5/review.md", "review.md", cwd=str(tmp_path))
    assert r.returncode == 0
