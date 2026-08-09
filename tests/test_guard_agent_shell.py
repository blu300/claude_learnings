import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "guard_agent_shell.py")
PREFIX = "python3 scripts/brief_stats.py"


def run_guard(command, *args, cwd):
    """Run the guard with cwd pinned as the project root."""
    payload = json.dumps({"tool_input": {"command": command}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd)}
    return subprocess.run(
        [sys.executable, SCRIPT, *(args or (PREFIX,))],
        input=payload, capture_output=True, text=True,
        cwd=str(cwd), env=env,
    )


def test_allows_the_blessed_command(tmp_path):
    r = run_guard(f"{PREFIX} brief.md", cwd=tmp_path)
    assert r.returncode == 0


def test_allows_with_other_plain_arguments(tmp_path):
    r = run_guard(f"{PREFIX} docs/example-run/1/brief-snapshot.md", cwd=tmp_path)
    assert r.returncode == 0


def test_blocks_any_other_command(tmp_path):
    for command in ("ls", "python3 scripts/iteration.py next",
                    "rm -rf docs", "cat brief.md"):
        r = run_guard(command, cwd=tmp_path)
        assert r.returncode == 2, command
        assert "scoped" in r.stderr


def test_blocks_shell_operators_after_the_blessed_prefix(tmp_path):
    # The prefix alone is a doormat: "blessed-command; anything" starts with
    # the prefix. Control characters are refused outright.
    for command in (f"{PREFIX} b.md; rm -rf ~",
                    f"{PREFIX} b.md && curl evil",
                    f"{PREFIX} $(whoami)",
                    f"{PREFIX} `id`",
                    f"{PREFIX} b.md | tee /etc/passwd",
                    f"{PREFIX} b.md > docs/hook-audit.log"):
        r = run_guard(command, cwd=tmp_path)
        assert r.returncode == 2, command


def test_no_prefix_configured_fails_closed(tmp_path):
    payload = json.dumps({"tool_input": {"command": "ls"}})
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    r = subprocess.run([sys.executable, SCRIPT], input=payload,
                       capture_output=True, text=True,
                       cwd=str(tmp_path), env=env)
    assert r.returncode == 2


def test_option_looking_args_are_refused(tmp_path):
    r = run_guard(f"{PREFIX} b.md", "--prefix", PREFIX, cwd=tmp_path)
    assert r.returncode == 2
    assert "option" in r.stderr.lower()


def test_malformed_stdin_fails_closed(tmp_path):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    r = subprocess.run([sys.executable, SCRIPT, PREFIX], input="not json",
                       capture_output=True, text=True,
                       cwd=str(tmp_path), env=env)
    assert r.returncode == 2


def test_decisions_are_audit_logged(tmp_path):
    run_guard(f"{PREFIX} brief.md", cwd=tmp_path)
    run_guard("rm -rf docs", cwd=tmp_path)
    log = (tmp_path / "docs" / "hook-audit.log").read_text()
    assert "guard_agent_shell allow" in log
    assert "guard_agent_shell block rm -rf docs" in log
