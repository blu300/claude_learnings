import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "check_subagent_output.py")


def run_hook(cwd, *args):
    """Run the hook with cwd as the project root.

    CLAUDE_PROJECT_DIR is pinned to cwd so both the check and the audit log
    anchor where the test expects — inheriting a real value from a live
    session would make the hook check (and log into) the actual repository.
    """
    # SubagentStop payloads carry no file path; an empty object is enough.
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd)}
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        input="{}", capture_output=True, text=True, cwd=str(cwd), env=env,
    )


def audit_log(tmp_path):
    log = tmp_path / "docs" / "hook-audit.log"
    return log.read_text() if log.exists() else ""


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
    # No docs/.current_iteration — run outside a pipeline. Stay out of the
    # way, but leave an audit line saying so: silence here is exactly the
    # "never loaded" ambiguity the audit log exists to remove.
    (tmp_path / "docs").mkdir()
    result = run_hook(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert "check_subagent_output allow" in audit_log(tmp_path)


def test_allows_when_marker_points_at_missing_folder(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / ".current_iteration").write_text("9")  # folder 9 does not exist
    result = run_hook(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert "check_subagent_output allow" in audit_log(tmp_path)


def test_expected_file_present_allows(tmp_path):
    make_iteration(tmp_path, 2, ["review.md"])
    result = run_hook(tmp_path, "review.md")
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    # The audit detail names what was checked, so the per-agent wiring is
    # distinguishable from the legacy coarse wiring in the log.
    assert "checked: review.md" in audit_log(tmp_path)


def test_expected_file_missing_blocks_despite_populated_folder(tmp_path):
    # The old coarse check could only catch the FIRST writer into a fresh
    # folder — any pre-existing .md satisfied it. The per-agent expected
    # file must catch an agent that wrote nothing even here.
    make_iteration(tmp_path, 2, ["definition.md", "clarification.md"])
    result = run_hook(tmp_path, "review.md")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert "review.md" in payload["reason"]
    assert "You finished" in payload["reason"]


def test_option_args_refused_falls_back_to_coarse(tmp_path):
    # A typo'd flag must not corrupt the check. The hook cannot usefully
    # fail the run from a Stop event, so it drops ALL arguments, uses the
    # coarse check, and says so in the audit log.
    make_iteration(tmp_path, 2, ["definition.md"])
    result = run_hook(tmp_path, "--file", "review.md")
    assert result.returncode == 0
    assert result.stdout.strip() == ""  # coarse check passes: folder non-empty
    log = audit_log(tmp_path)
    assert "refused option" in log
    assert "checked: review.md" not in log


def test_no_reblock_when_stop_hook_already_active(tmp_path):
    # stop_hook_active=true means the agent is already continuing because a
    # stop hook blocked it. Blocking again would trap an agent that
    # legitimately has nothing to write in an endless loop — its own escape
    # hatch ("say why in your final message") would re-trigger the block.
    make_iteration(tmp_path, 2, [])  # still empty: the nudge did not work
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, SCRIPT, "review.md"],
        input=json.dumps({"stop_hook_active": True}),
        capture_output=True, text=True, cwd=str(tmp_path), env=env,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""  # no block JSON the second time
    assert "letting the agent go" in audit_log(tmp_path)


def test_anchors_to_project_dir_not_cwd(tmp_path):
    # The original bug: the marker was read relative to the cwd, while the
    # audit log anchored to CLAUDE_PROJECT_DIR — the hook could check one
    # tree and log to another, or silently check nothing at all.
    project = tmp_path / "project"
    folder = project / "docs" / "2"
    folder.mkdir(parents=True)
    (project / "docs" / ".current_iteration").write_text("2")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    result = subprocess.run(
        [sys.executable, SCRIPT, "review.md"],
        input="{}", capture_output=True, text=True,
        cwd=str(elsewhere), env=env,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"  # docs/2 has no review.md
    assert "review.md" in payload["reason"]
