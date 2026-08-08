# Dispositions — response to `challenges.md`

Every item in `challenges.md` is dispositioned below. All nine are **Accepted**.

Before writing anything I re-fetched the two reference pages the review cites
(`code.claude.com/docs/en/hooks` and `/skills`, 2026-08-08) and checked each
claim against them rather than taking the review's word for it. The quotes
below are from that fetch, not from the review.

---

## Accepted

### 1. `allowed-tools` is a grant, not a restriction

**Verified.** The skills reference frontmatter table reads: *"Tools Claude can
use without asking permission during the turn that invokes this skill. The
grant clears when you send your next message."* And `disallowed-tools`:
*"Tools removed from Claude's available pool while this skill is active."*

The guide had these exactly backwards. Corrected in `docs/GUIDE.md` §3, and
transferable lesson #1 has been split into two — `tools:` (a real restriction
on subagents) and `allowed-tools:` (a pre-approval on skills) — because
bundling them was what produced the error.

The review's second-order point is also adopted: the grant expiring on the next
user message is a live wrinkle for *this* pipeline specifically, since the
orchestrator is a multi-turn relay that waits for a human. Added as its own
paragraph, contrasting skill-content lifetime with skill-permission lifetime.

### 2. Exit 0 + stderr produces no visible warning

**Verified, and this was the worst of the four.** Hooks reference: *"Stderr
from a hook that exits 0 goes to the debug log only, never the transcript, and
Claude never sees it."*

Both warn-only hooks were therefore **inert** — they printed to stderr, exited
0, and nothing reached anyone. Unit-tested, documented, demonstrated in the
harness, and doing nothing.

Fixed properly rather than just documented:

- `warn_paste_in_prompt.py` and `warn_estimates_in_backlog.py` now emit JSON on
  stdout with **both** `systemMessage` (to the user) and
  `hookSpecificOutput.additionalContext` (to Claude). Two channels, two
  audiences — worth showing both in a teaching repo.
- `tests/test_warn_hooks.py` asserts on the parsed JSON, not stderr.
- `verify_hooks.py` gained an `expect_warning` check that parses stdout.
- The exit-code table in `docs/GUIDE.md` §4 is rewritten, with a channel table
  covering user / Claude / PostToolUse / block.

The review's point that this collapses the tidy "2 means block" framing is
taken and taught rather than smoothed over: at PostToolUse the docs recommend
exit 2 *as the way to warn*, so exit 2's meaning is per-event.

**I checked the new assertion is not vacuous the way the old one was.**
Reverting `warn_paste_in_prompt.py` to the stderr version drops the harness to
29/31 with exit 1. The previous harness passed that same broken hook.

### 3. PostToolUse cannot block

**Verified.** The per-event table gives `PostToolUse | Can block? No | Shows
stderr to Claude; the tool already ran`.

I take no shelter in the offered "grounds to challenge". I meant "hard-block"
mechanically, in a section whose subject is the Pre/Post mechanism, 130 lines
after correctly writing that PostToolUse "already landed". It was a
self-contradiction, not shorthand.

Retitled to "rejects the result" in `docs/GUIDE.md` §5, `docs/VERIFY.md`, the
harness banner and the script's own docstring, each stating plainly that the
malformed file lands on disk and anything reading it in between sees the bad
version.

### 4. SubagentStop `block` does not stop, and does not reach the orchestrator

**Verified.** The per-event table: `SubagentStop | Can block? Yes | Prevents
the subagent from stopping`. Blocking a *stop* means the agent keeps running.

Both errors fixed:

- `docs/GUIDE.md` §5 now says what actually happens, notes that the `reason`
  goes to the subagent, and points at PostToolUse-on-`Agent` as the channel for
  reaching the parent — the contrast the review suggested.
- The `reason` string in `check_subagent_output.py` was addressed to the
  orchestrator ("Re-run the agent or report the failure and stop"), which is
  the wrong reader. It now instructs the subagent: *"You finished without
  writing any .md file in `docs/N`. Write your output file to that folder
  now."*

