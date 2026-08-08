import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "guard_orchestrator_write.py")


def run_guard(path, cwd):
    """Run the guard with cwd pinned as the project root (see
    test_guard_output_path.run_guard for why the env is controlled)."""
    input_json = json.dumps({"tool_input": {"file_path": path}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd)}
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=input_json, capture_output=True, text=True,
        cwd=str(cwd), env=env,
    )


def test_allows_clarification_in_docs_1(tmp_path):
    assert run_guard("docs/1/clarification.md", tmp_path).returncode == 0


def test_allows_brief_snapshot(tmp_path):
    assert run_guard("docs/1/brief-snapshot.md", tmp_path).returncode == 0


def test_blocks_clarification_outside_docs_1(tmp_path):
    # The rule says clarification.md lives in docs/1 only; the guard is
    # exactly as tight as the rule.
    assert run_guard("docs/2/clarification.md", tmp_path).returncode == 2


def test_blocks_current_iteration(tmp_path):
    # iteration.py writes the cursor itself now; the orchestrator has no
    # business touching it.
    assert run_guard("docs/.current_iteration", tmp_path).returncode == 2


def test_blocks_definition(tmp_path):
    assert run_guard("docs/2/definition.md", tmp_path).returncode == 2


def test_blocks_review(tmp_path):
    assert run_guard("docs/2/review.md", tmp_path).returncode == 2


def test_blocks_backlog(tmp_path):
    assert run_guard("docs/2/backlog.md", tmp_path).returncode == 2


def test_blocks_arbitrary_path(tmp_path):
    assert run_guard("src/main.py", tmp_path).returncode == 2


def test_blocks_brief_snapshot_wrong_iteration(tmp_path):
    assert run_guard("docs/2/brief-snapshot.md", tmp_path).returncode == 2


def test_blocks_lookalike_outside_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    evil = tmp_path / "evil" / "docs" / "1" / "clarification.md"
    assert run_guard(str(evil), project).returncode == 2
