# The Hardening Pass

A full review of this repository was run on 2026-08-08, and this branch is
what came out of it. This document is the record: what was found, what was
changed, and — most importantly — what was deliberately **not** changed and
why. It is written for whoever reviews or extends this repo next, human or
agent, so that every choice here reads as a decision rather than an
oversight.

Read it after `docs/GUIDE.md` and `coordinator guards.md` — it assumes both.

---

## 1. Bugs found and fixed

Three real defects survived two prior review rounds. All three are the same
species of failure the guide's lesson 13 warns about: the unit tests were
green because they tested what the scripts did, not what the rules claimed.

### The guards trusted the front of the path

`guard_output_path.py` and `guard_orchestrator_write.py` checked only the
last three components of a path. This passed, on every branch before this
one:

```
{"tool_input": {"file_path": "/tmp/evil/docs/2/review.md"}}   ->  exit 0
```

Any agent could write anywhere on disk, as long as the path *ended* in
`docs/<n>/<its-filename>` — a lookalike tree, or a `../` escape. Notably,
`coordinator guards.md` had just finished arguing "the agents are fine
because they have no second tool" while the guard on their only tool had
this hole. (That document now carries a correction.)

**Fix:** paths resolve against the project root (`CLAUDE_PROJECT_DIR`, which
the hook harness exports; the working directory otherwise) and must land
inside it.

### A dropped flag corrupted the allowlist

`guard_output_path.py` silently discarded any argument starting with `-`.
Invoke it as `guard_output_path.py --iteration 3 review.md` — the interface
the original implementation plan documented — and `--iteration` vanished
while `3` became an *allowed filename*: `docs/2/3` was writable.

**Fix:** unknown options are refused outright (exit 2). A guard that guesses
what you meant is a guard with two behaviours.

### The "hard cap" was opt-in

The iteration cap was armed only when the orchestrator passed `--max 4`, and
`--max abc` (or `--max 0`) silently disarmed it. Every document called this
"a gate the orchestrator cannot override"; in fact the orchestrator armed the
gate itself, by prose instruction — exactly the enforcement style this repo
exists to replace.

**Fix:** the cap is now a constant in `iteration.py` (`DEFAULT_MAX = 4`).
`--max` can lower it for one call and can never raise it; an invalid value is
a loud error. To change the real cap, a human edits the script. The claim in
the docs is now true rather than aspirational.

---

## 2. Behaviour changes

- **`iteration.py next` writes `docs/.current_iteration` itself**, atomically
  with creating the folder. Previously the orchestrator ran
  `echo <n> > docs/.current_iteration` by hand — a step it could forget, and
  the sole reason the skill pre-approved `Bash(echo *)`, the widest grant in
  its list. Both the step and the grant are gone. The orchestrator's
  writable-file list shrank from three to two, and its guard now refuses the
  cursor file along with everything else.

- **The orchestrator guard matches the rule exactly.** `clarification.md`
  was allowed in any `docs/<n>/`; the rule says it lives in `docs/1` only.
  The guard now agrees with the rule.

- **A `QUESTIONS` verdict no longer spends an iteration.** It used to create
  a new folder, so a run that hit questions twice burned half its budget
  without the reviewer ever seeing a revised design. Now the round is redone
  in the same folder once the human answers: the design was not judged
  wrong, it could not be judged at all. The overwritten `QUESTIONS` review
  is not lost in substance — its questions and their answers live on in
  `clarification.md`.

- **Every hook decision is logged.** `scripts/hook_audit.py` appends one
  line per decision — timestamp, script, allow/block/warn, detail — to
  `docs/hook-audit.log` (gitignored). This exists because a block message
  reaches only the agent that triggered it: after a run, "nothing fired" and
  "nothing was loaded" are indistinguishable from the transcript. The
  live-fire test (`LLM as judge.md`) now cross-checks its evidence against
  this log, which the session under test does not author.

---

## 3. Documentation corrections

