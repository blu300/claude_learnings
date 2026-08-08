# The Design-Cycle Pipeline — A Learning Guide

This is a guide to how this repository works, written to teach the mechanisms
rather than just document the code. It covers **subagents**, **skills**,
**hooks**, and **the state that passes between them**.

The system is deliberately small: four agents, one skill, six scripts. Nothing
here needs to be more complicated than it is.

---

## 1. The big picture

The pipeline takes a **brief** (a rough description of something to build) and
turns it into an **approved design** plus a **backlog**. It does that with four
specialists and a coordinator:

```
                    ┌──────────────────────────────────┐
                    │   ORCHESTRATOR (the skill)       │
                    │   design-cycle/SKILL.md          │
                    │   - talks to the human           │
                    │   - routes file paths            │
                    │   - never writes the documents   │
                    └────┬───────┬───────┬───────┬─────┘
                         │       │       │       │
              ┌──────────┘       │       │       └──────────┐
              ▼                  ▼       ▼                  ▼
        ┌───────────┐     ┌──────────┐ ┌──────────┐  ┌───────────────┐
        │ clarifier │ ──▶ │ designer │⇄│ reviewer │─▶│ backlog-writer│
        └───────────┘     └──────────┘ └──────────┘  └───────────────┘
              │                  │           │               │
        clarification.md   definition.md  review.md      backlog.md
                           dispositions.md
```

The loop in the middle is the important part: **designer → reviewer → designer
→ reviewer**, until the reviewer says APPROVED (or four iterations elapse).

Everything lives in numbered folders, one per iteration:

```
docs/
  .current_iteration      <- single line: "2"
  1/  brief-snapshot.md  clarification.md  definition.md  review.md
  2/  definition.md  dispositions.md  review.md
  3/  definition.md  dispositions.md  review.md  backlog.md
```

---

## 2. Subagents

### What they are

A **subagent** is a separate Claude instance with its own prompt, its own tool
list, and — critically — **its own context window**. It cannot see your
conversation, and you cannot see its reasoning. It receives a task, does it,
and returns a short report.

Each of the four lives in `.claude/agents/<name>.md`. The file is a prompt with
YAML frontmatter:

```yaml
---
name: reviewer
description: Reviews a design document against its criteria...
tools: Read, Write, Grep, Glob      # the ONLY tools it may use
model: inherit
memory: project
color: orange
hooks: ...                          # covered in section 4
---

You review a design document. You never edit the design...
```

**`description` is not decoration.** It is how the coordinating agent decides
which subagent to invoke. Write it as "use this when…" guidance.

**`tools` is a hard restriction.** The reviewer has `Read, Write, Grep, Glob`
and no `Bash` — so it cannot run commands, no matter what its prompt says. This
is the first and bluntest enforcement mechanism in the system: *if an agent
shouldn't be able to do something, don't give it the tool.*

### The four agents

| Agent | Job | Writes |
|---|---|---|
| **clarifier** | Interrogates the brief, produces questions before any design exists | `clarification.md` |
| **designer** | Turns criteria into a design; revises against reviews | `definition.md`, `dispositions.md` |
| **reviewer** | Judges the design against its criteria, returns a verdict | `review.md` |
| **backlog-writer** | Decomposes an approved design into epics/stories/tasks | `backlog.md` |

### Why isolation is the point

Two design decisions in this pipeline only make sense once you understand
context isolation:

- **The reviewer is always spawned fresh, never resumed.** It has no memory of
  previous rounds and no knowledge of how the design was produced. From
  `reviewer.md`: *"You have no knowledge of how the design was produced or what
  was said while it was written. That is the point — judge what is on the
  page."* A reviewer that remembered arguing with the designer last round would
  start defending its position instead of reading.

- **The designer IS resumed across iterations.** It keeps the reasoning behind
  its earlier choices, so revision two is a revision rather than a rewrite.

Same mechanism, opposite settings, for opposite reasons.

### The relay pattern

Subagents **cannot talk to the human**. Only the orchestrator can. So when the
clarifier has questions, it writes them to a file, and the orchestrator reads
them out and relays the answers back. Every human interaction is a relay.

This is also why the orchestrator is told to **pass file paths, never file
contents**. Pasting a design into a prompt would blow up context and duplicate
the source of truth. Files are the transport; the orchestrator is a router.

---

## 3. Skills

A **skill** is a packaged procedure — `.claude/skills/design-cycle/SKILL.md`
here. It's what the orchestrator *is*.

```yaml
---
name: design-cycle
description: Runs the clarify, design, review and backlog pipeline...
argument-hint: [path-to-brief]
disable-model-invocation: true
allowed-tools: Bash(python3 scripts/iteration.py *) Bash(echo *) Read Edit
hooks: ...
---
```

Things worth noticing:

