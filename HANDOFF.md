# Pipeline Hardening — Handoff for Cloud Session

## What this is

Hardening a four-agent design-cycle pipeline (clarifier → designer → reviewer → backlog-writer) against judgement drift, state loss, and prose-only enforcement. 11 tasks across 3 phases.

## Documents

- **Spec:** `docs/superpowers/specs/2026-08-08-pipeline-hardening-design.md`
- **Plan:** `docs/superpowers/plans/2026-08-08-pipeline-hardening.md`

## Progress

**All 11 tasks complete.** Full suite: `python3 -m pytest tests/ -q` -> 35 passed.

| Task | Status |
|------|--------|
| 1: Add --max flag to iteration.py | DONE |
| 2: Scope guard_output_path.py (multi-filename + iteration scoping) | DONE |
| 3: Orchestrator write restriction hook | DONE |
| 3b: SubagentStop output check hook (learning add-on) | DONE |
| 4: Warn-only hooks (paste + estimates) | DONE |
| 5: Review format validation hook | DONE |
| 6: Wire hooks into agent/skill config | DONE |
| 7: Designer writes dispositions.md | DONE |
| 8: Reviewer reads dispositions | DONE |
| 9: Contradiction handling + brief snapshot | DONE |
| 10: Reviewer rubric + structured scoring | DONE |
| 11: Clarifier rubric, designer deference, backlog granularity | DONE |

## Learning guide

`docs/GUIDE.md` explains every component and how the pieces fit together.

## Notes for whoever picks this up

- All six hook scripts are wired into config; nothing is left unreferenced.
- The reviewer's documented scoring table was verified to pass
  `validate_review_format.py`, so the prompt and its enforcing hook agree.
- The backlog sizing heuristic is deliberately spelled out ("one to three
  working days") rather than written with digits, so it cannot trip
  `warn_estimates_in_backlog.py`.
- Nothing has been run end-to-end against a real brief yet. The scripts are
  unit-tested; the pipeline itself has not been exercised live.

## Testing pattern

All tests use pytest. Script paths are absolute
(`Path(__file__).resolve().parent.parent / "scripts" / ...`), and tests
invoke `sys.executable` rather than a `python3` literal so they run on both
Windows and Linux. Use `cwd=str(tmp_path)` for scripts that read
`docs/.current_iteration`.