- **"Subagents cannot talk to the human" was out of date.** Current Claude
  Code lets a subagent use `AskUserQuestion`
  ([tools reference](https://code.claude.com/docs/en/tools-reference)). The
  README, guide and `coordinator guards.md` said the platform forbade it —
  and, tellingly, it was the one load-bearing claim none of them cited. The
  corrected framing is better teaching anyway: this pipeline's agents cannot
  ask *because the tool is withheld from them*, the same
  restrict-by-capability move as withholding `Bash`. The relay pattern stays,
  now as a choice (one durable record of answers) rather than a workaround.

- **`memory: project` is conditional, not broken.** The field only takes
  effect when Claude Code's auto memory is enabled
  ([sub-agents reference](https://code.claude.com/docs/en/sub-agents));
  with it off, the agent launches without memory tools — which is exactly
  what the recorded run observed. The docs now say when it works instead of
  calling it unverified.

- **The live-fire test tightened.** Its cap test was removed (script
  behaviour, already proven two cheaper ways — lesson 13 again); the runner
  must record *how* each violation was attempted, because the coordinator's
  hooks only apply while the skill is orchestrating and silence outside that
  scope is not a broken guard; and both prompts now use the audit log — the
  runner appends it verbatim, the judge treats any quoted guard message
  without a matching log line as fabricated.

---

## 4. The redesign deliberately not done

This is the decision this document mainly exists to record.

### The gap

The coordinator must not write the design. Its guard enforces that on the
Write and Edit tools — but the coordinator is a *skill* running in the main
session, and the main session has a shell. `echo "..." > docs/1/definition.md`
goes around the guard entirely. A skill's `allowed-tools` cannot close this:
it pre-approves tools, it never removes one. The four specialist agents do
not have this gap because agent `tools:` lists are hard restrictions and
theirs contain no shell. The full analysis is `coordinator guards.md`.

### The proper fix, and its price

Move the coordinator into `.claude/agents/coordinator.md` with
`tools: Read, Write, Grep, Glob, Agent`. No shell in the list means no second
route; the existing guard would then cover everything the coordinator can
do. The platform supports it: subagents can spawn subagents (three layers
below the main conversation by default — a default that has churned across
CLI versions, so check yours), can be resumed with context intact, and can
even be granted `AskUserQuestion` to talk to the human directly.

The price is the shape of the repo. A fifth agent, a rewritten skill reduced
to a relay stub (which itself still has the shell), a redrawn diagram, and a
guide whose clearest teaching contrast — *agent `tools:` restricts, skill
`allowed-tools` merely pre-approves, and here is what that difference costs*
— becomes a historical footnote instead of a live thing you can poke at.

### The decision

**Keep the coordinator a skill. Document the gap loudly.**

Three reasons, in order of weight:

1. **This is a learning repo.** The gap is the single best illustration in
   the codebase of a transferable lesson: a guard that watches routes is
   always one trick behind; take the capability away instead. Fixing it
   would remove the exhibit. Keeping it — analysed in one document, decided
   in another, stated plainly in the guard's own docstring — teaches more
   than the fix would.
2. **The guard covers the failure it exists for.** The threat model is
   *drift* — a coordinator that forgets the rule and reaches for the normal
   write tool gets blocked. Evading the guard requires a deliberately odd
   way of writing a file, which is not what drifting looks like. Unattended
   operation against an adversarial model is the case that needs option 4,
   and this repo is not that.
3. **The gap got smaller anyway.** Removing `Bash(echo *)` means an
   unexpected shell write once again hits the permission prompt when a human
   is present, and the audit log means a bypass that dodges the guard still
   cannot dodge the record being *absent* where the transcript claims a
   block happened.

If this repo's purpose ever changes — if the pipeline is to run unattended
and the blinding rule must be *true* rather than true-under-supervision — do
option 4 first, and re-read the "What it costs" section of
`coordinator guards.md`, which now carries the verified platform facts.

---

## 5. Also in this pass

- **CI.** One workflow (`.github/workflows/ci.yml`): `pytest -q` and
  `scripts/verify_hooks.py` on every push and pull request. The README's
  "49 passed / 38 cases" claims are now checked by a machine instead of
  asserted by a document.
- **A learning path in the README** — the reading order for the whole repo,
  ending with the live-fire test as an optional capstone.
- Tests pin `CLAUDE_PROJECT_DIR` per case, so guard results no longer depend
  on where the tests happen to run.

## 6. For the next reviewer

Things that will rot, and where they are load-bearing:

- **Version-dependent platform claims**: subagent nesting depth and
  `AskUserQuestion` availability (`coordinator guards.md`), auto-memory
  semantics (README, VERIFY). Each carries a citation; re-check against
  current docs before relying on them. The tiebreak order stands: live
  session beats docs, docs beat this repo.
- **The live-fire test has not been run since these changes.** Everything in
  sections 1–2 is proven at the script layer (49 tests, 38 harness cases);
  whether the harness fires these hooks in a real session is exactly the
  claim `LLM as judge.md` exists to test, and it needs a human present.
- **The `QUESTIONS` same-folder redo is untested in a live run** — the
  recorded run under `docs/1`–`docs/4` predates it and never hit a
  `QUESTIONS` verdict at all.
- The concurrent-pipeline race on `docs/.current_iteration` remains open and
  accepted, as the original spec recorded.