- **`allowed-tools` is scoped to specific commands.** Not "Bash" but
  `Bash(python3 scripts/iteration.py *)`. The orchestrator can run the
  iteration script and `echo`, and nothing else. Again: restriction by
  capability, not by instruction.
- **`disable-model-invocation: true`** means it only runs when a human asks
  for it — it won't fire on its own.
- **`$ARGUMENTS`** in the body receives the brief path.
- **`` !`command` ``** executes at load time and injects the output into the
  prompt. Here `` !`python3 scripts/iteration.py list` `` tells the
  orchestrator which iteration folders already exist, before it does anything.

### The deliberately blinded coordinator

The single most interesting design choice in this repo: **the orchestrator is
forbidden from reading the design.**

```
- Keep your own reading to a minimum. You may read exactly these: the
  questions from clarification.md, dispositions.md, and the Verdict: line
  plus any Questions for human section from each review.md. You never read
  definition.md.
```

Why? Because an orchestrator that reads the design becomes a second reviewer —
one with no rubric, no discipline, and no accountability. It would start having
opinions and steering. Keeping it blind keeps the review authority in exactly
one place.

This has a direct consequence: **because it cannot read, it cannot verify.**
That's the entire reason hooks exist in this project.

---

## 4. Hooks — the heart of it

### The problem hooks solve

Most rules in the original pipeline were **prose in a prompt**: "never write
definition.md", "stop after 4 iterations", "don't paste file contents". Prose
is a request. An agent that drifts, misreads, or gets creative simply breaks
the rule and nobody notices. The spec calls this **silent degradation**.

A hook is a **shell command the harness runs around a tool call**. It is code,
not persuasion. It cannot be talked out of its opinion.

### The two events used here

| Event | Fires | Can it block? |
|---|---|---|
| **PreToolUse** | *before* a tool call executes | **Yes** — the call never happens |
| **PostToolUse** | *after* the tool call completed | The write already landed; it can reject the *result* and demand a fix |
| **SubagentStop** | when a delegated subagent finishes | Not tool-scoped at all — agent-scoped |

The Pre/Post distinction matters. To stop a file being written at all, you need
**PreToolUse**. To judge the *content* of a file, you need **PostToolUse** —
because the content doesn't exist until the write has happened.

### How a hook is declared

In the frontmatter of an agent or skill:

```yaml
hooks:
  PreToolUse:
    - matcher: "Write|Edit"                       # which tools trigger it
      hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/guard_output_path.py" review.md'
```

- `matcher` is a regex against the tool name.
- `${CLAUDE_PROJECT_DIR}` makes the path work regardless of working directory.
- Arguments after the script name are ordinary CLI args — that's how one
  generic guard serves four agents with different allowed filenames.

### How a hook communicates

The harness pipes the tool call to the script as **JSON on stdin**, and reads
the result back. Every script here follows the same shape:

```python
call = json.load(sys.stdin)              # the tool call
path = call["tool_input"]["file_path"]   # what it's trying to write
...
print("Blocked: ...", file=sys.stderr)   # message shown to the agent
return 2                                 # exit code = the decision
```

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | Allow. (stderr is still shown — this is how warn-only hooks work.) |
| `2` | **Block.** stderr is fed back to the agent so it can correct itself. |

**Or structured JSON on stdout** — a richer channel than an exit code:

```python
print(json.dumps({"decision": "block", "reason": "..."}))
```

`check_subagent_output.py` uses this form. Same outcome, but it passes a
message rather than just a status.

### The load-bearing distinction: hard-block vs warn-only

This is the design principle that keeps the system usable:

> **Structural rules hard-block (exit 2). Heuristic rules warn only (exit 0).**

A *structural* rule is a fact: the path either is or isn't
`docs/2/review.md`. No judgement, no false positives — safe to block.

A *heuristic* rule is a guess: a 2000-character prompt is *probably* pasted
content, but might legitimately be long. The word "effort" is *probably* an
estimate, but might be prose.

Why the split? Because **there is often no human present to unblock a false
positive.** A heuristic that hard-blocked would halt an unattended pipeline
over a guess. The rejected alternative — "hard-block everything, with a
`--force` escape hatch" — was dismissed in one line: *the model would force
everything, defeating the purpose.*

---

## 5. The six scripts

All are stdlib-only Python, all under ~90 lines.

### `iteration.py` — folder management *(not a hook)*

Prints/creates numbered iteration folders. The hardening added `--max`:

```bash
python3 scripts/iteration.py next --max 4   # exits 1 if docs/4 already exists
```

This converts the prose rule *"stop after 4 design iterations"* into a gate
the orchestrator **cannot override**, because it isn't the one deciding — the
script exits non-zero and there's no fifth folder to write into.

### `guard_output_path.py` — PreToolUse, hard-block

