# The audit log — how the record actually gets written

Every guard decision, every warning, every session event in this repo ends
up as one line in `docs/hook-audit.log`. This document answers "how are we
actually running that logger?" — first the surprising shape of the answer,
then the theory, then every line of the code that does it.

The surprising shape first: **there is no logger.** No process is watching,
no service is running, nothing is subscribed to anything. There is a
49-line Python module, `scripts/hook_audit.py`, and every hook script
imports it and calls one function at the moment it decides something. For
the few milliseconds a hook process exists, *it* is the logger. When it
exits, nothing remains but the line it appended.

That is worth sitting with, because it answers the question people usually
mean: nothing needs starting, nothing can crash overnight, nothing needs
configuring. The record exists because twelve small scripts each agreed to
write one line before returning — and for no other reason.

---

## Part 1 — The theory: why a log, and why this shape

### Why it exists at all

A guard's block message is shown only to the agent that triggered it. So
after a run, the transcript cannot answer the one question that matters:
**"no blocks happened" and "no guards were ever loaded" look exactly the
same from the outside.** This repo learned that the expensive way — the
case study (CASE-STUDY.md) is the story of five protections silently not
loading, discovered only because the log that *should* have had routine
lines had none.

The audit log is the answer: a mechanical record written by the scripts
themselves — not by the session under test, which is what makes it
evidence. The live-fire judge (`LLM as judge.md`) cross-checks every
quoted guard message against it; a quoted block with no matching line is
treated as fabricated.

### The four rules of the record

1. **Allows are logged, not just blocks.** The boring `allow` lines are
   the proof of life: four agents writing four legitimate files should
   produce four `allow` lines, and their absence means the guards never
   ran. A log that only recorded drama couldn't tell silence from death.
2. **Warn hooks log only when they warn.** Their silence proves nothing —
   by design. (This asymmetry matters when reading: no
   `warn_paste_in_prompt` lines might mean clean prompts *or* a dead
   hook; no `guard_output_path` lines during agent writes means dead
   guard, full stop.)
3. **Fail-opens are logged too.** When the stop-check has nothing to
   check (no cursor file), it says so in the log rather than exiting
   silently — because a silent "nothing to do" is indistinguishable from
   "never ran", which is rule 1's problem all over again.
4. **Logging must never break a guard.** If the line can't be written,
   the guard still returns its decision. The record serves the guards,
   never the reverse.

### One event, several lines — and that's correct

Rules run in layers here (agent-level and project-level), so a single
write can legitimately produce two lines with the same timestamp:

```
09:16:08 guard_orchestrator_write allow C:\...\docs\1\clarification.md
09:16:08 guard_docs_writes        allow C:\...\docs\1\clarification.md
```

Two separate hook processes, spawned for the same event, each appending
its own line. Duplicates are not a bug — and where the evidence shows
both layers loaded, a *single* line where two are expected is itself a
finding (one layer died).

---

## Part 2 — The code: all of it

`scripts/hook_audit.py` has one constant and one function. Line numbers
as of this writing.

**Line 29 — the name:**

```python
LOG_NAME = "hook-audit.log"
```

**Lines 32–48 — the entire mechanism:**

```python
def record(script: str, decision: str, detail: str) -> None:      # 32
    try:                                                          # 38
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR")
                    or Path.cwd())                                # 39
        log = root / "docs" / LOG_NAME                            # 40
        log.parent.mkdir(exist_ok=True)                           # 41
        stamp = datetime.datetime.now(datetime.timezone.utc)      # 42
                    .isoformat(timespec="seconds")
        with log.open("a", encoding="utf-8") as handle:           # 45
            handle.write(f"{stamp} {script} {decision} {detail}\n")  # 46
    except OSError:                                               # 47
        pass                                                      # 48
```

Line by line, because each one carries a decision:

- **Line 32 — the three-part signature** is the line format: *who*
  (`script` — the guard's own name, which is how you can grep one guard's
  history), *what* (`decision` — `allow`, `block`, `warn`, or for the
  flight recorder the event name), *about what* (`detail` — a path, a
  command, a reason). Format is contract: the preflight greps these
  columns, and the judge parses them.
- **Line 38 — everything is inside a `try`.** That's rule 4 as code: the
  whole body, including path construction, is allowed to fail.
