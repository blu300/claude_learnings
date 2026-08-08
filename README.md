# claude_learnings

A working example built to teach four Claude Code concepts: **subagents**,
**skills**, **hooks**, and **the state that passes between them**.

The example is a *design pipeline*. You give it a rough brief; four specialist
agents interrogate it, design it, review the design, and break the result into
a backlog. A coordinator routes between them and relays anything that needs a
human.

It is deliberately small — four agents, one skill, six hook scripts and a
folder-management script, none longer than about ninety lines — because the
point is to be readable, not impressive.

```
       you ──▶ /design-cycle brief.md
                      │
                      ▼
        ┌───────────────────────────────┐
        │  ORCHESTRATOR  (the skill)    │  talks to you, routes file paths,
        │  design-cycle/SKILL.md        │  never writes or reads the design
        └──┬────────┬────────┬───────┬──┘
           ▼        ▼        ▼       ▼
      clarifier  designer  reviewer  backlog-writer      (the subagents)
           │        │   ▲     │             │
           │        └───┴─────┘             │
           │        loop until APPROVED     │
           ▼        ▼                       ▼
     clarification.md  definition.md   backlog.md        (files on disk)
                       dispositions.md  review.md
```

---

# Part 1 — How you use it

## Starting a run

You invoke the skill and hand it a brief:

```
/design-cycle brief.md
```

The brief is a plain markdown file — a few sentences describing what you want.
It does not need to be good. Being vague is fine; questioning the vagueness is
the pipeline's first job.

`design-cycle` is a **skill**: a packaged procedure the coordinator follows. It
is marked so Claude can't invoke it on its own — you start it, deliberately, by
name.

## What happens, in order

**1. It asks you questions.** The `clarifier` reads your brief and writes a
list of assumptions and questions. The orchestrator reads them out to you,
blocking ones first.

Each question is marked **blocking** or **useful**:

- **blocking** — the designer would have to invent an answer, and inventing it
  wrong means rework. The pipeline waits.
- **useful** — worth knowing, safe to skip.

Skip anything you don't care about. Unanswered questions are recorded as
unanswered, so the designer knows which assumptions are still guesses rather
than quietly treating silence as agreement.

**2. It designs and reviews, on its own.** This is the long part and you are
not involved. The `designer` writes a design; a `reviewer` judges it and
returns one of three verdicts:

| Verdict | What happens |
|---|---|
| `APPROVED` | Move on to the backlog |
| `CHANGES REQUESTED` | New iteration, designer revises, review again |
| `QUESTIONS` | **Stops and asks you** — the criteria themselves are ambiguous |

The loop runs until approval or **four iterations**, whichever comes first. The
cap is a hard stop, not a guideline.

**3. It may come back to you.** Only on `QUESTIONS`. The reviewer can't reach
you directly — no subagent can — so it writes the question down and the
orchestrator relays it. Your answers are appended to the same clarification
file, which is the single record of everything you have said.

**4. It reports.** When the run ends you get: how many iterations it took, the
paths to the design and backlog, and any review findings the designer
*accepted rather than fixed*. That last one matters — it is where the design
knowingly left something on the table.

You then read the files yourself. The orchestrator won't summarise the design
back to you, on purpose: a summary is a lossy copy of a document you can just
open.

## Your three touchpoints

The whole interaction is:

```
   invoke  ──▶  answer the clarifier's questions  ──▶  [maybe answer the
                                                        reviewer's]  ──▶  read
```

Everything else is agents talking to each other through files.

## Where the output goes

One numbered folder per round:

```
docs/
  1/  brief-snapshot.md   frozen copy of your brief
      clarification.md    questions + your answers        <- your record
      definition.md       the design
      review.md           verdict + scoring table
  2/  definition.md       revised
      dispositions.md     what the designer did with each finding
      review.md
  3/  ...                 backlog.md appears in the approved round
```

A real run is committed under `docs/1` – `docs/4` if you want to read one. It
did **not** converge — it hit the cap with the review still asking for changes,
which is a normal outcome and worth seeing.

---

# Part 2 — How it works

Four mechanisms. Each solves a problem the previous one creates.

