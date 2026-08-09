# Hooks, skills, tools & permissions — from zero to runtime

This is the mechanics manual. It explains the four building blocks this
repo is made of — first *what they are and why they exist*, then *how you
write them*, then *what actually happens at runtime*. GUIDE.md tells you
why this pipeline made the choices it made; this document teaches the
machinery those choices are made of. Read this one first if the YAML and
JSON in the repo still look like incantations.

Everything here is illustrated with this repo's own files, so you can open
each example next to its explanation.

---

# Part 1 — What these things are, and why

Start from what a Claude Code session actually is: a language model in a
loop. The model reads the conversation, decides what to do next, and — this
is the important part — *it cannot touch anything*. It can only produce
text. Everything real that happens (a file read, a file written, a command
run) happens because the model asked the harness to use a **tool**, and the
harness did it.

**Tools are the hands.** `Read`, `Write`, `Edit`, `Bash` (the shell),
`Grep`, `Glob`, `Agent` (delegate to a subagent), `AskUserQuestion` (put
clickable choices to the human). Every action passes through one. That
choke point is what makes everything else in this document possible: if all
action goes through tools, then controlling tools controls action.

**Permissions are what the hands may touch.** Some tool uses are harmless
(reading a file), some aren't (running `rm`). Claude Code therefore asks
you before risky tool calls — that's the permission prompt — and keeps
rules about what's pre-approved, what's always denied, and what always
requires asking. The outermost permission is **workspace trust**: the "do
you trust the files in this folder?" dialog, which gates whether a
project's own configuration is honoured at all.

**Skills are packaged procedures.** A skill is a markdown file of
instructions that loads into the conversation when invoked — by you typing
`/name`, or (unless the skill forbids it) by Claude deciding it fits the
task. Why needed: without skills, every repeatable workflow means pasting
the same instructions into chat. With them, `/design-cycle brief.md` *is*
the pipeline. This repo's one skill is
`.claude/skills/design-cycle/SKILL.md` — the orchestrator's entire job
description.

**Agents (subagents) are coworkers with their own context.** Delegating to
an agent starts a fresh conversation with its own instructions, its own
tool list, and no memory of yours. Why needed: isolation. This repo's
reviewer judges a design *without knowing how it was made* — that is only
possible because the reviewer is a separate context, not a paragraph in a
shared one.

**Hooks are rules as code.** A hook is a shell command the harness runs at
a fixed moment — before a tool call, after one, when an agent finishes,
when a session starts. The harness runs it *mechanically*: the model does
not decide whether the hook runs and cannot talk it out of its answer. Why
needed: everything else on this list is, at bottom, *prose that steers a
model*, and prose can drift. A hook is the one mechanism that doesn't.
This repo uses hooks in three postures: **guards** that block rule-breaking
writes, **warnings** that flag suspicious-but-maybe-fine behaviour without
blocking, and a **flight recorder** that writes down what happened.

How they stack, smallest picture:

```
permissions & trust  ─  what any of this MAY do
        tools        ─  what a session CAN do
        skills       ─  procedures, loaded when invoked
        agents       ─  separate contexts with their own tools
        hooks        ─  code that fires at fixed moments, regardless
```

---

# Part 2 — How you write them

## 2.1 A hook declaration, dissected

This is the designer's write guard, verbatim from
`.claude/agents/designer.md`:

```yaml
hooks:
  PreToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/guard_output_path.py" definition.md dispositions.md'
```

Line by line:

- **`hooks:`** — the top-level map. Its keys are **event names**; its
  values are lists of matcher groups. One `hooks:` block can declare many
  events at once.
- **`PreToolUse`** — the event: *when* this fires. `PreToolUse` means
  "before a tool call executes", and it is the only write-guard moment that
  can actually prevent anything — everything later is reaction. Other
  events you'll meet in this repo: `PostToolUse` (after; can't block),
  `Stop` (when the agent finishes — auto-converted to `SubagentStop` for
  subagents), `SessionStart`, `FileChanged`, and the rest of the flight
  recorder's catalogue (GUIDE.md §4 has the full table).
