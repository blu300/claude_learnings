# Project memory

This file is loaded into every Claude Code session in this repo,
automatically, before the conversation starts. That is the whole feature:
skills load when *invoked*, agents load when *delegated to* — CLAUDE.md is
simply always there. Use it for the standing rules a session needs before
it does anything. (This file is itself one of the teaching exhibits — see
"CLAUDE.md — the always-on layer" in docs/learning/GUIDE.md.)

## What this repo is

A small teaching example: a four-agent design pipeline (clarify → design →
review → backlog) run by the `/design-cycle` skill, enforced by Python hook
scripts, with every hook decision logged to `docs/hook-audit.log`. Start
with README.md's learning path if you are new here.

## Rules for working in this repo

- Design and planning work in this repo goes through the pipeline: the
  human types `/design-cycle <brief>`. Never use outside planning or spec
  skills here (superpowers' writing-plans, brainstorming, and similar) —
  this repo IS the demonstration of its own skills and agents, and
  routing its design work through a different stack defeats the entire
  point. Note the pipeline will never start itself: its skill sets
  `disable-model-invocation: true`, so if nobody has typed
  `/design-cycle`, say so instead of substituting another workflow.

- `docs/example-run/` is a committed specimen of a real pipeline run — do
  not hand-edit it. Live runs write to `docs/1/`, `docs/2/`, … which are
  transient and never committed.
- Never write `docs/.current_iteration` or `docs/hook-audit.log` yourself
  — they belong to `scripts/iteration.py` and `scripts/hook_audit.py`, and
  a settings-level guard will refuse the Write anyway. A leftover
  `.current_iteration` from an aborted run may be *deleted*.
- Run the tests with `python3 -m pytest tests/ -q` and the demonstration
  harness with `python3 scripts/verify_hooks.py`. Both must stay green;
  CI runs exactly these two commands.
- Hook scripts live in `scripts/`, one file per rule, none longer than
  about 150 lines. If you add one: write its unit tests, add a
  `verify_hooks.py` section, and make it log its decisions via
  `hook_audit.record` — including the boring "nothing to do" ones. The
  case study (docs/learning/CASE-STUDY.md) is the story of why.
- Documentation states counts (tests, harness cases, scripts). If you
  change the numbers, update README.md and docs/learning/VERIFY.md.
