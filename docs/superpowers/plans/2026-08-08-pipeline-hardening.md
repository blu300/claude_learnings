# Pipeline Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the four-agent design-cycle pipeline against judgement drift, state loss, and prose-only enforcement.

**Architecture:** Three phases of changes — mechanical hooks first (cheapest, highest leverage), then state-flow fixes, then prompt-level drift mitigations. Each phase builds on the previous but is independently useful.

**Tech Stack:** Python 3 scripts (hooks), Markdown (agent prompts), YAML frontmatter (hook declarations)

## Global Constraints

- All hook scripts live in `scripts/` and use the same pattern as `guard_output_path.py`: read tool call JSON from stdin, exit 0 to allow, exit 2 to block, stderr message shown to agent.
- Warn-only hooks exit 0 but still print to stderr.
- No external dependencies — stdlib only.
- All tests use pytest with no fixtures beyond tmp_path.

---

### Task 1: Add --max flag to iteration.py

**Files:**
- Modify: `scripts/iteration.py:56-79` (the `main` function)
- Test: `tests/test_iteration.py` (create)

**Interfaces:**
- Consumes: nothing new
- Produces: `iteration.py next --max N` exits 1 with message when at cap

- [ ] **Step 1: Write the failing test**

```python
# tests/test_iteration.py
import subprocess
from pathlib import Path

def test_next_respects_max(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    docs = tmp_path / "docs"
    for i in range(1, 5):
        (docs / str(i)).mkdir(parents=True)

    result = subprocess.run(
        ["python3", "scripts/iteration.py", "next", "--max", "4"],
        capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 1
    assert "maximum" in result.stderr.lower()


def test_next_allows_below_max(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    docs = tmp_path / "docs"
    for i in range(1, 3):
        (docs / str(i)).mkdir(parents=True)

    result = subprocess.run(
        ["python3", "scripts/iteration.py", "next", "--max", "4"],
        capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 0
    assert "docs/3" in result.stdout or "docs\\3" in result.stdout


def test_next_without_max_has_no_cap(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    docs = tmp_path / "docs"
    for i in range(1, 20):
        (docs / str(i)).mkdir(parents=True)

    result = subprocess.run(
        ["python3", "scripts/iteration.py", "next"],
        capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_iteration.py -v`
Expected: FAIL — `--max` not recognized

- [ ] **Step 3: Implement --max in iteration.py**

Replace the `next` command block in `main()`:

```python
if command == "next":
    max_iterations = None
    if "--max" in argv:
        max_idx = argv.index("--max")
        if max_idx + 1 < len(argv) and argv[max_idx + 1].isdigit():
            max_iterations = int(argv[max_idx + 1])

    if max_iterations and found and found[-1] >= max_iterations:
        print(
            f"Maximum of {max_iterations} iterations reached. "
            f"Current highest: docs/{found[-1]}",
            file=sys.stderr,
        )
        return 1

    number = (found[-1] + 1) if found else 1
    folder = DOCS / str(number)
    folder.mkdir(parents=True)
    print(folder)
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_iteration.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/iteration.py tests/test_iteration.py
git commit -m "feat: add --max flag to iteration.py next command"
```

---

### Task 2: Scope guard_output_path.py to current iteration and multiple filenames

**Files:**
- Modify: `scripts/guard_output_path.py`
- Test: `tests/test_guard_output_path.py` (create)

**Interfaces:**
- Consumes: `docs/.current_iteration` file (written by orchestrator)
- Produces: `guard_output_path.py <filename1> [filename2...] [--iteration N]` — pass if path matches any filename AND the correct iteration

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_guard_output_path.py
import json
import subprocess
from pathlib import Path

def run_guard(tmp_path, tool_input_path, *args):
    """Helper to run the guard with given stdin and args."""
    input_json = json.dumps({"tool_input": {"file_path": tool_input_path}})
    result = subprocess.run(
        ["python3", "scripts/guard_output_path.py", *args],
        input=input_json, capture_output=True, text=True, cwd=tmp_path
    )
    return result


def test_multiple_filenames_first_matches(tmp_path):
    r = run_guard(tmp_path, "docs/2/definition.md", "definition.md", "dispositions.md")
    assert r.returncode == 0


def test_multiple_filenames_second_matches(tmp_path):
    r = run_guard(tmp_path, "docs/2/dispositions.md", "definition.md", "dispositions.md")
    assert r.returncode == 0