- **`- matcher: "Write|Edit"`** — *which occurrences* of the event. For
  tool events the matcher is a **regex matched against the tool's name** —
  this one fires for the `Write` tool or the `Edit` tool, and not for
  `Read` or `Bash`. It matches tool *names*, never file paths — path
  logic belongs to your script. Omit `matcher` entirely and the hooks
  fire on every occurrence of the event. Two events repurpose the field:
  on `SubagentStop` it matches the *agent type*, on `FileChanged` the
  *watched filename*.
- **`hooks:` (inner)** — the list of things to run when the matcher hits.
  More than one is fine; each runs.
- **`type: command`** — how to run it. `command` means "spawn this shell
  command"; it is the type you will use essentially always.
- **`command: '...'`** — the actual command line. Three details that carry
  all the weight:
  - **`${CLAUDE_PROJECT_DIR}`** is an environment variable the harness
    sets to the project root. Using it makes the path work no matter what
    the current working directory is when the hook fires — hook scripts
    must never assume they're run from the repo root (this repo once had a
    bug from exactly that assumption; see `check_subagent_output.py`'s
    history in CASE-STUDY.md).
  - **`definition.md dispositions.md`** — everything after the script is
    ordinary command-line arguments. This is how ONE generic script serves
    four different agents: each agent's declaration passes its own
    allowlist. The knowledge "the designer may write definition.md" lives
    *in this line*, not in the script.
  - The input arrives separately: when the hook fires, the harness pipes
    the event's details to your command as **JSON on stdin** (Part 3).

The same declaration in JSON, for `.claude/settings.json` — same shape,
different syntax:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/scripts/guard_docs_writes.py\"" }
        ]
      }
    ]
  }
}
```

## 2.2 Where a hook lives changes what it means

The same syntax can be declared in four places, and the *place* is a
scoping decision:

| Declared in | Fires for | Loads | This repo's example |
|---|---|---|---|
| an agent's frontmatter | that agent's activity only | when the agent is delegated to — **after workspace trust** | `guard_output_path.py` ×4, `check_subagent_output.py`, `guard_agent_shell.py` |
| a skill's frontmatter | the main session, while the skill orchestrates | when the skill is invoked — after trust | `guard_orchestrator_write.py`, `warn_paste_in_prompt.py` |
| project `.claude/settings.json` | **every session in this project**, and subagents' tool calls too | session start | `guard_docs_writes.py`, the flight recorder, both validators |
| `~/.claude/settings.json` (user) | every session on your machine | session start | (none here — this repo keeps to itself) |

Rules of thumb, straight from this repo's scars:

- **Per-agent rules must live in agent frontmatter** — that is the only
  place that knows *who* is acting. A settings-level hook cannot tell the
  reviewer's write from the designer's; the identity exists only in which
  agent's file declares the hook.
- **Rules that must survive anything go in settings.json.** Frontmatter
  hooks sit behind the trust gate and have failed to load silently
  (CASE-STUDY.md); the settings layer is what held. Defense in depth means
  both.
- **Skill-frontmatter hooks see the orchestrator, not the agents.** A
  PreToolUse hook in SKILL.md fires on the *main session's* tool calls
  only — delegated agents' writes never pass through it.

## 2.3 What an agent is made of

From `.claude/agents/clarifier.md`, abridged:

```yaml
---
name: clarifier
description: Reads an initial brief and produces the questions...
tools: Read, Write, Grep, Glob, Bash
model: inherit
memory: project
hooks:
  PreToolUse:
    - matcher: "Write|Edit"
      hooks: [...]
    - matcher: "Bash"
      hooks: [...]
