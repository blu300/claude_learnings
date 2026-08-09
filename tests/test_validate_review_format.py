import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "validate_review_format.py")


def run_on_path(tmp_path, path):
    """Run the validator on a path, with tmp_path pinned as the project root.

    CLAUDE_PROJECT_DIR is pinned so the scope gate anchors where the test
    expects, and so hook_audit logs into the temp tree instead of falling
    back to the real repository's docs/hook-audit.log.
    """
    input_json = json.dumps({"tool_input": {"file_path": str(path)}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=input_json, capture_output=True, text=True,
        cwd=str(tmp_path), env=env,
    )


def run_validator(tmp_path, content):
    # The validator only grades <root>/docs/<n>/review.md — anything else is
    # out of scope by design, so the fixtures live where a real review does.
    review = tmp_path / "docs" / "2" / "review.md"
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text(content)
    return run_on_path(tmp_path, review)


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


def test_out_of_scope_paths_pass_untouched(tmp_path):
    # Wired in .claude/settings.json, this hook fires on EVERY Write in the
    # project. A malformed file that is not docs/<n>/review.md must pass
    # silently — otherwise every ordinary write in every session would be
    # nagged with "First line must be 'Verdict: ...'".
    for relative in ("notes.md", "docs/notes.md", "docs/learning/review.md",
                     "docs/2/definition.md"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("not a review at all")
        r = run_on_path(tmp_path, target)
        assert r.returncode == 0, relative
        assert r.stderr.strip() == "", relative


def test_review_lookalike_outside_project_ignored(tmp_path):
    # A file that ENDS in docs/<n>/review.md but lives outside the project
    # is not this pipeline's review.
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "elsewhere" / "docs" / "2" / "review.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("garbage")
    r = run_on_path(project, outside)
    assert r.returncode == 0