The docstring is rewritten too, and the test asserts the reason is phrased as
an instruction to the agent.

### 5. "The two events used here" heads a three-row table

**Verified.** Retitled to three, the "Can it block?" column now answers the
question for every row, and the agent-type matcher point is in the prose — it
is a genuinely useful contrast with tool-name matchers, as the review says.

### 6. "Six scripts"

**Verified** — the intro said six, the section listed seven, `scripts/` holds
eight including the harness. Now "six hook scripts and one folder-management
script", section retitled "The seven scripts".

### 7. Workspace trust is never mentioned

**Accepted.** This is the one most likely to make a beginner's copy silently do
nothing, and the guide had no way to diagnose it. Added a paragraph in §4 and a
new "Troubleshooting: nothing happens at all" section in `docs/VERIFY.md`
covering trust, manual-run-versus-skill, and looking for stderr that will never
appear.

### 8. `HANDOFF.md` contradicts itself

**Verified** — line 37 described the recorded run, line 48 said nothing had
been run. Line 48 was stale. Replaced with VERIFY's framing: the pipeline has
been exercised manually, never through the skill, so no hook has been observed
firing automatically.

### 9. `docs/README.md` describes a different run

**Accepted.** It predates this work, so it is inherited rather than introduced
— but it is still wrong for a reader who goes looking for `backlog.md`. Marked
explicitly as illustrative, with a note that the committed run capped without
converging.

---

## Rejected

None.

---

## Deferred

None. Every item in `challenges.md` is dispositioned above.

---

## Why full acceptance was appropriate

The pipeline's own designer prompt requires this paragraph when every finding
is accepted, on the grounds that uniform agreement is the shape capitulation
also takes. It applies here.

The honest reason is that items 1–4 are not judgement calls. Each one is a
verbatim line in a reference document that says the opposite of what the guide
said, and I re-fetched those documents myself rather than relying on the
review's quoting. There was nothing to defend. Items 5, 6, 8 and 9 are
arithmetic and internal consistency — equally not matters of opinion.

The place I could have pushed back is item 3, where the review explicitly
offered me an out ("if 'hard-block' was intended as shorthand"). Declining that
out is the more honest call: I used the word in a section explaining the
mechanism, immediately after describing the mechanism correctly.

Where I did exercise independent judgement was on **scope**, not on whether the
findings were right. The review's summary table implies four documentation
edits. Item 2 in fact required changing two scripts, two test files, the
harness, three documents and a regression check — because a documentation error
about how warnings travel meant the warnings had never travelled. Fixing the
prose alone would have left the hooks inert and the guide accurate about a
system that did not work.

---

## What actually caused all four

The review's diagnosis is the most valuable thing in it, and sharper than my
own "what this does not prove" section:

> Every level exercises **the script**. No level exercises **the harness
> contract**.

That is exactly right. Three verification levels, 38 tests, 31 harness cases,
all green — and none of them could catch a claim about what Claude Code does
with an exit code, because none of them ever invoke Claude Code. Green tests
measure the thing you tested, not the thing you asserted.

Both suggested remedies are adopted in part:

- **Cheap (done):** every behavioural claim in `docs/GUIDE.md` now links the
  reference doc it comes from, with a closing note establishing the tiebreak
  order — observed behaviour beats the docs, the docs beat this guide. Added as
  transferable lesson #13: verify the layer you are making claims about.
- **Real (not done):** a genuine skill-driven run with `--debug`, using a
  deliberately misbehaving agent, capturing an actual block in a transcript.
  The review is right that this single artifact would have caught items 2, 3
  and 4. It is the obvious next piece of work and it is not in this branch.

There is a certain irony in the whole episode worth recording, since this
project exists to stop *"rules that exist in English but not in code"*: two of
its own hooks enforced their rules only in English, and a guide about
mechanical enforcement made four factual errors about the enforcement
mechanism. The spec's word for that is silent degradation.