def test_multiple_filenames_none_match(tmp_path):
    r = run_guard(tmp_path, "docs/2/review.md", "definition.md", "dispositions.md")
    assert r.returncode == 2


def test_iteration_scoping_correct(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / ".current_iteration").write_text("3")
    r = run_guard(tmp_path, "docs/3/review.md", "review.md")
    assert r.returncode == 0


def test_iteration_scoping_wrong_number(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / ".current_iteration").write_text("3")
    r = run_guard(tmp_path, "docs/1/review.md", "review.md")
    assert r.returncode == 2
    assert "iteration" in r.stderr.lower()


def test_no_iteration_file_allows_any(tmp_path):
    r = run_guard(tmp_path, "docs/5/review.md", "review.md")
    assert r.returncode == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_guard_output_path.py -v`
Expected: multiple filenames tests and iteration tests FAIL

- [ ] **Step 3: Rewrite guard_output_path.py**

```python
#!/usr/bin/env python3
"""Block an agent from writing anywhere except its allowed output file(s).

Usage:
    guard_output_path.py <filename> [filename2 ...] 

Reads docs/.current_iteration to scope writes to the active iteration.
If that file does not exist, any iteration number is accepted.
"""

import json
import sys
from pathlib import Path, PurePosixPath

ALLOW = 0
BLOCK = 2
CURRENT_ITERATION_FILE = Path("docs/.current_iteration")


def get_current_iteration() -> str | None:
    if CURRENT_ITERATION_FILE.exists():
        return CURRENT_ITERATION_FILE.read_text().strip()
    return None


