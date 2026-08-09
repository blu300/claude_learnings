# claude_learnings

A working example built to teach four Claude Code concepts: **subagents**,
**skills**, **hooks**, and **the state that passes between them**.

The example is a *design pipeline*. You give it a rough brief; four specialist
agents interrogate it, design it, review the design, and break the result into
a backlog. A coordinator routes between them and relays anything that needs a
human.

It is deliberately small — four agents, one skill, nine hook scripts, two
shared modules and a folder-management script, none longer than about a
hundred and fifty lines — because the point is to be readable, not
impressive.

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

Runs write their output to numbered folders — `docs/1/`, `docs/2/`, … — one
per design iteration. A real, non-converging run is committed under
`docs/example-run/` as a specimen to read (out of the numbered range, so it
doesn't count against the iteration cap). Everything written *about* the
system lives in `docs/learning/`.

## Try it

```bash
python3 -m pytest tests/ -q         # 90 passed — the scripts are correct
python3 scripts/verify_hooks.py     # 62 cases — watch each hook decide
```

The second one is the one to *read*. It prints the JSON going in, the exit
code coming out, and the message the agent would see, for every hook.

For everything beyond these two commands — running the pipeline for real,
watching the audit log live, testing the flight recorder, and what to do
when hooks don't fire — see **[`run-guide.md`](run-guide.md)**, the
practical companion to the learning path below.

## The learning path

In order. Each step assumes the ones before it.

1. **[`docs/learning/overview.md`](docs/learning/overview.md)** — the tour:
   what a run looks like from your side, then a first pass over all four
   mechanisms.
2. **Run the tests**: `python3 -m pytest tests/ -q`. This proves the scripts
   are correct, and nothing else — a distinction the rest of the path keeps
   coming back to.
3. **Run and read `python3 scripts/verify_hooks.py`** — every hook shown
   deciding, with the JSON in, the exit code out, and the audit log it leaves
   behind.
4. **[`docs/learning/GUIDE.md`](docs/learning/GUIDE.md)** — every mechanism in
   depth, why each choice was made, the known gap that was deliberately kept,
   and the fifteen transferable lessons.
5. **Read the recorded run** in `docs/example-run/`, with the "Results from
   the recorded run" section of
   [`docs/learning/VERIFY.md`](docs/learning/VERIFY.md) as your companion. It
   did not converge, and that outcome is worth seeing.
6. **Read the prompts themselves**: `.claude/agents/*.md` and
   `.claude/skills/design-cycle/SKILL.md`. After the guide, you will
   recognise every line.
7. **Optional capstone**: run the live-fire test in
   [`LLM as judge.md`](LLM%20as%20judge.md). It takes a real session, real
   money, and ~30 minutes, and it tests the one thing nothing above can —
   whether the harness actually runs these guards.
8. **[`docs/learning/CASE-STUDY.md`](docs/learning/CASE-STUDY.md)** — read
   this last: the day the capstone was run for real and five of seven
   guards silently never loaded. What it looked like, why it was invisible,
   the three root causes, and the six lessons that reshaped this repo.
   (The unabridged forensic record is [`hook_error.md`](hook_error.md).)

`docs/superpowers/` holds the original spec and implementation plan — the
historical record, superseded in places by later hardening.

Behavioural claims in these documents are checked against the
[Claude Code docs](https://code.claude.com/docs/en/hooks). If you observe
something different in a live session, believe the session.
