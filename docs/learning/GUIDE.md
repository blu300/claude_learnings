# The Design-Cycle Pipeline — A Learning Guide

This is a guide to how this repository works, written to teach the mechanisms
rather than just document the code. It covers **subagents**, **skills**,
**hooks**, and **the state that passes between them**.

The system is deliberately small: four agents, one skill, nine hook scripts, a
shared audit-log module and one folder-management script. Nothing here needs
to be more complicated than it is.

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

The four specialists **cannot talk to the human** — but be precise about why,
because the first version of this guide got it wrong. It is not a platform
limit: current Claude Code lets a subagent use the `AskUserQuestion` tool,
with the prompt surfacing in the main session
([tools reference](https://code.claude.com/docs/en/tools-reference)). These
four cannot ask because that tool is not in their `tools:` list — the same
restrict-by-capability move as withholding `Bash`. So when the clarifier has
questions, it writes them to a file, and the orchestrator reads them out and
relays the answers back. Every human interaction is a relay, and every answer
lands in one durable file instead of a transcript.

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
allowed-tools: Bash(python3 scripts/iteration.py *) Read Edit
hooks: ...
---
```

Things worth noticing:

- **`allowed-tools` is a permission *grant*, not a restriction.** This one
  catches people out, including the first version of this guide. It lists
  tools Claude may use *without a permission prompt* during the turn that
  invoked the skill — it does not remove anything from the pool, and every
  other tool remains callable under your normal permission settings. Writing
  `Bash(python3 scripts/iteration.py *)` means "don't prompt me for that
  command", not "only that command is allowed".

  The field that actually restricts is **`disallowed-tools`**, which removes
  tools from the pool while the skill is active.

  > *"Tools Claude can use without asking permission during the turn that
  > invokes this skill. The grant clears when you send your next message."*
  > — [skills reference](https://code.claude.com/docs/en/skills)

  **And note that expiry**, because this pipeline runs headfirst into it. The
  grant clears on the user's next message, but the orchestrator is a
  multi-turn relay — it asks the human the clarifier's questions and waits.
  On the turn after the human answers, the grant is gone and
  `Bash(python3 scripts/iteration.py *)` prompts normally. Skill *content*
  persists for the session; skill *permissions* last one turn. Those are two
  different lifetimes and it is worth knowing which is which.
- **`disable-model-invocation: true`** means it only runs when a human asks
  for it — it won't fire on its own. Know the side effect before you reach
  for this flag: an invite-only skill is invisible to Claude's own skill
  selection, so a plain-words request ("plan this for me") gets answered by
  whatever *other* installed skills volunteer — on a machine with an
  always-on planning plugin, that plugin wins every time. This repo learned
  that live: a session cheerfully ran a third-party planning skill inside
  the repo built to demonstrate this pipeline. The counterweights are
  CLAUDE.md (an always-on rule saying design work goes through
  `/design-cycle`) and project settings disabling the competing plugin
  here (`enabledPlugins` in `.claude/settings.json`).
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

### CLAUDE.md — the always-on layer

Skills load when *invoked*. Agents load when *delegated to*. There is a third
layer that loads before either: **`CLAUDE.md`**, a plain markdown file at the
repo root that Claude Code reads into every session automatically, before the
conversation starts. No trigger, no command — if the file exists, its
contents are simply there.

| Layer | Loads | Best for |
|---|---|---|
| `CLAUDE.md` | every session, at start | standing rules a session needs *before it does anything* |
| a skill | when someone invokes it | a procedure with steps |
| an agent | when the orchestrator delegates | a role with its own context |

This repo ran for months without one, and the gap showed in a small way: a
fresh session opening this folder knew nothing about the pipeline until it
stumbled into it — nothing told it that `docs/example-run/` is a preserved
specimen rather than ordinary docs, or that the iteration cursor is not its
to write. Rules like that can't live in the skill, because sessions that
never invoke the skill still need them.

Look at what the repo's [`CLAUDE.md`](../../CLAUDE.md) does **not** contain,
because that's the design lesson: no pipeline procedure (that's the skill's
job), no role descriptions (the agents' job), no rule a hook already
enforces better — just the handful of things every session must know on
arrival, and where to read more. Always-on context is paid for on every
single prompt, so the always-on layer should be the *smallest* of the three.

(The flight recorder — next section — logs an `InstructionsLoaded` line
when the file loads, so you can see the moment it happens.)

---

## 4. Hooks — the heart of it

### The problem hooks solve

Most rules in the original pipeline were **prose in a prompt**: "never write
definition.md", "stop after 4 iterations", "don't paste file contents". Prose
is a request. An agent that drifts, misreads, or gets creative simply breaks
the rule and nobody notices. The spec calls this **silent degradation**.

A hook is a **shell command the harness runs around a tool call**. It is code,
not persuasion. It cannot be talked out of its opinion.

### The three enforcement events

| Event | Fires | Can it block? |
|---|---|---|
| **PreToolUse** | *before* a tool call executes | **Yes** — the call never happens |
| **PostToolUse** | *after* the tool call completed | **No** — the tool already ran. It shows stderr to Claude, which makes it fix the result |
| **SubagentStop** | when a delegated subagent finishes | **Yes** — but "block" here prevents the subagent *stopping*, i.e. it keeps running |

Three things follow, and each one bites:

**To prevent a write, you need PreToolUse.** Nothing later can un-write a file.

**To judge a file's *content*, you need PostToolUse** — the content doesn't
exist until the write has happened. But PostToolUse **cannot block**: the file
lands on disk and stays there. The best it can do is tell Claude to fix it on a
subsequent write, and anything reading the file in between sees the bad version.

**"Block" does not mean the same thing at every event.** At PreToolUse it stops
the call. At SubagentStop it does the reverse of what the word suggests — it
stops the agent from *finishing*, so the agent keeps going. Read the per-event
table in the [hooks reference](https://code.claude.com/docs/en/hooks) rather
than assuming exit 2 has one universal meaning.

`SubagentStop` is also the odd one out for matching: it isn't tool-scoped, but
it does support matchers — they filter on **agent type** (`general-purpose`,
`Explore`, or a custom agent's frontmatter `name`) rather than on tool name.

### The rest of the catalogue — and the flight recorder

The three events above are the *enforcement* events — the ones where a
script gets to say no. But the [hooks reference](https://code.claude.com/docs/en/hooks)
lists around thirty events in total. Most of the rest are not about
permission at all: they are moments in a session's life — it started, it
compacted its memory, a delegation began, a tool call failed, it ended.

This repo covers those with one deliberately boring script:
**`session_log.py`, the flight recorder.** Wired in `.claude/settings.json`
against fourteen events, it appends one line per event to the same
`docs/hook-audit.log` the guards write, and never blocks anything. The
motivation comes straight from the case study: after an unattended run, the
questions are always "did it compact?", "which agents ran, in what order?",
"why did it stall?" — and the transcript answers none of them mechanically.
The recorder does.

What each recorded event tells you:

| Event | The line answers |
|---|---|
| `SessionStart` / `SessionEnd` | when sessions began and ended, and why. SessionStart also *injects context*: if a pipeline run is mid-flight, the new session is told before it can trip over the state |
| `Stop` / `StopFailure` | each finished turn — and the turns that died to an API error, which otherwise vanish without a trace |
| `SubagentStart` / `SubagentStop` | every delegation, with the agent type. The live-fire judge can now verify "four agents, in the right order" from a record the session under test didn't write |
| `UserPromptExpansion` | the moment `/design-cycle` expanded — proof the skill was invoked as a command |
| `PostToolUseFailure` | tool calls that *failed* (PostToolUse only fires on success) |
| `Notification` | what Claude Code tried to tell someone — e.g. *why* an unattended run sat waiting |
| `PreCompact` / `PostCompact` | when a long run compressed its context. Evidence written *after* compaction relies on a summary, not verbatim memory — the judge deserves to know which is which |
| `InstructionsLoaded` | the moment CLAUDE.md entered the session |
| `ConfigChange` | settings changed mid-session — including a session under test editing away its own guards |
| `FileChanged` | a *watched file* changed on disk, whoever changed it. Wired here to `docs/.current_iteration`: the write guards can't see a Bash redirect rewrite the cursor (the B3b gap), but the file changing is visible regardless of which tool did it. Detection where prevention isn't available |

And one more warn hook lives at this layer: **`UserPromptSubmit`** fires on
the *human's* prompt, before Claude processes it. `warn_paste_in_user_prompt.py`
applies the paste heuristics there — the repo warned for months when the
orchestrator pasted content into a delegation while nobody applied the same
rule to the human at the top of the chain. (UserPromptSubmit *can* reject a
prompt outright; a heuristic never should, so it warns.)

**The events this repo deliberately does not cover**, because each needs
infrastructure the repo doesn't use — knowing *why* you skip something is
part of the lesson:

| Event(s) | Fires around | Why not here |
|---|---|---|
| `Setup` | `claude --init-only` / maintenance runs | nothing to install or migrate here |
| `PermissionRequest`, `PermissionDenied` | the permission prompt flow | a hook here can silently auto-approve tools — powerful, and exactly the kind of power a learning repo should not normalise |
| `PostToolBatch` | batches of parallel tool calls | the pipeline delegates one agent at a time on purpose |
| `MessageDisplay` | text as it is displayed | cosmetic rewriting; easy to misuse, nothing to teach here |
| `TaskCreated`, `TaskCompleted` | the task-list system | unused in this repo |
| `TeammateIdle` | agent teams | unused — the four agents are subagents, not a team |
| `CwdChanged`, `DirectoryAdded` | multi-folder sessions | this is a one-folder project |
| `WorktreeCreate`, `WorktreeRemove` | git worktrees | unused |
| `Elicitation`, `ElicitationResult` | MCP servers asking the user for input | no MCP servers here |

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

**One thing that will silently defeat all of this: workspace trust.** Hooks
declared in a *project's* agent or skill frontmatter only run once the
workspace trust dialog has been accepted for the folder that file came from.
Clone this repo, decline the dialog (or never see it), and every guard here
fails to fire with no error and no explanation — the pipeline just runs
unguarded. If you are testing hooks and nothing happens at all, check trust
before you debug the script.

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
| `0` | Allow. **stderr goes to the debug log only — nobody sees it.** |
| `2` | The blocking signal. What it blocks depends on the event (see above). stderr *is* fed back to the agent. |

That first row is the trap, and this guide fell into it. Printing a warning to
stderr and exiting 0 does nothing at all:

> *"Stderr from a hook that exits 0 goes to the debug log only, never the
> transcript, and Claude never sees it."*
> — [hooks reference](https://code.claude.com/docs/en/hooks)

Both warn-only hooks in this repo were originally written that way and were
therefore **completely inert**. They looked correct, they were unit-tested, and
they did nothing in a real session.

**To say something without blocking, use JSON on stdout.** Two fields, two
different audiences:

```python
print(json.dumps({
    "systemMessage": "Warning: ...",              # -> the USER sees this
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": "...",               # -> CLAUDE sees this
    },
}))
```

| You want to reach | Use |
|---|---|
| The **user** | `systemMessage`, exit 0 — action proceeds |
| **Claude**, non-blocking | `hookSpecificOutput.additionalContext`, exit 0 |
| **Claude**, from PostToolUse | exit 2 — the tool already ran, so this warns rather than blocks |
| Block a call outright | `decision: "block"` with a `reason`, or exit 2 at a blockable event |

Note the third row collapses the tidy "2 means block" story: at PostToolUse the
docs actively recommend exit 2 *as the way to warn*, because there is nothing
left to block. Exit 2's meaning is per-event, not universal.

### The load-bearing distinction: hard-block vs warn-only

This is the design principle that keeps the system usable:

> **Structural rules block. Heuristic rules warn and let the action through.**

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

## 5. The scripts

All are stdlib-only Python, all under ~150 lines: nine hook scripts, two
shared modules (`hook_audit.py`, `docs_scope.py`) and one folder manager.

### `iteration.py` — folder management *(not a hook)*

Prints/creates numbered iteration folders, and does two more things that used
to be the orchestrator's job:

- **The cap lives here, as a constant.** `DEFAULT_MAX = 4` in the script.
  An earlier version armed the cap only when the orchestrator passed
  `--max 4` — which made "a gate the orchestrator cannot override" untrue,
  since not passing the flag removed the gate. Now no flag is needed,
  `--max` can lower the cap but never raise it, and an invalid value is a
  loud error instead of a silent no-op. To change the real cap, a human
  edits the file.
- **Creating a folder writes `docs/.current_iteration`** in the same call.
  The guards' cursor is set atomically with the folder it points at, so it
  cannot be forgotten, and the orchestrator needs no shell access to
  maintain it.

```bash
python3 scripts/iteration.py next   # exits 1 if docs/4 already exists
```

### `guard_output_path.py` — PreToolUse, hard-block

Used by all four agents. Takes the allowed filename(s) as arguments:

```yaml
command: '... guard_output_path.py definition.md dispositions.md'
```

Blocks any write that isn't `docs/<n>/<one-of-those-names>` **inside the
project**. The anchoring matters: an earlier version checked only how the
path *ended*, so a lookalike tree anywhere on disk
(`/tmp/evil/docs/2/review.md`) sailed through. Paths now resolve against the
project root (`CLAUDE_PROJECT_DIR`) and must land inside it. It also scopes
by iteration: it reads `docs/.current_iteration` and refuses writes into an
*older* folder, so iteration 3's designer cannot overwrite iteration 2's work.

**Why a file and not an environment variable?** From the spec: *"This avoids
depending on per-delegation env vars which the agent framework may not
support."* A file on disk is a boring, reliable channel that every process can
read.

### `guard_orchestrator_write.py` — PreToolUse, hard-block

Enforces the blinding rule from the write side. The orchestrator may write
exactly two things — `docs/1/clarification.md` and `docs/1/brief-snapshot.md`
— and nothing else. Both live in `docs/1` only, and the guard is exactly as
tight as the rule.

Note its failure mode: if it can't parse the tool call, it **blocks**. For a
structural guard, fail-closed is correct.

Note also its **known limit**: it watches Write and Edit, and the
orchestrator — a skill in the main session — also has a shell the guard does
not see. That gap is deliberate and has its own section:
[The coordinator's shell](#the-coordinators-shell--a-gap-kept-on-purpose).

### `guard_docs_writes.py` — PreToolUse, hard-block, the settings floor

The one guard wired in `.claude/settings.json` instead of frontmatter, added
after the loading failure in the case study. Settings hooks run in *every*
session, however it was launched — so this layer holds even when the
frontmatter guards silently fail to load, which is precisely the scenario
that motivated it.

The price of living at this layer is identity: a settings hook cannot know
*which* agent is writing (that knowledge exists only in the per-agent
frontmatter wiring), so this guard enforces only the agent-independent
rules — right folder, right iteration, no stray files in `docs/<n>/`, and no
Write/Edit of the iteration cursor or the audit logs. Cross-writes between
agents remain the frontmatter guard's job. **Defense in depth means the
backup layer catches less, and writes down exactly what it misses.**

It also carries the repo's most Windows-shaped scar: its name checks are
case-insensitive and colon/stream path forms are refused, because NTFS
happily treats `docs/.Current_Iteration` as the real cursor — the review
that caught this found a working bypass in code written to stop bypasses.

### `warn_paste_in_prompt.py` — PreToolUse on `Agent`, warn-only

Watches delegation prompts for signs of pasted file content: over 2000
characters, three or more markdown headers, or a fenced code block. Warns
via JSON on stdout (`systemMessage` + `additionalContext`), always exits 0.

Note the matcher is `"Agent"`, not `"Write"` — this hook fires on
**delegation** rather than on file writes.

### `warn_paste_in_user_prompt.py` — UserPromptSubmit, warn-only

The same three heuristics (imported from `warn_paste_in_prompt.py` — one
place to tune them), pointed at the **human's** prompt instead of the
orchestrator's delegations. For months this repo policed pasting at every
hop except the first one. The pipeline wants a *path* to a brief, not the
brief inline: pasted content leaves no file for the agents to read and
nothing for `brief-snapshot.md` to freeze.

UserPromptSubmit is an event that *can* reject a prompt outright (exit 2).
This hook never does — same principle as every heuristic here: structural
rules block, guesses warn.

### `warn_estimates_in_backlog.py` — PostToolUse, warn-only

Reads the backlog after it's written and flags time/effort estimates
(`3 days`, `5 points`, "estimate", "sizing"). PostToolUse is *required* here —
you cannot inspect a file's content before it exists.

### `validate_review_format.py` — PostToolUse, rejects the result

Review structure is structural, not heuristic, so this one exits 2 rather than
warning. But note what that can and cannot do here: **PostToolUse cannot block**
— the malformed `review.md` is written to disk and stays there. Exit 2 shows the
error to the reviewer, which makes it rewrite the file. Anything reading
`review.md` between the two writes sees the bad version.

That is the strongest guarantee available at this event, and it is weaker than
the PreToolUse guards, which stop the write happening at all.

It rejects a `review.md` that:

- doesn't start with a valid `Verdict:` line,
- is missing any of the five scored dimensions,
- **contradicts itself** — APPROVED with a FAIL in the table, or CHANGES
  REQUESTED with everything PASS.

That last check is the interesting one: it enforces *internal consistency*
between two parts of a document. The agent can't quietly approve a design it
just scored as failing.

### `check_subagent_output.py` — SubagentStop, JSON output

When a subagent finishes, it checks that the agent's own output file exists in
the current iteration folder. Each agent's frontmatter declares a `Stop` hook
(converted to `SubagentStop` at runtime — the documented wiring for subagent
stop hooks) and passes the filename that agent owns, the same way
`guard_output_path.py` takes its allowlist. Run with no arguments it falls
back to the original coarse form: does the folder contain *any* `.md` file?

**It does not do what SKILL.md's prose rule says**, and the gap is instructive.
The rule is *"if an agent fails to write its file, report the failure and
stop."* What `{"decision": "block", "reason": ...}` actually does at
SubagentStop is:

> *"Returning `decision: "block"` … prevents the subagent from stopping"*
> — [hooks reference](https://code.claude.com/docs/en/hooks)

So it **keeps the agent running** and hands it the `reason` as its next
instruction — close to the opposite of "stop". And the `reason` goes to the
**subagent**, not to the orchestrator, so it must be phrased as an instruction
to the agent that just tried to finish ("write your output file now"), not as
a report to its parent. To inject context into the *parent* session after a
subagent returns, you would use a PostToolUse hook on the `Agent` tool instead
— a different channel entirely.

In practice keep-going-and-fix-it is the better behaviour here: the agent gets
a chance to write the file it forgot. But it is not what the prose says, and
writing the `reason` for the wrong reader is an easy mistake — this repo made
it first time round.

**Its knowledge comes from the wiring, not the event — a lesson in itself.**
SubagentStop receives no `file_path`: it isn't tied to a tool call, so the
event *cannot* say which file was expected. The first version therefore only
asked "did anything get written?" — honest, but it could catch only the first
writer into a fresh folder; once any agent had written any `.md`, every later
agent that wrote nothing passed. The fix is the same trick the write guard
uses: the expected filename rides in each agent's frontmatter command line.
The event still knows nothing; the *declaration* does. It still stays out of
the way when it can't tell which folder is active (no marker file → exit 0,
with an audit line saying so — an earlier version was silent here, which made
"hook never ran" and "nothing to check" indistinguishable in the log, exactly
the ambiguity `hook_error.md` is about).

### `session_log.py` — the flight recorder, fourteen events, warn-nothing

Covered in depth in ["The rest of the catalogue"](#the-rest-of-the-catalogue--and-the-flight-recorder)
above. As a *script* it is worth reading for one design habit: the event
name arrives as a command-line argument, so the `settings.json` wiring reads
like a table of what gets recorded, and an event it doesn't recognise still
gets a line — a recorder that drops the unfamiliar is quieter than it
should be. It never blocks: a flight recorder that could ground the plane
would be a very different instrument.

### `docs_scope.py` — shared path scoping *(not a hook)*

Three functions used by the settings-layer hooks: where is the project
root, which iteration is current, and is this path a pipeline file
(`<root>/docs/<n>/<name>`)? It exists because three scripts needed the same
answer and path-anchoring bugs are exactly the kind that only bite one
platform — one implementation, one set of tests, one place to fix the next
Windows surprise.

### `hook_audit.py` — the mechanical record *(not a hook)*

One shared function, used by every hook above: each decision appends a line —
timestamp, script, allow/block/warn, detail — to `docs/hook-audit.log`
(gitignored).

It exists because a guard's block message is seen only by the agent that
triggered it. After a live run, "no blocks happened" and "no hooks ever
loaded" look identical from the transcript — the log is the only thing that
can tell them apart, and it is written by the scripts themselves, not by the
session being tested. The live-fire test (`LLM as judge.md`) cross-checks its
evidence against this file. Logging failures are swallowed: the record must
never be the thing that breaks a guard.

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
the conversation) learns which iteration is active. `iteration.py` writes it
whenever it creates a folder — the orchestrator used to update it by hand
with `echo`, which meant a forgettable step and a shell grant; moving it into
the script removed both.

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
2. Orchestrator creates `docs/1` with `iteration.py next` — which enforces
   the cap and records the folder in `.current_iteration` itself — then
   copies the brief to `brief-snapshot.md`.
   *The snapshot is on the guard's allow-list; the cursor is the script's
   business, not the orchestrator's.*
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
   - CHANGES REQUESTED → new folder (`iteration.py next`, which moves the
     cursor too), back to 5. The designer is *resumed* and also writes
     `dispositions.md`; the reviewer is *fresh* and reads that log.
   - QUESTIONS → relay to the human, then redo the round **in the same
     folder**. The design wasn't judged wrong — it couldn't be judged at all
     — so a question round doesn't spend one of the four iterations.
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
- **The orchestrator's shell.** Its write guard watches Write and Edit; as a
  skill in the main session it also has Bash, which the guard does not see.
  This one gets its own section below — it is the best exhibit in the repo.
- **`memory: project` needs auto memory on.** Three agents declare it, and in
  testing it appeared inert — the docs explain why: the `memory` field only
  takes effect when Claude Code's auto memory is enabled; with it off, the
  agent launches without memory instructions or tools
  ([sub-agents reference](https://code.claude.com/docs/en/sub-agents)). The
  declarations are kept, correctly described as conditional.

Knowing what your guardrails *don't* catch is as important as knowing what they
do.

### The coordinator's shell — a gap kept on purpose

The coordinator must not write the design, and a guard enforces that — on the
Write and Edit tools. But the coordinator is a *skill* running in the main
session, and the main session has a shell. This goes around the guard
entirely:

```
Write to docs/1/definition.md          -> blocked
echo "..." > docs/1/definition.md      -> allowed, silently
```

Same outcome, different route, no guard on the second route. And a skill's
`allowed-tools` cannot close it: that field *pre-approves* tools so they
don't prompt — it never removes one. The four specialists don't have this
gap because an agent's `tools:` list is a hard restriction and theirs
contains no shell. **The gap is what happens when a restriction that works
for agents is assumed to work for a skill.**

How serious it is depends on who is watching. With a human present, an
unexpected shell command hits the permission prompt — the permission system
covers for the guard (the hardening pass removed the `Bash(echo *)`
pre-approval that would have let an `echo` write through silently). Run
unattended, the guard is the only thing standing there, and it isn't looking
at the shell.

**The proper fix exists and was deliberately not done.** Move the
coordinator into `.claude/agents/coordinator.md` with a tool list and no
shell in it — no second route to close, because there is no second route.
The platform supports it: subagents can spawn subagents (three layers deep
by default — a default that has churned across CLI versions), can be resumed
with context intact, and can even be granted `AskUserQuestion` to talk to
the human directly. The price is the shape of the repo: a fifth agent, the
skill reduced to a relay stub (which still has the shell), and this guide's
clearest teaching contrast — agent `tools:` restricts, skill `allowed-tools`
merely pre-approves — reduced to a footnote.

Kept as a skill, for three reasons:

1. **This is a learning repo**, and the gap is its best exhibit of a
   transferable lesson: a guard that watches routes is always one trick
   behind; take the capability away instead. Fixing it would remove the
   exhibit. An honest, loudly documented limit teaches more than the fix.
2. **The guard covers the failure it exists for.** The threat is *drift* — a
   coordinator that forgets the rule and reaches for the normal write tool
   gets blocked. Evading it takes a deliberately odd way of writing a file,
   which is not what drifting looks like.
3. **A bypass can't hide from the record.** The audit log means a transcript
   that claims a block happened while `docs/hook-audit.log` shows nothing is
   lying — dodging the guard cannot forge the log's silence.

If this pipeline were ever to run unattended, with the blinding rule
required to be *true* rather than true-under-supervision, the
coordinator-as-agent redesign is the one change to make first.

---

## 10. The transferable lessons

1. **Restrict subagents with `tools:`.** It is a hard allowlist — the agent
   cannot call anything else, whatever its prompt says. This is the bluntest
   and most reliable control in the system.
2. **`allowed-tools:` on a skill is the opposite of a restriction** — it
   pre-approves tools so they don't prompt, and expires on the next user
   message. `disallowed-tools:` is the one that removes tools. Do not confuse
   a permission grant with a sandbox.
3. **PreToolUse blocks; PostToolUse judges results.** Pick by whether you need
   to prevent the action or inspect its output.
4. **Hard-block facts, warn on guesses.** A heuristic that blocks will
   eventually halt something important for no reason.
5. **Exit 0 stderr is invisible.** It reaches the debug log and nothing else.
   To warn without blocking, emit JSON on stdout: `systemMessage` for the
   user, `hookSpecificOutput.additionalContext` for Claude.
6. **Exit 2's meaning is per-event.** It blocks at PreToolUse, merely warns at
   PostToolUse (the tool already ran), and at SubagentStop it stops the agent
   *finishing* — which keeps it running. Check the per-event table rather than
   assuming.
7. **Files are how state survives an agent boundary.** No shared memory.
8. **Isolation is a setting, not a constraint** — resume the designer for
   continuity, spawn the reviewer fresh for independence.
9. **If the coordinator can't read it, it can't verify it** — which is exactly
   when you need a hook.
10. **Pair prompts with enforcement.** A format instruction plus a hook that
   validates it is far stronger than either alone.
11. **Prefer honest coarseness to fake precision.** The SubagentStop hook checks
   what it actually can, and documents what it can't.
12. **Write down what you didn't fix.** Undocumented gaps get mistaken for
    guarantees.
13. **Verify the layer you are making claims about.** Every test in this repo
    exercises *the scripts*. None of them exercise *the harness contract* —
    what Claude Code does with an exit code, where stderr goes, what
    `allowed-tools` grants. Four wrong claims in the first version of this
    guide lived in exactly that gap, and a fully green test suite could not
    see any of them. Green tests measure the thing you tested, not the thing
    you asserted.
14. **A guard that checks how a path ends trusts everything before it.**
    The first version of the write guards passed any path ending in
    `docs/<n>/<file>` — including `/tmp/evil/docs/2/review.md`. Anchor path
    rules to a root and require the resolved path to land inside it.
15. **Guards should leave a record.** A block message reaches only the agent
    that triggered it; afterwards, "nothing fired" and "nothing was loaded"
    look the same. One append-only log line per decision makes the difference
    checkable — and gives any later audit something mechanical to trust.

---

## A note on sourcing

Every behavioural claim about Claude Code in this guide links to the reference
doc it comes from. That convention exists because the first version of this
guide got four of them wrong — `allowed-tools`, exit-0 stderr, PostToolUse
blocking, and SubagentStop `block` semantics — and nothing in the test suite
could catch a documentation error. A citation lets you check a claim without
running anything, and lets a future editor re-check it against a newer doc.

Behaviour observed in a live session beats these docs, and these docs beat this
guide. If you find a disagreement, that order is the tiebreak.
