# Verifying the Pipeline — Step by Step

A guide to reproducing every check that was run against this system, so you can
see the mechanisms working yourself rather than taking a transcript's word for
it.

There are three levels, cheapest first:

| Level | Command | Time | What it proves |
|---|---|---|---|
| 1. Unit tests | `python3 -m pytest tests/ -q` | seconds | The scripts are correct |
| 2. Hook demo | `python3 scripts/verify_hooks.py` | seconds | The mechanisms behave as designed, with visible inputs and outputs |
| 3. Live run | see [Level 3](#level-3--a-live-pipeline-run) | ~20 min | The agents actually use them |

---

## Level 1 — Unit tests

```bash
python3 -m pytest tests/ -q
```

Expected: `102 passed`.

If `pytest` is missing: `pip install pytest`.

These assert correctness in isolation — each script gets a crafted input and
its output is checked. They tell you nothing about whether the hooks are
*wired up*, only that the code works.

---

## Level 2 — The hook demonstration harness

```bash
python3 scripts/verify_hooks.py
```

Expected: `66/66 cases behaved as expected`, exit code 0.

This is the one to read rather than just run. For every hook it prints the
payload going in, the exit code coming out, and the message an agent would
see. It builds any files it needs in a temp directory and cleans up, so it
never touches your real `docs/`.

### What each section shows

**1. `guard_orchestrator_write.py`** — the blinding rule, enforced.
Watch the first case carefully: creating `clarification.md` is REFUSED —
the clarifier creates that file, and the orchestrator may only append to
it once it exists (the rule a live run's drift added; the block message
names the right agent). Then watch it allow the same path once the file
exists, allow `docs/1/brief-snapshot.md` (orchestrator-created, so no
existence rule), then
refuse everything else with **exit 2** — the design, the cursor file (which
`iteration.py` owns now), a `clarification.md` outside `docs/1`, and a
lookalike path outside the project. This is why the orchestrator can be
trusted not to write the design with its file tools: it *can't*. (Its shell
is another matter — see "The coordinator's shell" in `GUIDE.md`.)

**2. `guard_output_path.py`** — one guard, four agents, anchored and scoped.
The allowed filenames arrive as CLI arguments, which is how a single script
serves every agent. Three cases to stare at: `REFUSES a PREVIOUS iteration`
(with the cursor at 2, a write to `docs/1/definition.md` is refused, so a
later iteration cannot clobber an earlier one), `REFUSES a lookalike tree`
(a path that merely *ends* in `docs/2/definition.md` but lives outside the
project — the bug the anchoring fix closed), and `REFUSES unknown options`
(a dropped flag must not silently corrupt the allowlist). The section ends by
printing `docs/hook-audit.log` from the temp scope — every decision you just
watched, recorded by the scripts themselves.

**2b. `guard_agent_shell.py`** — a whole tool grant, narrowed to one
command. The clarifier's `tools:` list grants Bash (all-or-nothing — the
list takes no patterns), and this hook makes it a single-command shell.
The case to stare at is `REFUSES the blessed prefix with a chained
command`: `python3 scripts/brief_stats.py b.md; rm -rf docs` *starts with*
the allowed prefix — without the shell-operator check, a prefix allowlist
is a doormat.

**3. `warn_paste_in_prompt.py`** — the heuristic/structural split.
It detects pasted content and warns **while still exiting 0**. Compare that
directly with section 1, where a structural violation exits 2. This is the
single most important design decision in the system: a guess must never halt an
unattended pipeline.

Look at *how* it warns. It emits JSON on stdout — `systemMessage` for the user,
`hookSpecificOutput.additionalContext` for Claude — not stderr. Stderr from a
hook that exits 0 goes to the debug log and nobody ever sees it, so an earlier
version of this hook that printed to stderr was completely inert while looking
correct and passing its tests.

**4. `warn_estimates_in_backlog.py`** — why PostToolUse exists.
It reads the file's *content*, which does not exist until the write has already
happened. No amount of PreToolUse cleverness can inspect a file that isn't
written yet.