Used by all four agents. Takes the allowed filename(s) as arguments:

```yaml
command: '... guard_output_path.py definition.md dispositions.md'
```

Blocks any write that isn't `docs/<n>/<one-of-those-names>`. It also scopes by
iteration: it reads `docs/.current_iteration` and refuses writes into an
*older* folder, so iteration 3's designer cannot overwrite iteration 2's work.

**Why a file and not an environment variable?** From the spec: *"This avoids
depending on per-delegation env vars which the agent framework may not
support."* A file on disk is a boring, reliable channel that every process can
read.

### `guard_orchestrator_write.py` — PreToolUse, hard-block

Enforces the blinding rule from the write side. The orchestrator may write
exactly three things — `clarification.md`, `docs/1/brief-snapshot.md`, and
`docs/.current_iteration` — and nothing else.

Note its failure mode: if it can't parse the tool call, it **blocks**. For a
structural guard, fail-closed is correct.

### `warn_paste_in_prompt.py` — PreToolUse on `Agent`, warn-only

Watches delegation prompts for signs of pasted file content: over 2000
characters, three or more markdown headers, or a fenced code block. Prints to
stderr, always exits 0.

Note the matcher is `"Agent"`, not `"Write"` — this hook fires on
**delegation** rather than on file writes.

### `warn_estimates_in_backlog.py` — PostToolUse, warn-only

Reads the backlog after it's written and flags time/effort estimates
(`3 days`, `5 points`, "estimate", "sizing"). PostToolUse is *required* here —
you cannot inspect a file's content before it exists.

### `validate_review_format.py` — PostToolUse, **hard-block**

The one PostToolUse hook that blocks, because review structure is structural,
not heuristic. It rejects a `review.md` that:

- doesn't start with a valid `Verdict:` line,
- is missing any of the five scored dimensions,
- **contradicts itself** — APPROVED with a FAIL in the table, or CHANGES
  REQUESTED with everything PASS.

That last check is the interesting one: it enforces *internal consistency*
between two parts of a document. The agent can't quietly approve a design it
just scored as failing.

### `check_subagent_output.py` — SubagentStop, JSON output

Mechanises *"if an agent fails to write its file, report the failure and
stop."* When any subagent finishes, it checks the current iteration folder
contains at least one `.md` file.

**It is deliberately coarse, and that's a lesson in itself.** SubagentStop
receives no `file_path` — it isn't tied to a tool call — so it *cannot* know
which file was expected. It can only ask "did anything get written?" Rather
than parsing transcripts to fake precision, it does the coarse check honestly
and documents the limit. It also stays silent when it can't tell which folder
is active (no marker file → exit 0), because a guard that fires outside its
intended context is worse than no guard.

---

## 6. State: how information survives between agents

Subagents share no memory. Everything that must survive a hop is **a file**.
Three of the hardening tasks exist purely to stop information vanishing.

### `dispositions.md` — the litigation log

**The problem:** the reviewer is spawned fresh every round, so it doesn't know
it already raised a finding and got a good answer. It raises it again. The
designer either re-argues or capitulates. Nothing converges.

**The fix:** the designer writes a log of every review finding as **Accepted**,
**Rejected**, or **Deferred**, with reasoning. The reviewer reads it before
reviewing, and is instructed not to re-raise a rejected finding unless it can
specifically refute the reasoning.

Note who writes it: the **designer**, not the orchestrator. The alternative —
having the orchestrator parse the design — was rejected because the designer
already has the context and parsing is fragile. The known trade-off is
accepted openly: the designer frames its own rejections, and the reviewer is
allowed to disagree with that framing.

### `brief-snapshot.md` — freezing the input

The brief is copied to `docs/1/brief-snapshot.md` at the start, and every agent
reads the *snapshot*, never the original. If someone edits the brief while the
pipeline is running, the agents don't silently start working from different
inputs mid-run.

### Contradiction marking — superseding, not overwriting

When a human's later answer contradicts an earlier one, the orchestrator does
**not** overwrite it:

```markdown
1. ~~On-demand only~~ **Superseded by #7**
7. [blocking] Batch processing is required for enterprise accounts.
```

The designer sees the original assumption, the correction, and the link
between them. An overwrite would have destroyed the fact that a change of
direction ever happened.

### `.current_iteration` — the shared cursor

One line, one number. It's how a hook (a separate process, with no access to
the conversation) learns which iteration is active. The orchestrator updates it
before each delegation.

The spec is honest that this is imperfect: two pipelines running in the same
directory would race on this file. Accepted for v1, documented as an open
question.

---

## 7. Drift: making judgement observable

Phase 3 addresses a different failure: agents making *inconsistent judgements*
run to run. You can't hook your way out of this — no script can tell whether a
design is good — so the tactic changes from **enforcement** to **structure**.

