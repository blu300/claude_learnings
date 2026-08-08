import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "guard_orchestrator_write.py")


def run_guard(path):
    input_json = json.dumps({"tool_input": {"file_path": path}})
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=input_json, capture_output=True, text=True
    )


def test_allows_clarification():
    assert run_guard("docs/2/clarification.md").returncode == 0


def test_allows_brief_snapshot():
    assert run_guard("docs/1/brief-snapshot.md").returncode == 0


def test_allows_current_iteration():
    assert run_guard("docs/.current_iteration").returncode == 0


def test_blocks_definition():
    r = run_guard("docs/2/definition.md")
    assert r.returncode == 2


def test_blocks_review():
    r = run_guard("docs/2/review.md")
    assert r.returncode == 2


def test_blocks_backlog():
    r = run_guard("docs/2/backlog.md")
    assert r.returncode == 2


def test_blocks_arbitrary_path():
    r = run_guard("src/main.py")
    assert r.returncode == 2


def test_blocks_brief_snapshot_wrong_iteration():
    r = run_guard("docs/2/brief-snapshot.md")
    assert r.returncode == 2