**5. `validate_review_format.py`** — structural rules at a non-blocking event.
PostToolUse **cannot block**: the malformed `review.md` is already on disk and
stays there. Exit 2 shows the error to the reviewer so it rewrites the file —
a weaker guarantee than the PreToolUse guards, and worth understanding as such.
The two cases worth staring at are `REFUSES APPROVED that contradicts a FAIL`
and `REFUSES CHANGES REQUESTED with all PASS`. The hook is enforcing *internal
consistency* between two parts of a document — an agent cannot quietly approve
a design it just scored as failing.

**6. `check_subagent_output.py`** — a different event, a different channel.
Fires on `SubagentStop` (declared as a `Stop` hook in each agent's
frontmatter), so it gets no `file_path` — what it knows comes from the
frontmatter arguments: each agent's wiring passes the filename that agent
owns. Watch the `POPULATED folder` case: `definition.md` already exists, the
coarse check is satisfied, and the missing `review.md` is still caught. It
replies with `{"decision": "block", "reason": ...}` on stdout while exiting
0 — a richer channel than a status code.

`block` here does **not** stop the agent: at SubagentStop it prevents the agent
*finishing*, so the agent keeps running and receives the `reason` as its next
instruction. That means the reason must be addressed to the **subagent**, not
to the orchestrator, which never sees it. Note the no-cursor case too: the
hook stays out of the way rather than guessing — but leaves an `allow` line
in the audit log saying so, because a silent fail-open is indistinguishable
from a hook that never loaded.

**6b. `guard_docs_writes.py`** — the settings.json floor. After the day the
agent-frontmatter hooks silently failed to load (`hook_error.md`), the
agent-independent rules were duplicated into a guard wired in
`.claude/settings.json`, which runs in every session. It cannot know *who* is
writing — agent identity exists only in frontmatter — so cross-writes between
agents remain frontmatter's job; but older-iteration overwrites, stray files,
and Write/Edit access to the iteration cursor and the audit log itself are
blocked in every session, whichever way it was launched.

**7. `iteration.py next`** — the cap, no flag required.
Five calls, four folders. The fifth exits 1 and creates nothing — the cap is
a constant in the script, `--max` can lower it but never raise it (watch the
`--max 99` call refuse), and each successful call moves
`docs/.current_iteration` itself. The orchestrator cannot loop forever
because there is nowhere left to write, and it cannot forget the cursor
because it never touches it.

**8. `session_log.py`** — the flight recorder. Five different session
events, five lines in the same audit log the guards use. Two cases repay a
close look: `SessionStart` doesn't just log — when a pipeline run is
mid-flight it *injects context*, so a fresh session is warned about the
state before it can trip over it; and `FileChanged` records the iteration
cursor changing on disk — which a Bash redirect can do without any Write
tool call, invisibly to every PreToolUse guard. The recorder can't prevent
that; it can make sure it isn't silent.