### Mechanical verdict derivation

Instead of "decide APPROVED or CHANGES REQUESTED", the reviewer now scores five
dimensions and the verdict *falls out of the table*:

| Dimension | Verdict |
|---|---|
| Coverage | PASS/FAIL |
| Soundness | PASS/FAIL |
| Decisions | PASS/FAIL |
| Gaps | PASS/FAIL |
| Over-reach | PASS/FAIL |

- Any FAIL → CHANGES REQUESTED
- All PASS → APPROVED

This doesn't eliminate drift — it **relocates** it. The verdict stops being a
free-floating vibe and becomes a function of five smaller judgements, each
attached to a named dimension and a specific finding. Smaller judgements are
more observable, and the scoring table is grep-able after the fact.

And it's the one drift mitigation with real teeth, because
`validate_review_format.py` enforces the format and catches contradictions.
**The prompt and the hook are a pair** — the prompt asks for the structure, the
hook makes it non-optional.

### Default-to-safe tiebreaks

The clarifier's rubric:

> A useful question the human skips costs nothing; a blocking question the
> human ignores stops the pipeline. **When in doubt, mark it useful.**

The tiebreak points away from the expensive failure. Good rubrics don't just
define terms — they say what to do when you can't tell.

### Making capitulation expensive

The designer's deference self-check: if you accepted *every* finding, you must
write a paragraph titled "Why full acceptance was appropriate."

It doesn't forbid full acceptance — sometimes the reviewer is right about
everything. It makes total deference something you justify **out loud, in a
file others read**. Social friction where mechanical enforcement is impossible.

---

## 8. Putting it together: one full run

1. Human runs the skill with a brief path.
2. Orchestrator creates `docs/1` (`--max 4` gate), copies the brief to
   `brief-snapshot.md`, writes `1` to `.current_iteration`.
   *Guard allows all three — they're on its allow-list.*
3. Delegates to **clarifier** → writes `docs/1/clarification.md`.
   *PreToolUse guard checks the filename. SubagentStop checks it wrote
   something.*
4. Orchestrator reads the questions, relays them to the human, writes the
   answers back (striking through anything superseded).
5. Delegates to **designer** → `docs/1/definition.md`.
   *Paste-warn hook checks the delegation prompt.*
6. Delegates to **reviewer** (fresh) → `docs/1/review.md`.
   *PostToolUse validator rejects a malformed or self-contradicting review.*
7. Orchestrator reads **only the `Verdict:` line**.
   - CHANGES REQUESTED → new folder, update `.current_iteration`, back to 5.
     The designer is *resumed* and also writes `dispositions.md`; the reviewer
     is *fresh* and reads that log.
   - QUESTIONS → relay to the human.
   - APPROVED → continue.
8. Delegates to **backlog-writer** → `backlog.md`.
   *Estimate-warn hook flags any effort estimates.*
9. Orchestrator reads the final `dispositions.md` and reports what was
   accepted rather than fixed — **without ever having read the design.**

---

## 9. What this deliberately does not fix

Stated plainly in the spec, and worth keeping in view:

- **A model can game the scoring.** Nothing stops a reviewer scoring PASS on
  everything without genuine evaluation. The structured format doesn't prevent
  a sloppy review — it makes one *identifiable afterwards*.
- **Clarifier question quality.** The rubric calibrates blocking vs useful; it
  doesn't stop useless questions being asked.
- **Lossy transcription.** A human answer with three conditions will still get
  simplified by the orchestrator relaying it. The real fix — the human writing
  directly into the file — is outside the pipeline's scope.

Knowing what your guardrails *don't* catch is as important as knowing what they
do.

---

## 10. The transferable lessons

1. **Restrict by capability, not instruction.** `tools:` and `allowed-tools:`
   stop things prompts only discourage.
2. **PreToolUse blocks; PostToolUse judges results.** Pick by whether you need
   to prevent the action or inspect its output.
3. **Hard-block facts, warn on guesses.** A heuristic that blocks will
   eventually halt something important for no reason.
4. **Exit 2 to block, exit 0 to allow; stderr talks to the agent.** Or emit
   JSON for a richer reply.
5. **Files are how state survives an agent boundary.** No shared memory.
6. **Isolation is a setting, not a constraint** — resume the designer for
   continuity, spawn the reviewer fresh for independence.
7. **If the coordinator can't read it, it can't verify it** — which is exactly
   when you need a hook.
8. **Pair prompts with enforcement.** A format instruction plus a hook that
   validates it is far stronger than either alone.
9. **Prefer honest coarseness to fake precision.** The SubagentStop hook checks
   what it actually can, and documents what it can't.
10. **Write down what you didn't fix.** Undocumented gaps get mistaken for
    guarantees.