def is_allowed(path: str, filenames: list[str], required_iteration: str | None) -> bool:
    parts = PurePosixPath(path.replace("\\", "/"))
    if parts.name not in filenames:
        return False
    if not parts.parent.name.isdigit():
        return False
    if parts.parent.parent.name != "docs":
        return False
    if required_iteration and parts.parent.name != required_iteration:
        return False
    return True


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("guard_output_path.py: no allowed filename given", file=sys.stderr)
        return BLOCK

    filenames = [a for a in argv[1:] if not a.startswith("-")]
    if not filenames:
        print("guard_output_path.py: no allowed filename given", file=sys.stderr)
        return BLOCK

    try:
        call = json.load(sys.stdin)
        path = call["tool_input"]["file_path"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print(
            "Blocked: could not read the file path from this tool call, "
            "so the write was refused rather than allowed unchecked.",
            file=sys.stderr,
        )
        return BLOCK

    required_iteration = get_current_iteration()

    if is_allowed(path, filenames, required_iteration):
        return ALLOW

    iteration_msg = f" in iteration {required_iteration}" if required_iteration else ""
    allowed_msg = " or ".join(filenames)
    print(
        f"Blocked: this agent may only write docs/<n>/{allowed_msg}{iteration_msg}. "
        f"Refused: {path}",
        file=sys.stderr,
    )
    return BLOCK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_guard_output_path.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/guard_output_path.py tests/test_guard_output_path.py
git commit -m "feat: support multiple filenames and iteration scoping in write guard"
```

---

### Task 3: Orchestrator write restriction hook

**Files:**
- Create: `scripts/guard_orchestrator_write.py`
- Test: `tests/test_guard_orchestrator_write.py` (create)

**Interfaces:**
- Consumes: tool call JSON on stdin
- Produces: exit 0 if path is `docs/<n>/clarification.md`, `docs/1/brief-snapshot.md`, or `docs/.current_iteration`; exit 2 otherwise

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_guard_orchestrator_write.py
import json
import subprocess

def run_guard(path):
    input_json = json.dumps({"tool_input": {"file_path": path}})
    return subprocess.run(
        ["python3", "scripts/guard_orchestrator_write.py"],
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_guard_orchestrator_write.py -v`
Expected: FAIL — script does not exist

- [ ] **Step 3: Implement guard_orchestrator_write.py**

```python
#!/usr/bin/env python3
"""Block the orchestrator from writing anything except clarification.md,
brief-snapshot.md, and .current_iteration."""

import json
import sys
from pathlib import PurePosixPath

ALLOW = 0
BLOCK = 2


def is_allowed(path: str) -> bool:
    normalized = PurePosixPath(path.replace("\\", "/"))

    if normalized.name == ".current_iteration" and normalized.parent.name == "docs":
        return True

    if normalized.name == "brief-snapshot.md":
        if normalized.parent.name == "1" and normalized.parent.parent.name == "docs":
            return True

    if normalized.name == "clarification.md":
        if normalized.parent.name.isdigit() and normalized.parent.parent.name == "docs":
            return True

    return False


def main() -> int:
    try:
        call = json.load(sys.stdin)
        path = call["tool_input"]["file_path"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("Blocked: could not read file path from tool call.", file=sys.stderr)
        return BLOCK

    if is_allowed(path):
        return ALLOW

    print(
        f"Blocked: orchestrator may only write clarification.md, "
        f"brief-snapshot.md, or .current_iteration. Refused: {path}",
        file=sys.stderr,
    )
    return BLOCK


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_guard_orchestrator_write.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/guard_orchestrator_write.py tests/test_guard_orchestrator_write.py
git commit -m "feat: add orchestrator write restriction hook"
```

---

### Task 4: Warn-only hooks (paste detection + estimate detection)

**Files:**
- Create: `scripts/warn_paste_in_prompt.py`
- Create: `scripts/warn_estimates_in_backlog.py`
- Test: `tests/test_warn_hooks.py` (create)

**Interfaces:**
- `warn_paste_in_prompt.py`: reads Agent tool call JSON from stdin, warns if prompt >2000 chars or contains 3+ markdown headers or fenced code blocks. Always exits 0.
- `warn_estimates_in_backlog.py`: reads Write tool call JSON from stdin, reads the file that was written, warns if it contains time-unit patterns. Always exits 0.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_warn_hooks.py
import json
import subprocess
from pathlib import Path

def test_paste_warns_on_long_prompt():
    input_json = json.dumps({"tool_input": {"prompt": "x" * 2001}})
    r = subprocess.run(
        ["python3", "scripts/warn_paste_in_prompt.py"],
        input=input_json, capture_output=True, text=True
    )
    assert r.returncode == 0
    assert "warning" in r.stderr.lower()


def test_paste_warns_on_markdown_headers():
    prompt = "# Header 1\ntext\n## Header 2\ntext\n### Header 3\ntext"
    input_json = json.dumps({"tool_input": {"prompt": prompt}})
    r = subprocess.run(
        ["python3", "scripts/warn_paste_in_prompt.py"],
        input=input_json, capture_output=True, text=True
    )
    assert r.returncode == 0
    assert "warning" in r.stderr.lower()


def test_paste_silent_on_normal_prompt():
    input_json = json.dumps({"tool_input": {"prompt": "Read docs/1/brief.md and write docs/1/clarification.md"}})
    r = subprocess.run(
        ["python3", "scripts/warn_paste_in_prompt.py"],
        input=input_json, capture_output=True, text=True
    )
    assert r.returncode == 0
    assert r.stderr == ""


def test_estimates_warns_on_time_units(tmp_path):
    backlog = tmp_path / "backlog.md"
    backlog.write_text("# Backlog\n\n### Story 1.1\nEstimate: 3 days\n")
    input_json = json.dumps({"tool_input": {"file_path": str(backlog)}})
    r = subprocess.run(
        ["python3", "scripts/warn_estimates_in_backlog.py"],
        input=input_json, capture_output=True, text=True
    )
    assert r.returncode == 0
    assert "warning" in r.stderr.lower()


def test_estimates_warns_on_story_points(tmp_path):
    backlog = tmp_path / "backlog.md"
    backlog.write_text("# Backlog\n\n### Story 1.1\n5 points\n")
    input_json = json.dumps({"tool_input": {"file_path": str(backlog)}})
    r = subprocess.run(
        ["python3", "scripts/warn_estimates_in_backlog.py"],
        input=input_json, capture_output=True, text=True
    )
    assert r.returncode == 0
    assert "warning" in r.stderr.lower()


def test_estimates_silent_on_clean_backlog(tmp_path):
    backlog = tmp_path / "backlog.md"
    backlog.write_text("# Backlog\n\n### Story 1.1\nAcceptance criteria:\n- works\n")
    input_json = json.dumps({"tool_input": {"file_path": str(backlog)}})
    r = subprocess.run(
        ["python3", "scripts/warn_estimates_in_backlog.py"],
        input=input_json, capture_output=True, text=True
    )
    assert r.returncode == 0
    assert r.stderr == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_warn_hooks.py -v`
Expected: FAIL — scripts do not exist

- [ ] **Step 3: Implement warn_paste_in_prompt.py**

```python
#!/usr/bin/env python3
"""Warn (never block) when an agent delegation prompt looks like pasted content."""

import json
import re
import sys

def main() -> int:
    try:
        call = json.load(sys.stdin)
        prompt = call["tool_input"].get("prompt", "")
    except (json.JSONDecodeError, KeyError, TypeError):
        return 0

    warnings = []

    if len(prompt) > 2000:
        warnings.append(f"Prompt is {len(prompt)} chars (>2000) — may contain pasted file content.")

    header_count = len(re.findall(r"^#{1,3} ", prompt, re.MULTILINE))
    if header_count >= 3:
        warnings.append(f"Prompt contains {header_count} markdown headers — may contain pasted file content.")

    if "```" in prompt:
        warnings.append("Prompt contains fenced code blocks — may contain pasted file content.")

    if warnings:
        print("Warning: " + " ".join(warnings), file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Implement warn_estimates_in_backlog.py**

```python
#!/usr/bin/env python3
"""Warn (never block) when a backlog contains effort estimates."""

import json
import re
import sys
from pathlib import Path

ESTIMATE_PATTERNS = [
    r"\b\d+\s*(hours?|days?|weeks?|points?|sp)\b",
    r"\b(estimate|effort|sizing)\b",
]


def main() -> int:
    try:
        call = json.load(sys.stdin)
        path = call["tool_input"]["file_path"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return 0

    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    findings = []
    for pattern in ESTIMATE_PATTERNS:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            findings.extend(matches)

    if findings:
        print(
            f"Warning: backlog appears to contain effort estimates "
            f"(found: {', '.join(str(f) for f in findings[:5])}). "
            f"The spec says not to estimate.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_warn_hooks.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/warn_paste_in_prompt.py scripts/warn_estimates_in_backlog.py tests/test_warn_hooks.py
git commit -m "feat: add warn-only hooks for paste detection and estimate detection"
```

---

### Task 5: Review format validation hook

**Files:**
- Create: `scripts/validate_review_format.py`
- Test: `tests/test_validate_review_format.py` (create)

**Interfaces:**
- Consumes: Write tool call JSON on stdin (reads the written file path)
- Produces: exit 0 if review has valid verdict + scoring table; exit 2 with explanation otherwise

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_validate_review_format.py
import json
import subprocess
from pathlib import Path

def run_validator(tmp_path, content):
    review = tmp_path / "review.md"
    review.write_text(content)
    input_json = json.dumps({"tool_input": {"file_path": str(review)}})
    return subprocess.run(
        ["python3", "scripts/validate_review_format.py"],
        input=input_json, capture_output=True, text=True
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_validate_review_format.py -v`
Expected: FAIL — script does not exist

- [ ] **Step 3: Implement validate_review_format.py**

```python
#!/usr/bin/env python3
"""Validate that review.md has the correct structured format.

Hard-blocks (exit 2) if:
- First line is not a valid verdict
- Scoring table is missing or incomplete
- Verdict contradicts scoring (APPROVED with FAILs, or CHANGES REQUESTED with all PASS)
"""

import json
import re
import sys
from pathlib import Path

ALLOW = 0
BLOCK = 2
VALID_VERDICTS = {"APPROVED", "CHANGES REQUESTED", "QUESTIONS"}
REQUIRED_DIMENSIONS = {"coverage", "soundness", "decisions", "gaps", "over-reach"}


def validate(content: str) -> str | None:
    lines = content.strip().splitlines()
    if not lines:
        return "File is empty — expected Verdict: line"

    first_line = lines[0].strip()
    match = re.match(r"^Verdict:\s*(.+)$", first_line)
    if not match:
        return f"First line must be 'Verdict: APPROVED|CHANGES REQUESTED|QUESTIONS', got: '{first_line}'"

    verdict = match.group(1).strip()
    if verdict not in VALID_VERDICTS:
        return f"Invalid verdict '{verdict}'. Must be one of: {', '.join(VALID_VERDICTS)}"

    if verdict == "QUESTIONS":
        return None

    scores = {}
    for line in lines:
        row_match = re.match(r"\|\s*(\w[\w\s-]*?)\s*\|\s*(PASS|FAIL)\s*\|", line)
        if row_match:
            dim = row_match.group(1).strip().lower()
            score = row_match.group(2).strip()
            scores[dim] = score

    missing = REQUIRED_DIMENSIONS - set(scores.keys())
    if missing:
        return f"Missing scored dimensions: {', '.join(sorted(missing))}"

    has_fail = any(v == "FAIL" for v in scores.values())
    all_pass = all(v == "PASS" for v in scores.values())

    if verdict == "APPROVED" and has_fail:
        failed = [d for d, v in scores.items() if v == "FAIL"]
        return f"Verdict is APPROVED but these dimensions are FAIL: {', '.join(failed)}"

    if verdict == "CHANGES REQUESTED" and all_pass:
        return "Verdict is CHANGES REQUESTED but all dimensions are PASS — contradiction"

    return None


def main() -> int:
    try:
        call = json.load(sys.stdin)
        path = call["tool_input"]["file_path"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("Blocked: could not read file path from tool call.", file=sys.stderr)
        return BLOCK

    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"Blocked: could not read review file: {e}", file=sys.stderr)
        return BLOCK

    error = validate(content)
    if error:
        print(f"Blocked: {error}", file=sys.stderr)
        return BLOCK

    return ALLOW


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_validate_review_format.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_review_format.py tests/test_validate_review_format.py
git commit -m "feat: add review format validation hook"
```

---

### Task 6: Update agent prompts and SKILL.md for Phase 1 hooks

**Files:**
- Modify: `.claude/agents/designer.md` (hook declaration for multiple filenames)
- Modify: `.claude/agents/reviewer.md` (add PostToolUse hook for format validation)
- Modify: `.claude/agents/backlog-writer.md` (add PostToolUse hook for estimates)
- Modify: `.claude/skills/design-cycle/SKILL.md` (iteration cap in command, write .current_iteration, orchestrator hook)

**Interfaces:**
- Consumes: all scripts from Tasks 1–5
- Produces: updated pipeline configuration

- [ ] **Step 1: Update designer.md hook to allow dispositions.md**

In `.claude/agents/designer.md`, change the hook command from:

```yaml
command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/guard_output_path.py" definition.md'
```

to:

```yaml
command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/guard_output_path.py" definition.md dispositions.md'
```

- [ ] **Step 2: Add PostToolUse hook to reviewer.md**

In `.claude/agents/reviewer.md`, add after the existing PreToolUse hook:

```yaml
  PostToolUse:
    - matcher: "Write"
      hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/validate_review_format.py"'
```

- [ ] **Step 3: Add PostToolUse hook to backlog-writer.md**

In `.claude/agents/backlog-writer.md`, add after the existing PreToolUse hook:

```yaml
  PostToolUse:
    - matcher: "Write"
      hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/warn_estimates_in_backlog.py"'
```

- [ ] **Step 4: Update SKILL.md**

In `.claude/skills/design-cycle/SKILL.md`:

a) Change step 1 from `python3 scripts/iteration.py next` to:
```
python3 scripts/iteration.py next --max 4
```

b) Add after step 1, before step 2:
```
   Write the iteration number to `docs/.current_iteration` before each
   delegation: `echo <n> > docs/.current_iteration`
```

c) Add hook declarations to the frontmatter (after `allowed-tools`):
```yaml
hooks:
  PreToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/guard_orchestrator_write.py"'
    - matcher: "Agent"
      hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/warn_paste_in_prompt.py"'
```

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/designer.md .claude/agents/reviewer.md .claude/agents/backlog-writer.md .claude/skills/design-cycle/SKILL.md
git commit -m "feat: wire Phase 1 hooks into agent and skill definitions"
```

---

### Task 7: Designer writes dispositions.md

**Files:**
- Modify: `.claude/agents/designer.md` (add dispositions instructions)

**Interfaces:**
- Consumes: review from previous iteration
- Produces: `docs/<n>/dispositions.md` alongside `definition.md`

- [ ] **Step 1: Add dispositions instructions to designer.md**

Insert after the "Handling review feedback" section:

```markdown
## Dispositions log

On every iteration after the first (when you receive a review to respond to),
write `dispositions.md` to the same folder as your design. This is a separate
file from the design — it records what you did with each review finding.

If `dispositions.md` exists from a prior iteration, read all prior ones to
maintain continuity.

Format:

```markdown
# Dispositions — Iteration <n>

Prior iterations: docs/<n-1>/dispositions.md (if exists)

## Accepted
- [Finding from review] — adopted because: <reason>

## Rejected
- [Finding from review] — rejected because: <reason>

## Deferred
- [Finding from review] — cannot address without: <what's missing>
```

Every finding from the review must appear in exactly one section. Do not omit
findings.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/agents/designer.md
git commit -m "feat: instruct designer to write dispositions.md"
```

---

### Task 8: Reviewer reads dispositions

**Files:**
- Modify: `.claude/agents/reviewer.md` (add dispositions reading)
- Modify: `.claude/skills/design-cycle/SKILL.md` (pass dispositions path to reviewer)

**Interfaces:**
- Consumes: `docs/<n>/dispositions.md` from the designer
- Produces: reviewer that won't re-litigate settled arguments

- [ ] **Step 1: Add dispositions reading to reviewer.md**

Insert after "What you are given":

```markdown
You may also be given a path to a dispositions log from the current or prior
iterations. If provided, read it before reviewing. If a finding was previously
raised and the designer rejected it with reasoning you cannot specifically
refute, do not re-raise it. Your job is to find new problems or demonstrate
why the designer's reasoning is wrong — not to repeat yourself.
```

- [ ] **Step 2: Update SKILL.md step 6**

Change step 6 to also pass dispositions:

```
6. Delegate to the `reviewer` agent. Tell it to read `<dir>/definition.md`,
   the brief snapshot and the clarification path, and to write
   `<dir>/review.md`. If `dispositions.md` files exist from any iteration,
   pass all their paths. Always spawn a fresh reviewer.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/reviewer.md .claude/skills/design-cycle/SKILL.md
git commit -m "feat: reviewer reads dispositions to avoid re-litigation"
```

---

### Task 9: Contradiction handling and brief snapshot

**Files:**
- Modify: `.claude/skills/design-cycle/SKILL.md` (brief snapshot + contradiction marking)

**Interfaces:**
- Consumes: original brief path from user
- Produces: `docs/1/brief-snapshot.md`, strikethrough-marked contradictions in clarification

- [ ] **Step 1: Add brief snapshot to SKILL.md**

Insert into step 1, after creating the iteration folder:

```
   After creating `docs/1`, copy the brief to `docs/1/brief-snapshot.md`.
   From this point forward, all references to "the brief" mean the snapshot
   path, not the original. Agents never read the original.
```

- [ ] **Step 2: Add contradiction handling to SKILL.md**

Insert after step 4 (writing answers):

```
   When writing answers that contradict a previous answer in the same file,
   strike through the earlier answer with `~~` and add a note:
   `**Superseded by #<n>**`. The designer needs to see both the original
   assumption and the correction.
```

- [ ] **Step 3: Update the orchestrator read rules**

Replace the existing reading rules with:

```
- You may read: `clarification.md`, `dispositions.md`, and the `Verdict:`
  line of `review.md`. You never read `definition.md`.
```

- [ ] **Step 4: Fix step 9 reporting**

Replace step 9 with:

```
9. Read the final iteration's `dispositions.md` (if it exists). Report to
   the human: the number of iterations, the paths to the approved definition
   and the backlog, and any findings the designer accepted (from the Accepted
   section of dispositions.md).
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/design-cycle/SKILL.md
git commit -m "feat: add brief snapshot, contradiction handling, and fix step 9 reporting"
```

---

### Task 10: Reviewer rubric and structured scoring

**Files:**
- Modify: `.claude/agents/reviewer.md` (add rubric + scoring format)

**Interfaces:**
- Consumes: design document and criteria
- Produces: structured review with scoring table (validated by Task 5's hook)

- [ ] **Step 1: Add scoring section to reviewer.md**

Insert after "How to review", before "What you write":

```markdown
## Scoring

After completing your review, score each dimension:

| Dimension   | Verdict | Finding (if FAIL) |
|-------------|---------|-------------------|
| Coverage    | PASS/FAIL | ... |
| Soundness   | PASS/FAIL | ... |
| Decisions   | PASS/FAIL | ... |
| Gaps        | PASS/FAIL | ... |
| Over-reach  | PASS/FAIL | ... |

Derive your verdict mechanically:
- Any FAIL → `Verdict: CHANGES REQUESTED`
- All PASS → `Verdict: APPROVED`
- Cannot score because criteria are ambiguous → `Verdict: QUESTIONS`

A dimension is FAIL when it has at least one **blocking** finding. Non-blocking
findings do not cause FAIL.

## Approval threshold

A design is APPROVED when:
- Every criterion from the brief/clarification is addressed (Coverage PASS)
- The approach will work under the stated constraints (Soundness PASS)
- Every significant choice is justified, not merely asserted (Decisions PASS)
- Nothing is left undefined that would block implementation (Gaps PASS)
- Nothing is designed that the criteria did not ask for (Over-reach PASS)

"Addressed" means the design takes a position. It does not mean the position
is perfect.
```

- [ ] **Step 2: Update "What you write" section**

Replace the current "What you write" section with:

```markdown
## What you write

Write to exactly the path you were given, and nothing else. Structure:

First line — the verdict (derived from your scoring):

```
Verdict: APPROVED
Verdict: CHANGES REQUESTED
Verdict: QUESTIONS
```

Then the scoring table (as above).

Then:

- **Blocking** — findings that caused a FAIL score.
- **Non-blocking** — findings worth recording but not worth another round.
- **Questions for human** — only when the verdict is `QUESTIONS`.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/reviewer.md
git commit -m "feat: add structured scoring rubric to reviewer"
```

---

### Task 11: Clarifier rubric, designer deference check, backlog granularity

**Files:**
- Modify: `.claude/agents/clarifier.md` (blocking/useful rubric)
- Modify: `.claude/agents/designer.md` (deference self-check)
- Modify: `.claude/agents/backlog-writer.md` (granularity heuristic)

**Interfaces:**
- Consumes: nothing new
- Produces: calibrated prompts that reduce drift

- [ ] **Step 1: Add blocking/useful rubric to clarifier.md**

Replace "Mark each question **blocking** or **useful**. Be sparing: everything marked blocking stops the pipeline until a human replies." with:

```markdown
Mark each question **blocking** or **useful**:

- **Blocking**: the designer would have to invent an answer, AND getting that
  invention wrong means rework (not just suboptimality).
- **Useful**: everything else. A useful question the human skips costs nothing;
  a blocking question the human ignores stops the pipeline.

When in doubt, mark it useful.
```

- [ ] **Step 2: Add deference self-check to designer.md**

Insert after the dispositions log section:

```markdown
## Self-check on deference

If you accepted every finding from the review (or rejected none), add a
paragraph at the end of `dispositions.md` titled "Why full acceptance was
appropriate" explaining why every point happened to be correct this time. If
you cannot write that paragraph honestly, go back and find at least one point
where your original reasoning was sound and defend it.
```

- [ ] **Step 3: Add granularity heuristic to backlog-writer.md**

Insert after the decomposition rules:

```markdown
## Story sizing heuristic

A well-sized story is completable in 1–3 working days by one person who knows
the codebase. Use these signals:

- If the tasks under a story span more than 3 files in unrelated parts of the
  system, it is probably two stories.
- If you cannot write concrete acceptance criteria, the story is too vague —
  either break it down or move it to Unallocated with a note on what's missing.
- If the story is a single obvious change (rename, config tweak, one-line
  fix), it should be a task under a broader story, not a story itself.

When you cannot judge size because you lack codebase context, say so in a note
on the story rather than guessing.
```

- [ ] **Step 4: Commit**

```bash
git add .claude/agents/clarifier.md .claude/agents/designer.md .claude/agents/backlog-writer.md
git commit -m "feat: add drift mitigation rubrics to all agents"
```

---

## Execution order and dependencies

```
Task 1 (iteration.py --max) ─────────────────────────────┐
Task 2 (guard scoping) ──────────────────────────────────┤
Task 3 (orchestrator guard) ─────────────────────────────┤── Task 6 (wire hooks)
Task 4 (warn-only hooks) ────────────────────────────────┤
Task 5 (review format validation) ───────────────────────┘
                                                          │
Task 6 (wire hooks into config) ──────────────────────────┤
                                                          │
Task 7 (designer dispositions) ──────────────────────────┤── Task 8 (reviewer reads dispositions)
                                                          │
Task 8 (reviewer reads dispositions) ────────────────────┤
Task 9 (contradiction + snapshot + step 9) ──────────────┤
                                                          │
Task 10 (reviewer rubric) ───── depends on Task 5 (hook validates the format)
Task 11 (all drift rubrics) ── independent
```

Tasks 1–5 are independent and can run in parallel.
Task 6 depends on all of 1–5.
Tasks 7–9 can run in parallel after Task 6.
Task 10 depends on Task 5 (the hook it relies on).
Task 11 is independent of everything.
