# Pipeline Hardening — Handoff for Cloud Session

## What this is

Hardening a four-agent design-cycle pipeline (clarifier → designer → reviewer → backlog-writer) against judgement drift, state loss, and prose-only enforcement. 11 tasks across 3 phases.

## Documents

- **Spec:** `docs/superpowers/specs/2026-08-08-pipeline-hardening-design.md`
- **Plan:** `docs/superpowers/plans/2026-08-08-pipeline-hardening.md`

## Progress

| Task | Status | Commit |
|------|--------|--------|
| 1: Add --max flag to iteration.py | DONE | `8b10c5d` |
| 2: Scope guard_output_path.py (multi-filename + iteration scoping) | DONE | `953bb97` |
| 3: Orchestrator write restriction hook | IN PROGRESS — script written, test written, not yet run |
| 4: Warn-only hooks (paste + estimates) | Not started |
| 5: Review format validation hook | Not started |
| 6: Wire hooks into agent/skill config | Not started (depends on 1–5) |
| 7: Designer writes dispositions.md | Not started |
| 8: Reviewer reads dispositions | Not started (depends on 7) |
| 9: Contradiction handling + brief snapshot | Not started |
| 10: Reviewer rubric + structured scoring | Not started (depends on 5) |
| 11: Clarifier rubric, designer deference, backlog granularity | Not started |

## Task 3 state

The script and test file are already written on disk but uncommitted:
- `scripts/guard_orchestrator_write.py` — complete
- `tests/test_guard_orchestrator_write.py` — complete

Next step: run `python -m pytest tests/test_guard_orchestrator_write.py -v` and commit.

## How to continue

1. Read the plan at `docs/superpowers/plans/2026-08-08-pipeline-hardening.md` for full task details.
2. Resume at Task 3 (run tests, commit).
3. Tasks 4 and 5 are independent of each other — can be done in either order.
4. Task 6 wires all the Phase 1 hooks into agent configs — do it after 1–5 are committed.
5. Tasks 7–9 are Phase 2 (state loss). 7 and 9 are independent; 8 depends on 7.
6. Tasks 10–11 are Phase 3 (drift). 10 depends on 5 (the hook validates the format it introduces). 11 is independent.

## Testing pattern

All tests use pytest. The script path must be absolute (`Path(__file__).resolve().parent.parent / "scripts" / ...`). Use `sys.executable` instead of `python3`. Use `cwd=str(tmp_path)` for scripts that read `docs/.current_iteration`. The `python3` alias doesn't work on this Windows machine — always use `sys.executable`.

## Environment notes

- Windows 10, Python 3.10.8
- pytest installed to user site-packages (ignore the RequestsDependencyWarning in output — it's unrelated)
- Git repo initialized at `c:\Users\Benjamin\Documents\Learning\claude_learning`
- `.gitignore` excludes `.superpowers/`