---
(the agent's instructions, in plain prose)
```

- **`tools:`** is a **restriction**: the agent gets these tools and no
  others. Bare names only — `Bash` grants the whole shell; you cannot
  write `Bash(some pattern)` here. Withholding is the strongest move in
  this file: no `Agent` means it can't delegate, no `AskUserQuestion`
  means it can't reach the human, no `Bash` means no shell at all. What
  isn't granted doesn't need guarding.
- **`skills:`** (not used in this repo) preloads named skills into the
  agent's context at startup — full content, not just descriptions. That
  is how you'd give an agent a procedure without pasting it into its
  prompt.
- **`memory: project`** gives the agent a durable notes directory across
  runs (when auto-memory is enabled) — different thing entirely from
  conversation context.
- **`hooks:`** — as above, scoped to this agent.
- Everything **below the frontmatter** is the agent's system prompt: its
  role, its rules, its output format. Prose — which is exactly why the
  hooks exist alongside it.

## 2.4 Giving an agent a tool — the two-part trick

Suppose you want an agent to have *one specific script* and nothing else.
`tools:` can't say that — it grants `Bash` whole or not at all. So this
repo builds it from two parts, and the pair is a live exhibit:

1. **Grant the shell**: the clarifier's `tools:` includes `Bash`.
2. **Narrow it with a hook**: the clarifier declares a `PreToolUse` hook
   with `matcher: "Bash"` running `guard_agent_shell.py` with the blessed
   command as its argument. Every shell command the clarifier attempts is
   checked; anything that isn't `python3 scripts/brief_stats.py …` — or
   that smuggles shell operators after the blessed prefix (`;`, `&&`,
   `$()`…) — is refused with an audit line.

The tool itself, `scripts/brief_stats.py`, is deliberately ordinary
Python — word/heading/question counts for a brief. Nothing in the file
makes it "a tool"; **being a tool is a property of the wiring, not the
script**. And the contrast completes the lesson: the designer's `tools:`
has no `Bash` at all, so the same script, sitting in the same repo, simply
does not exist for it. Capability granted to one, absent for another,
allowlist enforced in between — try it by asking each agent to run it.

(Honest limit, stated in the guard's docstring too: a command-prefix
allowlist stops drift, not a determined adversary — it is a leash, not a
sandbox.)

## 2.5 What a skill is made of

From `.claude/skills/design-cycle/SKILL.md`:

```yaml
---
name: design-cycle
description: Runs the clarify, design, review and backlog pipeline...
argument-hint: [path-to-brief]
disable-model-invocation: true
allowed-tools: Bash(python3 scripts/iteration.py *) Read Write Edit
hooks: [...]
---
```

- **`description`** is what Claude reads when deciding whether a skill
  fits the current task — it is the trigger surface.
- **`disable-model-invocation: true`** removes that trigger: the skill
  runs *only* when a human types `/design-cycle`. The side effect matters
  (GUIDE.md §3 tells the story of being burned by it): an invite-only
  skill is invisible to Claude's own choosing, so pushier installed
  skills win any plain-words request.
- **`allowed-tools`** is a **pre-approval, not a restriction** — the most
  misread field in the file. It lists tool uses that won't show a
  permission prompt during the turn that invoked the skill — and unlike
  agent `tools:`, entries here *can* carry specifiers:
  `Bash(python3 scripts/iteration.py *)` pre-approves exactly that
  command shape. The grant expires when you send your next message; the
  skill's *content* persists for the session. Two lifetimes, one
  frontmatter. The field that actually restricts is `disallowed-tools`.
- **`$ARGUMENTS`** in the body receives what you typed after the command;
  **`` !`command` ``** runs at load time and injects its output into the
  prompt (the skill uses it to list existing iteration folders).

## 2.6 Permissions in settings

Beyond per-skill grants, `settings.json` (project or user) takes standing
rules:

```json
{
  "permissions": {
    "allow": [ "Bash(python3 scripts/iteration.py *)" ],
    "ask":   [ "Bash(git push *)" ],
    "deny":  [ "Read(./secrets/**)" ]
  }
}
```

Each rule is `Tool` or `Tool(specifier)`. Evaluation order is **deny, then
ask, then allow — first match wins**; specificity doesn't reorder it, so a
deny always beats an allow. This repo declares no permission rules — its
posture is hooks (which decide per-call, with logging) over blanket
grants — but the mechanism is where you'd start in a repo of your own.
And around all of it sits **workspace trust**: until you accept the
dialog for a folder, its project-level configuration — including agent
and skill frontmatter hooks — is not honoured. That gate fails *silent*,
which is how this repo earned its case study.

---

# Part 3 — What actually happens at runtime

## 3.1 Session start

You run `claude` in the project folder. Before you type anything:

1. Settings load and merge — user, project, local — including the
   `hooks:` blocks, which are **registered** (not run) now.
2. `CLAUDE.md` is read into context (the recorder logs
   `InstructionsLoaded`).
3. Trust is checked for the folder. Untrusted → project frontmatter hooks
   will be silently skipped later. This single step is the villain of
   CASE-STUDY.md.
4. The `SessionStart` event fires — in this repo, the flight recorder
   writes its first line, and warns the session if a pipeline run is
   mid-flight.

Nothing skill- or agent-related has happened: skills load when invoked,
agent hooks arm when the agent is delegated to.

## 3.2 The life of one Write call

The clarifier tries to write `docs/1/clarification.md`. Here is the whole
journey — this is the paragraph to internalise, everything else is
elaboration:

1. **The model emits a tool call**: `Write` with
   `{"file_path": "docs/1/clarification.md", "content": "..."}`. Nothing
   has touched disk.
2. **The harness collects every registered `PreToolUse` hook whose matcher
   matches the string `Write`** — here: `guard_output_path.py` (from the
   clarifier's frontmatter) and `guard_docs_writes.py` (from
   settings.json).
3. **Each hook runs as a separate process.** The command line from the
   declaration is executed; on stdin it receives the event as JSON:

   ```json
   { "hook_event_name": "PreToolUse",
     "tool_name": "Write",
     "tool_input": { "file_path": "docs/1/clarification.md", "content": "..." } }
   ```

   (For a `Bash` call, `tool_input` carries `command` instead — which is
   all `guard_agent_shell.py` looks at.)
4. **Each hook answers with its exit code.**
   - `0` — no objection. (Optionally, JSON on stdout for richer replies.)
   - `2` — **blocked**: the tool call never executes, and whatever the
     hook printed to **stderr is shown to the model** as the reason. The
     write does not happen.
   - Anything else — a hook error; treated as non-blocking.
5. All PreToolUse hooks pass → **the tool actually runs**. The file is
   written.
6. **`PostToolUse` hooks fire** (matcher against `Write` again) — here
   `validate_review_format.py` and `warn_estimates_in_backlog.py`, both
   of which look at the path and stand down: not their file. PostToolUse
   *cannot* block — the file is already on disk. Exit 2 here means "show
   my stderr to the model so it fixes the file with another write."
7. Later, when the clarifier finishes, its **`Stop` hook** fires (as
   `SubagentStop`): `check_subagent_output.py` checks the file it owed
   actually exists.

Every one of those decisions appended a line to `docs/hook-audit.log`.
That's not the harness — that's this repo's scripts calling
`hook_audit.record()`, because a decision nobody can see afterwards is a
decision you can't verify (CASE-STUDY.md, lesson 1).

## 3.3 How a hook talks back — the full channel table

| You want | Do this | Caveat |
|---|---|---|
| block the call | exit `2` (PreToolUse), or `{"decision":"block","reason":…}` | "block" *reverses meaning* at Stop/SubagentStop: it prevents the agent from *stopping* — it keeps it running with `reason` as its next instruction |
| explain a block to the model | print to **stderr**, exit 2 | stderr is only shown on exit 2 |
| warn without blocking | JSON on stdout, exit 0: `systemMessage` (shown to the human), `hookSpecificOutput.additionalContext` (given to the model) | **stderr on exit 0 goes to a debug log nobody reads.** Two hooks in this repo were once inert for exactly this reason — tested, documented, and doing nothing |
| stay silent | exit 0, no output | indistinguishable from "never ran" unless you log — hence the audit log |

## 3.4 Delegation, and where hooks come from at each moment

When the orchestrator delegates to the reviewer:

- `SubagentStart` fires (recorder line).
- A **fresh context** is created: the reviewer's frontmatter prose becomes
  its instructions; its `tools:` list defines its hands; its `skills:`
  (if any) are injected.
- Its frontmatter hooks are armed **if the folder is trusted** — this is
  the moment the trust gate bites, and it bites *per agent file*.
- The reviewer works; every tool call runs the gauntlet of §3.2 — its own
  frontmatter hooks plus the settings layer. The orchestrator's
  skill-frontmatter hooks are *not* in that gauntlet: they belong to the
  main session.
- The reviewer finishes → `Stop`→`SubagentStop` → its stop-check runs →
  `SubagentStop` recorder line. Its context is discarded; only its final
  report and its files survive.

That last sentence is the whole architecture of this repo: **contexts are
disposable, files are durable, and hooks are how the rules survive the
disposal.**

---

## Where to next

- GUIDE.md — why *this pipeline* wired these mechanisms the way it did,
  including every incident that changed the design.
- verify_hooks.py — every hook in this document, run in front of you.
- CASE-STUDY.md — what happened when the loading step silently failed,
  which is the best argument for Part 3 mattering at all.
