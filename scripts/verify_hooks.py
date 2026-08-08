#!/usr/bin/env python3
"""Exercise every hook script with a realistic payload and print the result.

This is a demonstration harness, not a test suite. The unit tests in tests/
assert correctness; this script *shows you the mechanism working* — the exact
JSON going in, the exit code coming out, and the message the agent would see.

Run it from the repository root:

    python3 scripts/verify_hooks.py

Every case prints PASS/FAIL against its expected outcome, so it doubles as a
smoke test. Exit code is 0 if every case behaved as expected, 1 otherwise.

Nothing here touches the real docs/ directory — each case that needs files
builds them in a temporary directory that is removed afterwards.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# Every case runs against a throwaway directory pinned as CLAUDE_PROJECT_DIR,
# the same way the hook harness pins the real project root. Pinning it keeps
# the guards anchored where each case expects, and keeps their audit log out
# of the real docs/.
DEFAULT_SCOPE = Path(tempfile.mkdtemp())

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, RED, YELLOW = "\033[32m", "\033[31m", "\033[33m"

results = []


def banner(title, subtitle=""):
    print(f"\n{BOLD}{'=' * 72}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    if subtitle:
        print(f"{DIM}{subtitle}{RESET}")
    print(f"{BOLD}{'=' * 72}{RESET}")


def run_hook(script, payload, cwd=None, args=()):
    """Pipe a tool call to a hook exactly as the harness would."""
    workdir = Path(cwd) if cwd else DEFAULT_SCOPE
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(workdir),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(workdir)},
    )
    return proc


def case(label, script, payload, expect_exit, *, cwd=None, args=(),
         expect_stdout_json=False, expect_warning=None):
    proc = run_hook(script, payload, cwd=cwd, args=args)
    ok = proc.returncode == expect_exit
    if expect_stdout_json:
        try:
            ok = ok and json.loads(proc.stdout).get("decision") == "block"
        except (json.JSONDecodeError, ValueError):
            ok = False
    if expect_warning is not None:
        # Warn-only hooks speak via JSON on stdout. Stderr from a hook that
        # exits 0 goes to the debug log only and Claude never sees it, so
        # asserting on stderr here would pass while the hook was inert.
        try:
            payload_out = json.loads(proc.stdout) if proc.stdout.strip() else None
        except (json.JSONDecodeError, ValueError):
            payload_out = None
        got_warning = bool(payload_out and payload_out.get("systemMessage"))
        ok = ok and (got_warning == expect_warning)
        if expect_warning and got_warning:
            ok = ok and bool(
                payload_out.get("hookSpecificOutput", {}).get("additionalContext")
            )

    verdict = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    results.append(ok)

    print(f"\n  {BOLD}{label}{RESET}")
    shown = payload.get("tool_input", {})
    detail = shown.get("file_path") or (shown.get("prompt", "")[:60] + "…" if shown.get("prompt") else "{}")
    print(f"    {DIM}in  :{RESET} {detail}")
    if args:
        print(f"    {DIM}args:{RESET} {' '.join(args)}")
    print(f"    {DIM}exit:{RESET} {proc.returncode}   (expected {expect_exit})   {verdict}")
    if proc.stderr.strip():
        print(f"    {DIM}stderr:{RESET} {YELLOW}{proc.stderr.strip()[:200]}{RESET}")
    if proc.stdout.strip():
        print(f"    {DIM}stdout:{RESET} {proc.stdout.strip()[:200]}")


# ---------------------------------------------------------------------------
# 1. guard_orchestrator_write.py — PreToolUse, hard-block
# ---------------------------------------------------------------------------

banner(
    "1. guard_orchestrator_write.py",
    "PreToolUse on Write|Edit. Structural rule -> hard-blocks with exit 2.\n"
    "Enforces the blinding rule: the orchestrator writes 2 files, both in\n"
    "docs/1, and nothing else. Paths are anchored to the project root.",
)

case("allows clarification.md in docs/1", "guard_orchestrator_write.py",
     {"tool_input": {"file_path": "docs/1/clarification.md"}}, 0)
case("allows the brief snapshot", "guard_orchestrator_write.py",
     {"tool_input": {"file_path": "docs/1/brief-snapshot.md"}}, 0)
case("REFUSES clarification.md outside docs/1", "guard_orchestrator_write.py",
     {"tool_input": {"file_path": "docs/2/clarification.md"}}, 2)
case("REFUSES the iteration cursor (iteration.py owns it)", "guard_orchestrator_write.py",
     {"tool_input": {"file_path": "docs/.current_iteration"}}, 2)
case("REFUSES the design", "guard_orchestrator_write.py",
     {"tool_input": {"file_path": "docs/2/definition.md"}}, 2)
case("REFUSES the review", "guard_orchestrator_write.py",
     {"tool_input": {"file_path": "docs/2/review.md"}}, 2)
case("REFUSES arbitrary source files", "guard_orchestrator_write.py",
     {"tool_input": {"file_path": "src/main.py"}}, 2)

lookalike_root = Path(tempfile.mkdtemp())
case("REFUSES a lookalike path outside the project", "guard_orchestrator_write.py",
     {"tool_input": {"file_path": str(lookalike_root / "docs" / "1" / "clarification.md")}}, 2)
shutil.rmtree(lookalike_root, ignore_errors=True)

# ---------------------------------------------------------------------------
# 2. guard_output_path.py — PreToolUse, hard-block, iteration-scoped
# ---------------------------------------------------------------------------

banner(
    "2. guard_output_path.py",
    "PreToolUse on Write|Edit. Takes allowed filenames as CLI args, so one\n"
    "generic guard serves all four agents. Scopes to the CURRENT iteration,\n"
    "and anchors to the project root — a path merely ENDING in docs/<n>/<file>\n"
    "is not enough.",
)

scope = Path(tempfile.mkdtemp())
(scope / "docs" / "2").mkdir(parents=True)
(scope / "docs" / "1").mkdir(parents=True)
(scope / "docs" / ".current_iteration").write_text("2")

print(f"\n  {DIM}(temp repo with docs/.current_iteration = 2){RESET}")

case("designer may write definition.md in iter 2", "guard_output_path.py",
     {"tool_input": {"file_path": "docs/2/definition.md"}}, 0,
     cwd=scope, args=("definition.md", "dispositions.md"))
case("designer may write dispositions.md in iter 2", "guard_output_path.py",
     {"tool_input": {"file_path": "docs/2/dispositions.md"}}, 0,
     cwd=scope, args=("definition.md", "dispositions.md"))
case("REFUSES a PREVIOUS iteration (no clobbering)", "guard_output_path.py",
     {"tool_input": {"file_path": "docs/1/definition.md"}}, 2,
     cwd=scope, args=("definition.md", "dispositions.md"))
case("REFUSES another agent's file", "guard_output_path.py",
     {"tool_input": {"file_path": "docs/2/review.md"}}, 2,
     cwd=scope, args=("definition.md", "dispositions.md"))

evil_root = Path(tempfile.mkdtemp())
case("REFUSES a lookalike tree outside the project", "guard_output_path.py",
     {"tool_input": {"file_path": str(evil_root / "docs" / "2" / "definition.md")}}, 2,
     cwd=scope, args=("definition.md", "dispositions.md"))
shutil.rmtree(evil_root, ignore_errors=True)

case("REFUSES unknown options rather than guessing", "guard_output_path.py",
     {"tool_input": {"file_path": "docs/2/definition.md"}}, 2,
     cwd=scope, args=("--iteration", "2", "definition.md"))

# The guards keep their own mechanical record — the audit log. Every decision
# above appended a line to docs/hook-audit.log inside the temp scope. The
# live-fire test cross-checks quoted evidence against exactly this file.
audit_log = scope / "docs" / "hook-audit.log"
audit_lines = audit_log.read_text().strip().splitlines() if audit_log.exists() else []
audit_ok = any(" block " in line for line in audit_lines) and any(
    " allow " in line for line in audit_lines)
results.append(audit_ok)
verdict = f"{GREEN}PASS{RESET}" if audit_ok else f"{RED}FAIL{RESET}"
print(f"\n  {BOLD}every decision above was appended to docs/hook-audit.log{RESET}")
for line in audit_lines[-3:]:
    print(f"    {DIM}{line}{RESET}")
print(f"    {DIM}log :{RESET} {len(audit_lines)} lines, allow and block both present   {verdict}")

shutil.rmtree(scope, ignore_errors=True)

# ---------------------------------------------------------------------------
# 3. warn_paste_in_prompt.py — PreToolUse on Agent, WARN ONLY
# ---------------------------------------------------------------------------

banner(
    "3. warn_paste_in_prompt.py",
    "PreToolUse on Agent (delegation, not writes). HEURISTIC rule -> warns but\n"
    "ALWAYS exits 0, so a false positive cannot halt the pipeline.\n"
    "Warns via JSON on stdout: systemMessage (to the user) +\n"
    "additionalContext (to Claude). Stderr on exit 0 would be invisible.",
)

case("silent on a proper paths-only delegation", "warn_paste_in_prompt.py",
     {"tool_input": {"prompt": "Read docs/1/definition.md and write docs/1/review.md"}}, 0,
     expect_warning=False)
case("warns on a very long prompt (still exit 0)", "warn_paste_in_prompt.py",
     {"tool_input": {"prompt": "x" * 2100}}, 0, expect_warning=True)
case("warns on pasted markdown + code (still exit 0)", "warn_paste_in_prompt.py",
     {"tool_input": {"prompt": "Review this:\n# A\ntext\n## B\ntext\n### C\n```py\nx=1\n```"}}, 0,
     expect_warning=True)

# ---------------------------------------------------------------------------
# 4. warn_estimates_in_backlog.py — PostToolUse, WARN ONLY
# ---------------------------------------------------------------------------

banner(
    "4. warn_estimates_in_backlog.py",
    "PostToolUse on Write. Must be Post: it reads the file's CONTENT, which\n"
    "does not exist until the write has happened. Heuristic -> warn only,\n"
    "via JSON on stdout (systemMessage + additionalContext).",
)

tmp = Path(tempfile.mkdtemp())
clean = tmp / "clean.md"
clean.write_text("# Backlog\n\n### Story 1.1\nAcceptance criteria:\n- works\n")
dirty = tmp / "dirty.md"
dirty.write_text("# Backlog\n\n### Story 1.1\nEstimate: 3 days\n5 points\n")

case("silent on a clean backlog", "warn_estimates_in_backlog.py",
     {"tool_input": {"file_path": str(clean)}}, 0, expect_warning=False)
case("warns on time units and story points (still exit 0)", "warn_estimates_in_backlog.py",
     {"tool_input": {"file_path": str(dirty)}}, 0, expect_warning=True)

shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# 5. validate_review_format.py — PostToolUse, HARD-BLOCK
# ---------------------------------------------------------------------------

banner(
    "5. validate_review_format.py",
    "PostToolUse on Write. PostToolUse CANNOT block -- the file is already on\n"
    "disk. Exit 2 shows stderr to the reviewer so it rewrites the file. The\n"
    "malformed version existed in between. Catches self-contradiction.",
)

tmp = Path(tempfile.mkdtemp())


def review(name, body):
    p = tmp / name
    p.write_text(body)
    return {"tool_input": {"file_path": str(p)}}


TABLE_ALL_PASS = """
| Dimension   | Verdict | Finding |
|-------------|---------|---------|
| Coverage    | PASS    |  |
| Soundness   | PASS    |  |
| Decisions   | PASS    |  |
| Gaps        | PASS    |  |
| Over-reach  | PASS    |  |
"""

TABLE_ONE_FAIL = TABLE_ALL_PASS.replace("| Soundness   | PASS    |",
                                        "| Soundness   | FAIL    |")

case("accepts APPROVED with all PASS", "validate_review_format.py",
     review("a.md", "Verdict: APPROVED\n" + TABLE_ALL_PASS), 0)
case("accepts CHANGES REQUESTED with a FAIL", "validate_review_format.py",
     review("b.md", "Verdict: CHANGES REQUESTED\n" + TABLE_ONE_FAIL), 0)
case("accepts QUESTIONS with no table", "validate_review_format.py",
     review("c.md", "Verdict: QUESTIONS\n\n## Questions for human\n- Which store?\n"), 0)
case("REFUSES a missing verdict line", "validate_review_format.py",
     review("d.md", "## Review\nLooks good.\n"), 2)
case("REFUSES APPROVED that contradicts a FAIL", "validate_review_format.py",
     review("e.md", "Verdict: APPROVED\n" + TABLE_ONE_FAIL), 2)
case("REFUSES CHANGES REQUESTED with all PASS", "validate_review_format.py",
     review("f.md", "Verdict: CHANGES REQUESTED\n" + TABLE_ALL_PASS), 2)
case("REFUSES a missing dimension", "validate_review_format.py",
     review("g.md", "Verdict: APPROVED\n" + TABLE_ALL_PASS.replace(
         "| Over-reach  | PASS    |  |\n", "")), 2)

shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# 6. check_subagent_output.py — SubagentStop, JSON OUTPUT
# ---------------------------------------------------------------------------

banner(
    "6. check_subagent_output.py",
    "SubagentStop -- fires when a delegated AGENT finishes, not around a tool\n"
    "call. Gets no file_path, so the check is deliberately coarse.\n"
    "decision:'block' does NOT stop the agent: it KEEPS IT RUNNING and hands\n"
    "the reason to the SUBAGENT (not the orchestrator) as its next instruction.",
)

tmp = Path(tempfile.mkdtemp())
(tmp / "docs" / "2").mkdir(parents=True)
(tmp / "docs" / ".current_iteration").write_text("2")
case("keeps agent running when it wrote nothing (JSON on stdout)", "check_subagent_output.py",
     {}, 0, cwd=tmp, expect_stdout_json=True)

(tmp / "docs" / "2" / "definition.md").write_text("# Design")
case("silent once the agent has written output", "check_subagent_output.py",
     {}, 0, cwd=tmp)

shutil.rmtree(tmp, ignore_errors=True)

tmp = Path(tempfile.mkdtemp())
(tmp / "docs").mkdir()
case("stays out of the way with no cursor file", "check_subagent_output.py",
     {}, 0, cwd=tmp)
shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
# 7. iteration.py --max — the hard cap (not a hook)
# ---------------------------------------------------------------------------

banner(
    "7. iteration.py next — the cap lives in the script",
    "Not a hook -- a gate. The 4-iteration cap is a constant in iteration.py:\n"
    "no flag is needed to arm it, and --max can lower it but never raise it.\n"
    "The script also records each new folder in docs/.current_iteration, so\n"
    "the guards' cursor can never be forgotten or out of step.",
)

tmp = Path(tempfile.mkdtemp())
(tmp / "scripts").mkdir()
shutil.copy(SCRIPTS / "iteration.py", tmp / "scripts" / "iteration.py")

for i in range(1, 6):
    proc = subprocess.run(
        [sys.executable, "scripts/iteration.py", "next"],
        capture_output=True, text=True, cwd=str(tmp),
    )
    expected = 0 if i <= 4 else 1
    ok = proc.returncode == expected
    results.append(ok)
    verdict = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    msg = (proc.stdout or proc.stderr).strip()
    print(f"    call {i}: exit={proc.returncode} (expected {expected}) {verdict}  {DIM}{msg}{RESET}")

created = sorted(p.name for p in (tmp / "docs").iterdir() if p.is_dir())
no_fifth = "5" not in created
results.append(no_fifth)
print(f"\n    folders created: {created}   "
      f"{GREEN + 'PASS' + RESET if no_fifth else RED + 'FAIL' + RESET} (no 5th folder)")

cursor = (tmp / "docs" / ".current_iteration").read_text().strip()
cursor_ok = cursor == "4"
results.append(cursor_ok)
print(f"    docs/.current_iteration: {cursor!r}   "
      f"{GREEN + 'PASS' + RESET if cursor_ok else RED + 'FAIL' + RESET} "
      f"(cursor tracks the newest folder)")

proc = subprocess.run(
    [sys.executable, "scripts/iteration.py", "next", "--max", "99"],
    capture_output=True, text=True, cwd=str(tmp),
)
raise_ok = proc.returncode == 1
results.append(raise_ok)
print(f"    next --max 99: exit={proc.returncode} (expected 1) "
      f"{GREEN + 'PASS' + RESET if raise_ok else RED + 'FAIL' + RESET} "
      f"(--max cannot raise the cap)")

shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------------------

shutil.rmtree(DEFAULT_SCOPE, ignore_errors=True)

banner("SUMMARY")
passed, total = sum(results), len(results)
colour = GREEN if passed == total else RED
print(f"\n  {colour}{BOLD}{passed}/{total} cases behaved as expected{RESET}\n")
sys.exit(0 if passed == total else 1)
