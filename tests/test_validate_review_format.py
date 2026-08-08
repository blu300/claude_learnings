import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "validate_review_format.py")


def run_validator(tmp_path, content):
    review = tmp_path / "review.md"
    review.write_text(content)
    input_json = json.dumps({"tool_input": {"file_path": str(review)}})
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=input_json, capture_output=True, text=True,
    )


def test_valid_approved(tmp_path):
    content = """Verdict: APPROVED

| Dimension   | Verdict | Finding |
|-------------|---------|---------|
| Coverage    | PASS    |         |
| Soundness   | PASS    |         |
| Decisions   | PASS    |         |
| Gaps        | PASS    |         |
| Over-reach  | PASS    |         |

## Non-blocking
- Minor naming inconsistency in section 3
"""
    assert run_validator(tmp_path, content).returncode == 0


def test_valid_changes_requested(tmp_path):
    content = """Verdict: CHANGES REQUESTED

| Dimension   | Verdict | Finding |
|-------------|---------|---------|
| Coverage    | PASS    |         |
| Soundness   | FAIL    | Auth flow breaks under concurrent requests |
| Decisions   | PASS    |         |
| Gaps        | PASS    |         |
| Over-reach  | PASS    |         |

## Blocking
- Auth flow will deadlock under concurrent requests
"""
    assert run_validator(tmp_path, content).returncode == 0


def test_valid_questions(tmp_path):
    content = """Verdict: QUESTIONS

## Questions for human
- Which datastore is authoritative?
"""
    assert run_validator(tmp_path, content).returncode == 0


def test_missing_verdict(tmp_path):
    content = """## Review\nLooks good.\n"""
    r = run_validator(tmp_path, content)
    assert r.returncode == 2
    assert "verdict" in r.stderr.lower()


def test_approved_but_has_fail(tmp_path):
    content = """Verdict: APPROVED

| Dimension   | Verdict | Finding |
|-------------|---------|---------|
| Coverage    | PASS    |         |
| Soundness   | FAIL    | Something breaks |
| Decisions   | PASS    |         |
| Gaps        | PASS    |         |
| Over-reach  | PASS    |         |
"""
    r = run_validator(tmp_path, content)
    assert r.returncode == 2
    assert "fail" in r.stderr.lower()


def test_changes_requested_but_all_pass(tmp_path):
    content = """Verdict: CHANGES REQUESTED

| Dimension   | Verdict | Finding |
|-------------|---------|---------|
| Coverage    | PASS    |         |
| Soundness   | PASS    |         |
| Decisions   | PASS    |         |
| Gaps        | PASS    |         |
| Over-reach  | PASS    |         |
"""
    r = run_validator(tmp_path, content)
    assert r.returncode == 2


def test_missing_dimension(tmp_path):
    content = """Verdict: APPROVED

| Dimension   | Verdict | Finding |
|-------------|---------|---------|
| Coverage    | PASS    |         |
| Soundness   | PASS    |         |
| Decisions   | PASS    |         |
| Gaps        | PASS    |         |
"""
    r = run_validator(tmp_path, content)
    assert r.returncode == 2
    assert "over-reach" in r.stderr.lower()
