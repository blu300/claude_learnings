import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "guard_output_path.py")


def run_guard(tool_input_path, *args, cwd):
    """Run the guard with cwd as the project root.

    CLAUDE_PROJECT_DIR is pinned to cwd so the guard anchors where the test
    expects — inheriting a real value from a live session (or picking up a
    stray docs/.current_iteration in the repo) would make results depend on
    where the tests happen to run.
    """
    input_json = json.dumps({"tool_input": {"file_path": tool_input_path}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd)}
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        input=input_json, capture_output=True, text=True,
        cwd=str(cwd), env=env,
    )


def test_multiple_filenames_first_matches(tmp_path):
    r = run_guard("docs/2/definition.md", "definition.md", "dispositions.md", cwd=tmp_path)
    assert r.returncode == 0


def test_multiple_filenames_second_matches(tmp_path):
    r = run_guard("docs/2/dispositions.md", "definition.md", "dispositions.md", cwd=tmp_path)
    assert r.returncode == 0


def test_multiple_filenames_none_match(tmp_path):
    r = run_guard("docs/2/review.md", "definition.md", "dispositions.md", cwd=tmp_path)
    assert r.returncode == 2
    # Must be refused for the FILENAME, not because of an iteration mismatch —
    # there is no cursor file here, so only the filename rule can fire.
    assert "review.md" in r.stderr


def test_iteration_scoping_correct(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / ".current_iteration").write_text("3")
    r = run_guard("docs/3/review.md", "review.md", cwd=tmp_path)
    assert r.returncode == 0


def test_iteration_scoping_wrong_number(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / ".current_iteration").write_text("3")
    r = run_guard("docs/1/review.md", "review.md", cwd=tmp_path)
    assert r.returncode == 2
    assert "iteration" in r.stderr.lower()


def test_no_iteration_file_allows_any(tmp_path):
    r = run_guard("docs/5/review.md", "review.md", cwd=tmp_path)
    assert r.returncode == 0


def test_absolute_path_inside_project_allowed(tmp_path):
    r = run_guard(str(tmp_path / "docs" / "2" / "review.md"), "review.md", cwd=tmp_path)
    assert r.returncode == 0


def test_lookalike_tree_outside_project_blocked(tmp_path):
    # The path ends in docs/<n>/<allowed-file> but lives outside the project.
    # A guard that only inspected the tail of the path would let this through.
    project = tmp_path / "project"
    project.mkdir()
    evil = tmp_path / "evil" / "docs" / "2" / "review.md"
    r = run_guard(str(evil), "review.md", cwd=project)
    assert r.returncode == 2


def test_dotdot_escape_blocked(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    r = run_guard("../evil/docs/2/review.md", "review.md", cwd=project)
    assert r.returncode == 2


def test_unknown_option_is_refused(tmp_path):
    # A dropped flag must not silently turn its value into an allowed
    # filename ("--iteration 3" must never allow docs/<n>/3).
    r = run_guard("docs/2/3", "--iteration", "3", "review.md", cwd=tmp_path)
    assert r.returncode == 2
    assert "option" in r.stderr.lower()


def test_decisions_are_audit_logged(tmp_path):
    run_guard("docs/2/review.md", "review.md", cwd=tmp_path)
    run_guard("docs/2/definition.md", "review.md", cwd=tmp_path)
    log = (tmp_path / "docs" / "hook-audit.log").read_text()
    assert "guard_output_path allow docs/2/review.md" in log
    assert "guard_output_path block docs/2/definition.md" in log