- **Line 39 — the anchor, and a scar.** The project root comes from
  `CLAUDE_PROJECT_DIR`, which the harness exports to every hook. The
  `or Path.cwd()` fallback is for running scripts by hand — and it once
  bit hard: the unit tests ran hook scripts without pinning that
  variable, so a plain `pytest` run appended junk lines *to the real
  log* via the fallback. The tests now pin it; the fallback stays,
  documented, for humans at a terminal.
- **Line 41 — `mkdir(exist_ok=True)`** creates `docs/` if missing. A
  detail that once carried a whole diagnosis: because the log's parent is
  always created, "no log file was created at all" can never mean "the
  folder was missing" — it can only mean the hook process never executed.
  That inference stopped a doomed test run thirty seconds in.
- **Lines 42–44 — timestamps are UTC**, second precision, ISO format.
  One timezone forever, because the judge compares times across sessions
  and machines.
- **Lines 45–46 — append mode, one `write()`, one line.** The file is
  opened for append and given a single short line ending in `\n`. This is
  why concurrent hooks (the two-layer pairs above) interleave cleanly in
  practice: each process makes one small append and closes. Honest
  footnote: this is "reliable for short appends", not a transactional
  guarantee — good enough for evidence, not a database.
- **Lines 47–48 — `except OSError: pass`.** Disk full, permissions,
  locked file: the guard's verdict still stands. The one deliberate
  silent failure in the repo, and the docstring says why: "Logging must
  never break a guard."

### How the module reaches the hooks

Every hook does `import hook_audit` — a bare import that works no matter
what directory the hook is spawned from, because Python always puts *the
script's own directory* on the module search path, and every hook lives
in `scripts/` next to `hook_audit.py`. No installation, no packaging: the
sibling file is the dependency.

And the call sites show the rules from Part 1 as code:

- `guard_output_path.py` lines 118 and 121 — `allow` and `block` both
  recorded, one line before returning either verdict (rule 1).
- `warn_paste_in_prompt.py` line 69 — the *only* `record` call in the
  file sits inside the warning branch (rule 2).
- `check_subagent_output.py` lines 121–130 — three different `allow`
  records for three different "nothing to check" reasons, each naming
  which (rule 3): no cursor, folder missing, already-nudged.

Note the ordering convention at every guard: **the audit line is written
before the block message is printed** — if anything goes wrong mid-block,
the record already exists.

---

## Part 3 — The file's life, and what protects it

- **Born** on the first decision of a session (line 41 plus first append).
- **Read** three ways: by you (`Get-Content docs\hook-audit.log -Wait` is
  the live ticker — see run-guide.md §4 for the reading rules), by the
  preflight (which greps for one line per hook class before spending
  money on a live-fire run), and by the judge (cross-checking quoted
  evidence).
- **Rotated** by the preflight (`hook-audit.pre-test.log`) rather than
  deleted, because a preflight's log is itself evidence.
- **Never committed** — it's in `.gitignore`. Runtime evidence, not an
  artifact; deleting it is always safe.
- **Protected from the agents it records.** `guard_docs_writes.py`
  refuses any Write or Edit of the log (and its rotation, and the
  cursor), matching names case-insensitively because the production
  filesystem would happily treat `Hook-Audit.log` as the same file. A
  session under test that could rewrite its own record would defeat the
  judge's entire method.
- **The honest gap:** a Bash redirect (`echo garbage >>
  docs/hook-audit.log`) walks past Write/Edit guards — the same
  documented B3b route as everywhere else. The main session has a shell;
  the four agents don't (only the clarifier, leashed to one command). So
  tampering is possible from exactly one place, and it is the place the
  human is watching.
- **Why the recorder doesn't watch the log itself:** the flight
  recorder's `FileChanged` hook watches the *cursor file*, deliberately
  not the audit log — a watcher that appends a line every time the file
  it watches grows a line would be a feedback loop. Recording the
  recorder is where this design correctly stops.

---

## The one-sentence version

Twelve scripts, one shared function, one append each, everything inside a
`try`: the audit log is not a system — it is a habit, enforced by code
review and the rule in CLAUDE.md that no hook ships without its
`record()` calls. The whole apparatus is the discipline of writing one
honest line before returning.
