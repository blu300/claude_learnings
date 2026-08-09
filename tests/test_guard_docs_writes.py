import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "guard_docs_writes.py")


def run_guard(tool_input_path, *, cwd):
    """Run the guard with cwd pinned as the project root (CLAUDE_PROJECT_DIR)."""
    input_json = json.dumps({"tool_input": {"file_path": str(tool_input_path)}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd)}
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=input_json, capture_output=True, text=True,
        cwd=str(cwd), env=env,
    )


def set_cursor(tmp_path, number):
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / ".current_iteration").write_text(str(number))


# --- pass-through: this is a guard on the pipeline tree, not a write lock ---

def test_passes_ordinary_project_files(tmp_path):
    for path in ("README.md", "scripts/new_tool.py", "docs/learning/GUIDE.md",
                 "docs/notes.md"):
        r = run_guard(path, cwd=tmp_path)
        assert r.returncode == 0, path


def test_passes_paths_outside_the_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "elsewhere" / "docs" / "2" / "review.md"
    r = run_guard(outside, cwd=project)
    assert r.returncode == 0


# --- pipeline state files: written by scripts, never via Write/Edit ---

def test_blocks_the_iteration_cursor(tmp_path):
    # An agent that can Write the cursor can repoint it and then "legally"
    # overwrite an older iteration — the exact violation this layer exists
    # to stop (B2 in the live-fire test).
    r = run_guard("docs/.current_iteration", cwd=tmp_path)
    assert r.returncode == 2
    assert "iteration.py" in r.stderr


def test_blocks_the_audit_log(tmp_path):
    # The audit log is the judge's ground truth; a writable audit log means
    # a session under test could fabricate or destroy its own record.
    r = run_guard("docs/hook-audit.log", cwd=tmp_path)
    assert r.returncode == 2


def test_blocks_the_rotated_preflight_log(tmp_path):
    # The preflight moves the log to hook-audit.pre-test.log and treats it
    # as evidence — it needs the same protection as the live log.
    r = run_guard("docs/hook-audit.pre-test.log", cwd=tmp_path)
    assert r.returncode == 2


def test_blocks_case_twiddled_state_files(tmp_path):
    # NTFS is case-insensitive: docs/.Current_Iteration IS the cursor on the
    # production machine, and Path.resolve() only canonicalizes case for
    # components that already exist — a not-yet-created cursor keeps the
    # attacker's spelling. A case-sensitive comparison here was a working
    # bypass of the repoint-and-rewrite protection.
    for path in ("docs/.Current_Iteration", "docs/Hook-Audit.log",
                 "docs/HOOK-AUDIT.LOG", "DOCS/.current_iteration"):
        r = run_guard(path, cwd=tmp_path)
        assert r.returncode == 2, path


def test_blocks_ntfs_stream_aliases(tmp_path):
    # name::$DATA addresses the same file under a name no allowlist matches.
    # Colons cannot appear in legitimate NTFS filenames, so refuse them all.
    for path in ("docs/.current_iteration::$DATA",
                 "docs/hook-audit.log:hidden",
                 "docs/2/review.md::$DATA"):
        r = run_guard(path, cwd=tmp_path)
        assert r.returncode == 2, path


def test_case_twiddled_iteration_paths_still_scoped(tmp_path):
    # DOCS/1/definition.md is docs/1/definition.md on NTFS — the iteration
    # scoping must not be escapable by re-casing the path.
    set_cursor(tmp_path, 2)
    assert run_guard("DOCS/1/definition.md", cwd=tmp_path).returncode == 2
    assert run_guard("docs/1/Definition.md", cwd=tmp_path).returncode == 2
    assert run_guard("DOCS/2/definition.md", cwd=tmp_path).returncode == 0


# --- docs/1-only files ---

def test_allows_brief_snapshot_in_docs_1(tmp_path):
    assert run_guard("docs/1/brief-snapshot.md", cwd=tmp_path).returncode == 0


def test_allows_clarification_in_docs_1_at_any_iteration(tmp_path):
    # clarification.md is carried forward: the orchestrator appends answers
    # to docs/1/clarification.md while later iterations are active.
    set_cursor(tmp_path, 3)
    assert run_guard("docs/1/clarification.md", cwd=tmp_path).returncode == 0


def test_blocks_clarification_outside_docs_1(tmp_path):
    r = run_guard("docs/2/clarification.md", cwd=tmp_path)
    assert r.returncode == 2
    assert "docs/1" in r.stderr


# --- iteration scoping for the agents' files ---

def test_allows_pipeline_file_in_current_iteration(tmp_path):
    set_cursor(tmp_path, 2)
    assert run_guard("docs/2/definition.md", cwd=tmp_path).returncode == 0
    assert run_guard("docs/2/review.md", cwd=tmp_path).returncode == 0


def test_blocks_pipeline_file_in_older_iteration(tmp_path):
    set_cursor(tmp_path, 2)
    r = run_guard("docs/1/definition.md", cwd=tmp_path)
    assert r.returncode == 2
    assert "current_iteration" in r.stderr or "iteration" in r.stderr


def test_block_message_names_the_stale_cursor_escape(tmp_path):
    # A stale cursor left by an aborted run must not brick interactive
    # maintenance without telling the user the way out.
    set_cursor(tmp_path, 4)
    r = run_guard("docs/2/definition.md", cwd=tmp_path)
    assert r.returncode == 2
    assert "delete the stale" in r.stderr


def test_no_cursor_allows_any_iteration(tmp_path):
    assert run_guard("docs/7/backlog.md", cwd=tmp_path).returncode == 0


# --- stray files in iteration folders ---

def test_blocks_stray_files_in_iteration_folders(tmp_path):
    r = run_guard("docs/2/notes.md", cwd=tmp_path)
    assert r.returncode == 2


# --- plumbing ---

def test_malformed_stdin_fails_closed(tmp_path):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    r = subprocess.run(
        [sys.executable, SCRIPT],
        input="not json", capture_output=True, text=True,
        cwd=str(tmp_path), env=env,
    )
    assert r.returncode == 2


def test_decisions_are_audit_logged(tmp_path):
    set_cursor(tmp_path, 2)
    run_guard("docs/2/definition.md", cwd=tmp_path)
    run_guard("docs/1/definition.md", cwd=tmp_path)
    log = (tmp_path / "docs" / "hook-audit.log").read_text()
    assert "guard_docs_writes allow docs/2/definition.md" in log
    assert "guard_docs_writes block docs/1/definition.md" in log


def test_windows_style_backslash_paths(tmp_path):
    set_cursor(tmp_path, 2)
    assert run_guard("docs\\2\\definition.md", cwd=tmp_path).returncode == 0
    assert run_guard("docs\\1\\definition.md", cwd=tmp_path).returncode == 2