## Subagents — isolated workers

A **subagent** is a separate Claude instance with its own prompt, its own tool
list, and **its own context window**. It cannot see your conversation. It gets
a task, does it, and returns a short report.

Each lives in `.claude/agents/<name>.md` — a prompt with YAML frontmatter:

```yaml
---
name: reviewer
description: Reviews a design document against its criteria...
tools: Read, Write, Grep, Glob      # the ONLY tools it may use
---
You review a design document. You never edit the design...
```

Two fields do the real work:

- **`description`** decides *when* the agent gets used. Write it as "use this
  when…" — it is routing information, not a label.
- **`tools`** is a hard allowlist. The reviewer has no `Bash`, so it cannot run
  commands whatever its prompt says. **If an agent shouldn't be able to do
  something, don't give it the tool** — that beats asking it nicely.

**The isolation is the feature, and it is tuned per agent:**

| Agent | Spawned how | Why |
|---|---|---|
| `reviewer` | **Fresh every round** | No memory of arguing with the designer last time. It judges what is on the page, not what it remembers. |
| `designer` | **Resumed across rounds** | Keeps the reasoning behind its earlier choices, so round two is a revision rather than a rewrite. |

Same mechanism, opposite settings, opposite reasons.

**Subagents cannot talk to you.** Only the orchestrator can. That is why every
human question is written to a file and relayed — the relay pattern is a
consequence of isolation, not a design flourish.

## Skills — the packaged procedure

A **skill** is a procedure Claude follows, at
`.claude/skills/design-cycle/SKILL.md`. Here it *is* the orchestrator.

```yaml
---
name: design-cycle
argument-hint: [path-to-brief]
disable-model-invocation: true
allowed-tools: Bash(python3 scripts/iteration.py *) Bash(echo *) Read Edit
---
```

- **`disable-model-invocation: true`** — only a human starts it.
- **`$ARGUMENTS`** in the body receives your brief path.
- **`` !`command` ``** runs at load time and injects the output into the
  prompt, so the orchestrator knows which folders already exist before it acts.
- **`allowed-tools` is a permission *grant*, not a restriction.** It skips the
  approval prompt for those commands during the invoking turn, and clears on
  your next message. It does not sandbox anything — `disallowed-tools` is the
  field that removes tools. This one catches people out.

**The key design choice: the orchestrator is deliberately blinded.** It may
read `clarification.md`, `dispositions.md`, and the verdict line of a review.
It never reads the design.

Why? An orchestrator that reads the design becomes a second reviewer — with no
rubric, no discipline, and no accountability — and starts steering. Blinding it
keeps review authority in exactly one place.

That creates the next problem: **something that cannot read cannot verify.**
Which is what hooks are for.

## Hooks — rules as code instead of prose

Most rules started as prose in a prompt: *"never write definition.md"*, *"stop
after four iterations"*. Prose is a request. An agent that drifts breaks the
rule and nobody notices.

A **hook** is a shell command the harness runs around a tool call. It is code.
It cannot be talked out of its opinion.

```yaml
hooks:
  PreToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/guard_output_path.py" review.md'
```

The harness pipes the tool call to your script as **JSON on stdin**; the script
answers with an exit code, or with JSON on stdout.

**Three events, and the differences matter:**

| Event | Fires | Can it stop things? |
|---|---|---|
| `PreToolUse` | before the call | **Yes** — the call never happens |
| `PostToolUse` | after the call | **No** — the file is already written. It tells Claude to fix it |
| `SubagentStop` | when an agent finishes | Yes, but "block" prevents *stopping* — the agent keeps running |

**How a hook answers:**

| Goal | Mechanism |
|---|---|
| Block a call | exit `2`, or `{"decision": "block", "reason": ...}` |
| Warn the **user** | `{"systemMessage": "..."}` on stdout, exit 0 |
| Warn **Claude** | `hookSpecificOutput.additionalContext`, exit 0 |
| Allow silently | exit `0` |

⚠️ **Stderr on exit 0 goes to the debug log and nobody ever sees it.** Two
hooks in this repo were originally written that way and were completely inert —
unit-tested, documented, and doing nothing. Warnings must travel as JSON.