**9. `warn_paste_in_user_prompt.py`** — the paste warning, pointed at the
human. Same heuristics as section 3, different event (`UserPromptSubmit`,
which fires on the human's prompt before Claude processes it) and a
different payload shape. That event *can* reject a prompt outright — watch
both cases exit 0 anyway, because a heuristic must never eat someone's
prompt on a guess.

---

## Level 3 — A live pipeline run

This exercises the agents themselves. Budget ~20 minutes; each agent takes
2–5 minutes.

> **Note on how the pipeline is meant to run.** The `design-cycle` skill is
> invoked by a human (`disable-model-invocation: true`) and runs as the
> orchestrator in the main session. The walkthrough below performs the same
> steps manually, which is useful for watching each stage — but note the
> caveat in [What a manual run does not prove](#what-a-manual-run-does-not-prove).

### Setup

```bash
# 1. Write a brief — anything small with real ambiguity in it.
#    (brief.md at the repo root belongs to the committed run — use a new file.)
cat > my-brief.md <<'EOF'
# Brief: <your thing>
<a few sentences describing what you want and why>
EOF

# 2. Create iteration 1 and snapshot the brief. The script enforces the cap
#    and writes docs/.current_iteration itself — no cursor step needed.
python3 scripts/iteration.py next             # prints docs/1
cp my-brief.md docs/1/brief-snapshot.md
```

The snapshot matters: from here on every agent reads
`docs/1/brief-snapshot.md`, never `my-brief.md`. Edit the original mid-run and
the agents are unaffected.

### The clarify step

Delegate to the `clarifier` agent with **paths only, never file contents**:

> Read the brief at `docs/1/brief-snapshot.md` and write your clarification to
> `docs/1/clarification.md`

It reports back only the path and how many questions are blocking. Read
`docs/1/clarification.md`, put the questions to a human, and write the replies
into the **Answers** section.

If a later answer contradicts an earlier one, do not overwrite it:

```markdown
1. ~~On-demand only~~ **Superseded by #7**
7. [blocking] Batch processing is required for enterprise accounts.
```

### The design/review loop

Delegate to `designer`:

> Criteria are in `docs/1/clarification.md` (read the Answers section). The
> brief is `docs/1/brief-snapshot.md`. Write your design to
> `docs/1/definition.md`

Then to `reviewer` — **always a fresh instance, never resumed**:

> Read the design at `docs/1/definition.md`. The criteria are
> `docs/1/clarification.md` and `docs/1/brief-snapshot.md`. Write your review
> to `docs/1/review.md`

Check the verdict, and confirm the format hook accepts what it wrote:

```bash
head -1 docs/1/review.md
grep -E '^\|' docs/1/review.md          # the scoring table
echo '{"tool_input":{"file_path":"docs/1/review.md"}}' \
  | python3 scripts/validate_review_format.py; echo "exit=$?"
```

`exit=0` means the reviewer's real output satisfies the hook that enforces it —
prompt and enforcement agreeing on a live artifact.

On `CHANGES REQUESTED`, bump the iteration and go round again:

```bash
python3 scripts/iteration.py next   # creates docs/2 and moves the cursor
```

**Resume the same designer** (do not spawn a new one) and ask for both files
this time — `docs/2/definition.md` and `docs/2/dispositions.md`. Spawn a
**fresh** reviewer and pass it the dispositions paths.

That asymmetry is the point: the designer keeps continuity, the reviewer keeps
independence.

### Reaching the end

- `Verdict: APPROVED` → delegate to `backlog-writer` for `backlog.md`.
- `Verdict: CHANGES REQUESTED` on iteration 4 → the cap fires. Confirm it:

```bash
python3 scripts/iteration.py next   # exit 1, no docs/5 — the cap is in the script
```

Either way, report from `dispositions.md` — never from the design.

### What to watch for

| Behaviour | Where it comes from |
|---|---|
| Designer writes no `dispositions.md` on iteration 1 | Correct — there is no review to respond to yet |
| Reviewer's findings are *new* each round, not repeats | It read the dispositions log |
| Designer rejects a finding with reasoning | Anti-capitulation — it is not obliged to accept |
| A "Why full acceptance was appropriate" paragraph appears | The deference self-check, triggered by accepting everything |
| Verdict matches the table (any FAIL → CHANGES REQUESTED) | Mechanical derivation, not a free-floating judgement |

---

## Results from the recorded run

A full run against a throwaway brief (a book-lending tracker) is committed
under `docs/example-run/` (folders `1/` through `4/`). It **did not
converge** — four iterations, then the cap fired.

That is a useful outcome, not a failed demo. What it showed:

| Iteration | FAILs | Finding |
|---|---|---|
| 1 | 2 | Freshness reporter false-warns permanently; `history` undefined |
| 2 | 2 | Git adapter syncs nothing (no commit); device-id ping-pong |
| 3 | 1 | Git adapter never establishes a remote |
| 4 | 1 | Setup block pushes a repo that can hold no commit |

Quality converged even though the verdict didn't: Coverage, Decisions, Gaps and
Over-reach all settled to PASS, and each surviving finding was narrower than
the last.

Two behaviours worth reading the files for:

- **`docs/example-run/3/dispositions.md`** contains the deference self-check,
  written unprompted: *"uniform agreement is the shape capitulation also takes."*
- **`docs/example-run/4/dispositions.md`** records the designer correcting the *reviewer's*
  stated failure mechanism — it accepted the finding but showed the review had
  named the wrong step. Without the log, that correction would have been buried
  in a design nobody in the loop is allowed to read.

---

## What a manual run does not prove

Be clear about the limits of the walkthrough above, because they are real:

- **Skill-level hooks do not fire.** The `PreToolUse` hooks declared in
  `SKILL.md`'s frontmatter apply when the *skill* is running as the
  orchestrator. Driving the steps by hand means those never trigger
  automatically — which is exactly why `verify_hooks.py` invokes them directly.
  (The subagent-stop check is declared as a `Stop` hook in each agent's own
  frontmatter — the documented location; a legacy `SubagentStop` block also
  remains in `SKILL.md`, though no session has ever been observed running it.)
- **No hook has been observed blocking a live agent mid-run.** In the recorded
  run no agent ever attempted a bad write, so every block shown came from
  feeding a script a payload. The scripts are proven; "a hook automatically
  stops a misbehaving agent" is not.
- **`memory: project` was inert in the recorded run — and the docs say when
  it would be.** The `memory` field only takes effect when Claude Code's auto
  memory is enabled; with auto memory off, the agent launches without memory
  instructions or tools
  ([sub-agents reference](https://code.claude.com/docs/en/sub-agents)). The
  designer reporting "no memory directory available" is consistent with auto
  memory being off in that session, not with a broken declaration. To see the
  feature work, enable auto memory and re-run.
- **One run is not evidence.** The anti-re-litigation check was confounded: the
  rejected remedy became moot when the designer deleted the component it
  attached to. A cleaner test needs a finding rejected while the component
  survives.
- **The recorded run predates the hardening pass.** The same-folder redo of a
  `QUESTIONS` round, the in-script iteration cap, the script-owned cursor and
  the audit log have all been proven at the script layer but not yet observed
  in a live pipeline run — the specimen under `docs/example-run/` never hit a
  `QUESTIONS` verdict at all. It also predates the interactive question flow:
  its clarification file shows the old all-questions-in-one-reply style, where
  a current run puts blocking questions to the human as clickable panels. The live-fire test in `LLM as judge.md` is how
  to close that gap.

---

## Troubleshooting: nothing happens at all

If you run the pipeline and no guard ever fires — no blocks, no warnings, as
though the hooks were not there — check these before debugging any script:

0. **Read `docs/hook-audit.log` first.** Every guard appends a line per
   decision. Lines present means the hooks ran and simply had nothing to
   block; an empty or missing log after a full run means they never loaded —
   and the causes below are the usual suspects.
1. **Workspace trust.** Hooks declared in a project's agent or skill
   frontmatter only run once the workspace trust dialog has been accepted for
   the folder those files came from. Declining it, or never seeing it, disables
   every project hook silently. Same applies to a project skill's
   `allowed-tools`.
2. **You are driving the steps by hand.** Skill-frontmatter hooks apply when
   the *skill* is the orchestrator. Running the steps manually means they never
   fire — use `scripts/verify_hooks.py` to exercise those directly.
3. **You are looking for a stderr warning.** Warn-only hooks exit 0, and exit-0
   stderr goes to the debug log only. Run with `--debug` to see it, or look for
   the `systemMessage` in the transcript instead.

## Cleaning up after a run

```bash
rm -rf docs/1 docs/2 docs/3 docs/4 docs/.current_iteration docs/hook-audit.log my-brief.md
```

Keep `docs/learning/` and `docs/superpowers/` — and keep `brief.md` at the
repo root: it is the committed input of the recorded run.

`docs/.current_iteration` is gitignored — it is a runtime cursor, not an
artifact.
