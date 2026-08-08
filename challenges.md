# Challenges to the learning guide

A review of `docs/GUIDE.md`, `docs/VERIFY.md` and `HANDOFF.md` for use as
beginner teaching material on agents, skills, tools and hooks.

**This is a challenge document, not a patch.** Nothing here has been changed.
Each item states the claim, the evidence against it, and what a correction
would look like. Push back on any of it — several of these are judgement calls
about emphasis rather than outright errors, and they are marked as such.

Every "actual behaviour" below is quoted from the current Claude Code
reference docs (`code.claude.com/docs/en/hooks`, `/skills`, `/sub-agents`),
fetched 2026-08-08. If those docs have changed, or if observed behaviour
differs from them, that beats this document.

## Summary

| # | Where | Claim | Severity |
|---|---|---|---|
| 1 | `docs/GUIDE.md:142`, `:510` | `allowed-tools` restricts the orchestrator's tools | Wrong |
| 2 | `docs/GUIDE.md:234`, `:250`, `:516` | exit 0 + stderr is how warn-only hooks work | Wrong |
| 3 | `docs/GUIDE.md:324`, `docs/VERIFY.md:70` | `validate_review_format.py` is a PostToolUse hard-block | Wrong |
| 4 | `docs/GUIDE.md:340` | SubagentStop `decision: "block"` reports failure to the orchestrator and stops | Wrong |
| 5 | `docs/GUIDE.md:187`, `:193` | "The two events used here" / SubagentStop row | Imprecise |
| 6 | `docs/GUIDE.md:7`, `:267` | "six scripts" | Miscount |
| 7 | not covered anywhere | project-scoped frontmatter hooks need workspace trust | Missing |
| 8 | `HANDOFF.md:37` vs `:48` | recorded live run vs nothing run end-to-end | Contradiction |
| 9 | `docs/README.md:17-18` | 3-iteration converged run ending in `backlog.md` | Stale |