**The principle that keeps it usable:**

> Structural rules block. Heuristic rules warn and let the action through.

A *structural* rule is a fact — the path either is or isn't `docs/2/review.md`.
Safe to block. A *heuristic* is a guess — a long prompt is *probably* pasted
content. Blocking on a guess would halt an unattended pipeline for no reason.

**The scripts:**

| Script | Event | Does |
|---|---|---|
| `guard_output_path.py` | Pre | One guard, four agents. Allowed filenames as CLI args; also refuses writes to an *older* iteration |
| `guard_orchestrator_write.py` | Pre | Enforces the blinding rule — orchestrator may write three files, nothing else |
| `warn_paste_in_prompt.py` | Pre (`Agent`) | Warns when a delegation prompt looks like pasted file content |
| `warn_estimates_in_backlog.py` | Post | Warns on effort estimates. Must be Post — it reads content that doesn't exist until the write lands |
| `validate_review_format.py` | Post | Rejects a review whose verdict contradicts its own scoring table |
| `check_subagent_output.py` | SubagentStop | Catches an agent that finished without writing its file |
| `iteration.py` | *not a hook* | Creates numbered folders. `--max 4` is the cap |

⚠️ **Project hooks only run once you accept the workspace trust dialog.**
Decline it and every guard here silently does nothing.

## State — how information survives a hop

Subagents share no memory, so anything that must cross an agent boundary is
**a file**.

- **`brief-snapshot.md`** — your brief, frozen at the start. Every agent reads
  the snapshot, so editing the original mid-run can't change what they're
  working from.
- **`dispositions.md`** — the designer records each review finding as
  **Accepted**, **Rejected** or **Deferred**, with reasoning. The reviewer
  reads it before reviewing. Without it, a fresh reviewer re-raises settled
  points forever and the design converges on nothing.
- **Superseded answers** — when a later answer contradicts an earlier one, the
  old one is struck through and marked, never overwritten:
  `1. ~~On-demand only~~ **Superseded by #7**`. The designer needs to see the
  change of direction happened.
- **`.current_iteration`** — one line, one number. How a hook (a separate
  process, with no access to the conversation) learns which round is active.

## Drift — where code can't reach

No script can judge whether a design is *good*. So for judgement, the tactic
shifts from enforcement to **structure**: the reviewer scores five dimensions
PASS/FAIL and the verdict is derived mechanically — any FAIL means CHANGES
REQUESTED.

That doesn't remove inconsistency, it **relocates** it: the verdict stops being
a free-floating opinion and becomes a function of five smaller, named, checkable
judgements. And `validate_review_format.py` enforces the shape — **the prompt
asks for the structure, the hook makes it non-optional.** Neither is strong
alone.

---

## What this deliberately does not solve

- A model can score PASS on everything without really evaluating. The format
  makes a sloppy review *identifiable afterwards*, not impossible.
- The orchestrator relaying your answers is lossy. A reply with three
  conditions gets simplified.
- `memory: project` is declared by three agents but appeared inert in testing —
  treat that feature as unverified here.

Knowing what your guardrails miss matters as much as knowing what they catch.

---

## Try it

```bash
python3 -m pytest tests/ -q         # 38 passed — the scripts are correct
python3 scripts/verify_hooks.py     # 31 cases — watch each hook decide
```

The second one is the one to *read*. It prints the JSON going in, the exit code
coming out, and the message the agent would see, for every hook.

## Where to go next

| File | For |
|---|---|
| **`docs/GUIDE.md`** | The full explanation — every mechanism, why each choice was made, and the transferable lessons |
| **`docs/VERIFY.md`** | Reproducing every check yourself, including a live run, and what a manual run does *not* prove |
| `docs/1/` – `docs/4/` | A real run to read |
| `.claude/agents/*.md` | The four agent prompts — short, and worth reading directly |
| `.claude/skills/design-cycle/SKILL.md` | The orchestrator's procedure |
| `docs/superpowers/` | The original spec and implementation plan |

Behavioural claims here are checked against the
[Claude Code docs](https://code.claude.com/docs/en/hooks). If you observe
something different in a live session, believe the session.