Items 1–4 are the ones that matter. They are all in the layer the verification
does not reach — see [The pattern behind 1–4](#the-pattern-behind-14).

## First, what holds up

Stated so the challenges below are read in proportion.

Both verification claims reproduce exactly:

```
python3 -m pytest tests/ -q      -> 35 passed
python3 scripts/verify_hooks.py  -> 31/31 cases behaved as expected, exit 0
```

Every frontmatter field used across the four agents and the skill is real and
correctly applied: `tools`, `model: inherit`, `memory: project`, `color` and
`hooks` on subagents; `disable-model-invocation`, `argument-hint`,
`allowed-tools` and `hooks` on the skill. `` !`command` `` load-time execution
and `$ARGUMENTS` work as `docs/GUIDE.md:146-152` describes. `matcher: "Agent"`
in `SKILL.md` is genuinely the correct PreToolUse tool name for subagent
spawning — the docs list `Agent` among the matchable tool names, so
`warn_paste_in_prompt.py` is wired to the right event.

The teaching structure is the strong part and is worth preserving through any
correction:

- Pre vs Post explained by *which one you need and why* rather than as an API
  listing (`docs/GUIDE.md:195-198`).
- The context-isolation asymmetry — designer resumed for continuity, reviewer
  spawned fresh for independence — as the organising idea (`:99-110`).
- §9 "What this deliberately does not fix" and `docs/VERIFY.md`'s "What a
  manual run does not prove", including the honest note that `memory: project`
  appears inert. Most tutorials do not do this at all.
- `scripts/verify_hooks.py` as a runnable, readable harness.

## 1. `allowed-tools` is a permission grant, not a restriction

**Claim** — `docs/GUIDE.md:142-145`:

> **`allowed-tools` is scoped to specific commands.** Not "Bash" but
> `Bash(python3 scripts/iteration.py *)`. The orchestrator can run the
> iteration script and `echo`, and nothing else. Again: restriction by
> capability, not by instruction.

And transferable lesson #1, `:510`:

> **Restrict by capability, not instruction.** `tools:` and `allowed-tools:`
> stop things prompts only discourage.

**Actual behaviour** — from the skills reference:

> The `allowed-tools` field grants permission for the listed tools during the
> turn that invokes the skill, so Claude can use them without prompting you for
> approval. **The grant clears when you send your next message** […] **It does
> not restrict which tools are available: every tool remains callable**, and
> your permission settings still govern tools that are not listed.

So `allowed-tools` is the opposite of what the guide says it is: it *widens*
what happens without a prompt, and restricts nothing. The field that removes
tools from the pool is `disallowed-tools`.

**Why this one matters most.** The guide bundles `tools:` and `allowed-tools:`
into a single lesson, but they do opposite things:

| Field | Where | Effect |
|---|---|---|
| `tools:` | subagent frontmatter | **Hard restriction.** The subagent cannot call anything else. `docs/GUIDE.md:81-84` is correct about this. |
| `allowed-tools:` | skill frontmatter | **Pre-approval.** Skips the permission prompt for one turn. Restricts nothing. |
| `disallowed-tools:` | skill frontmatter | **Restriction.** Removes tools from the pool while the skill is active. |

A beginner who learns the guide's version will write a skill believing it is
sandboxed when it is not.

**Second-order point, possibly worth its own paragraph in the guide.** The
grant clears on the user's next message. The `design-cycle` orchestrator is
specifically an interactive multi-turn relay — it puts the clarifier's
questions to the human and waits. On the turn after that answer, the
`allowed-tools` grant is gone and `Bash(python3 scripts/iteration.py *)` will
prompt normally. That is a real operational wrinkle in this exact pipeline, and
a good teaching example of skill-content lifetime versus permission lifetime.

**Suggested correction.** Rewrite `:142-145` as pre-approval; split lesson #1
into "restrict subagents with `tools:`" and "pre-approve skill commands with
`allowed-tools:`, which is not a restriction"; mention `disallowed-tools` as
the actual restricting field; add the clears-on-next-message note.

**Grounds to challenge.** If `allowed-tools` empirically behaved as a
restriction when this was written, say so and cite a version — the field's
semantics are the sort of thing that could have changed.

## 2. Exit 0 with stderr produces no visible warning

**Claim** — the exit code table, `docs/GUIDE.md:232-235`:

> | `0` | Allow. (stderr is still shown — this is how warn-only hooks work.) |

Restated as the section's central principle at `:250` ("Structural rules
hard-block (exit 2). Heuristic rules warn only (exit 0)"), as lesson #4 at
`:516` ("stderr talks to the agent"), and demonstrated in
`docs/VERIFY.md:60` ("prints a warning **and still exits 0**").

**Actual behaviour** — from the hooks reference, verbatim:

> Stderr from a hook that exits 0 goes to the debug log only, never the
> transcript, and Claude never sees it. To read it yourself, enable debug
> logging. To surface a warning to Claude from a `PostToolUse` or
> `PostToolUseFailure` hook, exit 2 instead so Claude sees the stderr even
> though the tool already ran.

**Consequence for this repo.** Both warn hooks are currently inert in a real
session. `scripts/warn_paste_in_prompt.py` and
`scripts/warn_estimates_in_backlog.py` each end with:

```python
print("Warning: ...", file=sys.stderr)
return 0
```

Nobody sees that — not the user, not the agent. `verify_hooks.py` shows the
warning text because it runs the script directly and captures stderr itself,
which is exactly the gap described in
[The pattern behind 1–4](#the-pattern-behind-14).

**The principle survives; the mechanism does not.** "Hard-block facts, warn on
guesses" is a good rule and should stay. What needs replacing is the claim
about *how* you warn. The available channels:

| Goal | Mechanism |
|---|---|
| Message to the **user** | `systemMessage` in JSON on stdout, exit 0 |
| Message to **Claude** | `additionalContext` in JSON on stdout, exit 0 |
| Message to **Claude** from PostToolUse, non-blocking-in-practice | exit 2 (tool already ran) |
| Transcript notice + first stderr line | any non-zero exit other than 2 |

Note the awkwardness this creates for the guide's tidy binary: from a
PostToolUse hook the docs actively recommend exit 2 to warn, which collapses
the "2 means block" framing. That is worth teaching rather than smoothing over
— exit 2's meaning is per-event, not universal.

**Suggested correction.** Fix the exit-code table; keep §4's principle but
re-express warn-only as `systemMessage`/`additionalContext`; change the two
warn scripts to emit JSON; update `docs/VERIFY.md:60` and the corresponding
`verify_hooks.py` cases so the harness asserts on the JSON rather than on
stderr.

## 3. PostToolUse cannot block

**Claim** — `docs/GUIDE.md:324`:

> ### `validate_review_format.py` — PostToolUse, **hard-block**
> The one PostToolUse hook that blocks, because review structure is
> structural, not heuristic.

And `docs/VERIFY.md:70`: "the only Post hook that blocks."

**Actual behaviour** — the hooks reference's per-event table gives PostToolUse
"Can Block? **No** — Shows stderr to Claude; tool already ran."

**The guide already knows this.** `docs/GUIDE.md:192` says of PostToolUse:
"The write already landed; it can reject the *result* and demand a fix." That
is accurate. Section 5 then contradicts it 130 lines later.

The distinction is not pedantic for a beginner: a malformed `review.md`
**is written to disk** and stays there. The hook makes the agent fix it on a
subsequent write; it does not prevent the bad file existing. Anything reading
`review.md` between the two writes sees the malformed version.

**Suggested correction.** Retitle to "PostToolUse, rejects the result", and
state plainly that the file lands first and the agent is told to correct it.
`docs/VERIFY.md:70` likewise.

**Grounds to challenge.** If "hard-block" was intended as shorthand for
"non-negotiable, unlike the warn hooks" rather than as a claim about
mechanism, say so — but then it needs different wording, because it sits in a
section whose whole subject is the Pre/Post mechanism.

## 4. SubagentStop `decision: "block"` does not stop, and does not talk to the orchestrator

**Claim** — `docs/GUIDE.md:339-341`:

> Mechanises *"if an agent fails to write its file, report the failure and
> stop."*

And the script's own docstring, `scripts/check_subagent_output.py:17-21`:

> Returning `{"decision": "block", "reason": "..."}` tells the orchestrator the
> subagent stopped without producing output and passes a message back

**Actual behaviour** — from the SubagentStop section of the hooks reference:

> Returning `decision: "block"` with a `reason` **keeps the subagent running**
> and delivers `reason` to the **subagent** as its next instruction. To inject
> context into the parent session after a subagent returns, use a `PostToolUse`
> hook on the `Agent` tool instead.

Two things are inverted:

1. It is a *keep going and fix it* signal, not a stop signal. The pipeline rule
   being mechanised is "report the failure and stop" — this does close to the
   opposite. In practice that may be the better behaviour (the subagent gets a
   chance to write the file it forgot), but the guide should say what actually
   happens.
2. The `reason` goes to the **subagent**, not the orchestrator. The current
   reason text is addressed to the wrong reader: *"Re-run the agent or report
   the failure and stop, as the pipeline rules require"* is an instruction to
   the orchestrator, delivered to the agent that just finished.

**Suggested correction.** Rewrite the `reason` string as an instruction to the
subagent ("You finished without writing any .md file in `docs/N`. Write your
output file now."); correct `docs/GUIDE.md:339-341` and the docstring; note the
`PostToolUse`-on-`Agent` alternative for reaching the parent, which is a good
teaching contrast between the two channels.

The honesty in `:346-350` about the hook being deliberately coarse is good and
should stay — it is just attached to a wrong description of the mechanism.

## 5. "The two events used here" heads a three-row table

`docs/GUIDE.md:187` — the table below it lists PreToolUse, PostToolUse and
SubagentStop.

The SubagentStop row (`:193`) puts "Not tool-scoped at all — agent-scoped" in
the **"Can it block?"** column, so the column's question goes unanswered. The
answer is yes: SubagentStop exit 2 prevents the subagent from stopping. It also
*does* support matchers — they filter on agent type (`general-purpose`,
`Explore`, or a custom agent's frontmatter `name`) rather than on tool name.
"Not tool-scoped" is right; "no matcher" would be wrong, and the phrasing
invites that reading.

Suggest: retitle to "The three events used here", answer the block question in
its own column, and move the agent-type matcher note into the prose — it is a
genuinely useful contrast with tool-name matchers.

## 6. "Six scripts"

`docs/GUIDE.md:7` says "four agents, one skill, six scripts"; `:267` heads the
section "## 5. The six scripts" and then lists seven. `scripts/` contains eight
files (the seven plus `verify_hooks.py`).

Presumably "six hooks, plus `iteration.py` which is not one". The section is
already careful to mark `iteration.py` as *(not a hook)*, so the fix is just to
make the count match: "six hook scripts plus a folder-management script."

## 7. Workspace trust is never mentioned

Not an error, but the most likely thing to make a beginner's copy of this
pattern silently do nothing.

From the hooks reference: frontmatter hooks in a project subagent run only
after the workspace trust dialog is accepted for the folder the agent file came
from. The skills reference says the same for a project skill's `allowed-tools`.

Someone who clones this repo, runs `/design-cycle`, declines or never sees the
trust dialog, and watches every guard fail to fire has no way to diagnose it
from `docs/GUIDE.md` or `docs/VERIFY.md`. Worth one paragraph in §4 and one
line in VERIFY's troubleshooting.

## 8. `HANDOFF.md` contradicts itself about the live run

- `:37` — "`docs/1/` .. `docs/4/` — a recorded live run that hit the iteration
  cap without converging."
- `:48` — "Nothing has been run end-to-end against a real brief yet. The
  scripts are unit-tested; the pipeline itself has not been exercised live."

`docs/VERIFY.md`'s "Results from the recorded run" and "What a manual run does
not prove" sections resolve this correctly and with more care than either
bullet: a run happened, it was driven manually step by step, and therefore the
skill-level hooks never fired. `:48` reads as a stale note from before the run.

Suggest replacing `:48` with VERIFY's framing: the pipeline has been exercised
manually; it has never been exercised through the skill, so no hook has been
observed firing automatically.

## 9. `docs/README.md` describes a different run

`docs/README.md:8-18` shows a three-iteration tree ending in
`review.md   Verdict: APPROVED` and `backlog.md`. The committed run is four
iterations, capped, no approval and no backlog. `:25` — "`backlog.md` appears
only in the folder whose review was approved" — is then describing a file that
does not exist in this repo.

This predates the branch, so it may be deliberately illustrative. If so, one
line saying "illustrative — the committed run under `docs/1`–`docs/4` did not
converge" would stop a beginner going looking for `backlog.md`.

## The pattern behind 1–4

All four errors share a cause worth naming, because it is itself a good lesson.

The three verification levels in `docs/VERIFY.md` are:

1. `pytest` — feeds each script a crafted payload, asserts its output.
2. `verify_hooks.py` — feeds each script a crafted payload, prints and asserts
   its output.
3. The manual run — drives the agents by hand, which
   `docs/VERIFY.md:233-236` correctly notes means the skill-level hooks never
   fire at all.

Every level exercises **the script**. No level exercises **the harness
contract** — what Claude Code does with an exit code, where stderr goes,
whether a `decision` field means stop or continue, what `allowed-tools` grants.
That contract is precisely where all four errors live.

`docs/VERIFY.md:237-241` half-sees this: *"No hook has been observed blocking a
live agent mid-run […] The scripts are proven; 'a hook automatically stops a
misbehaving agent' is not."* That is exactly right, and it is a bigger
admission than its placement suggests — it applies to the guide's *claims*, not
just to the demo's coverage. The verification cannot catch a documentation
error about harness semantics, because it never invokes the harness.

Two ways to close it, either of which would be a stronger teaching artifact
than the current level 3:

- **Cheap:** a `docs/GUIDE.md` convention of citing the reference doc next to
  each behavioural claim, so a reader can check a claim without running
  anything, and a future editor can re-verify against a newer doc.
- **Real:** one genuine skill-driven run with `--debug` on, with a deliberately
  misbehaving agent, capturing an actual block in the transcript. That single
  artifact would have caught 2, 3 and 4.

## Suggested disposition format

Same convention the pipeline uses on itself — for each item: **Accepted**,
**Rejected** (with reasoning), or **Deferred**. Items 1–4 are the ones where a
rejection would be genuinely informative, since they turn on doc-versus-observed
behaviour and observed behaviour wins.
