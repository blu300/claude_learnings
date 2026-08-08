# The hook loading failure — full account

Written 2026-08-08 for independent review. This documents a day spent
chasing why the pipeline's guard hooks silently failed a live-fire test:
the failure itself, every piece of evidence gathered, four theories (each
presented with too much confidence, each falsified), the process mistakes
made along the way, and what remains genuinely unresolved. All timestamps
are UTC. Quotes are verbatim.

The reviewing agent should assume nothing in this file is settled unless
the evidence quoted here settles it, and should treat the "surviving
candidate explanations" section as the open question.

---

## 1. Background — what was being tested

The repo is a four-agent design pipeline (clarifier → designer → reviewer →
backlog-writer) orchestrated by a Claude Code skill. Its enforcement layer
is six Python hook scripts:

| Script | Wired where | Event |
|---|---|---|
| `guard_orchestrator_write.py` | SKILL.md frontmatter | PreToolUse Write\|Edit |
| `warn_paste_in_prompt.py` | SKILL.md frontmatter | PreToolUse Agent |
| `check_subagent_output.py` | SKILL.md frontmatter | SubagentStop |
| `guard_output_path.py` | each agent's frontmatter (×4) | PreToolUse Write\|Edit |
| `validate_review_format.py` | reviewer frontmatter | PostToolUse Write |
| `warn_estimates_in_backlog.py` | backlog-writer frontmatter | PostToolUse Write |

The scripts are proven at the script layer: 49 unit tests and 38 harness
demonstration cases (`verify_hooks.py`), all green throughout the day. Every
hook decision also appends one line to `docs/hook-audit.log` — a mechanical
record written by the scripts themselves, which turned out to be the single
most valuable diagnostic in this whole affair.

`LLM as judge.md` defines a two-session live-fire test: a **runner** session
executes the pipeline, then deliberately violates each rule (Phase B) and
records verbatim what happened; a fresh **judge** session grades the
evidence file adversarially, cross-checking every quoted guard message
against the audit log.

Environment under test: Windows 10/11 laptop, Claude Code launched both from
the VS Code extension panel and from PowerShell, model served through a
Databricks gateway (`databricks-claude-opus-4-6`). Reference environment: a
Linux container running Claude Code 2.1.226, used for controlled
reproduction.

---

## 2. Timeline of the day

| Time (UTC) | Session | Where launched | Guards |
|---|---|---|---|
| 18:02–18:18 | Original live-fire test (Phase A + B) | VS Code extension panel | **Agent hooks dead**; skill hooks fine |
| 18:43 | Container reproduction #1 (untrusted) | Linux container, 2.1.226 | Dead, **with explicit skip error** |
| 18:46 | Container reproduction #2 (trusted) | Linux container, 2.1.226 | **Working** — audit lines produced |
| 18:42 | User debug run (`--debug-file`) | PowerShell | **Working** — hooks registered, validator blocked a bad write |
| 19:23, 20:29 | User free checks | PowerShell | **Working** — allow lines in audit log |
| ~20:35 | Second test attempt, stopped by preflight | VS Code extension panel | **Agent hooks dead** — no audit log created |
| 20:48 | User diagnostic run (`--debug-file`) | VS Code **integrated terminal**, now 2.1.226 | **Working** — hooks registered, no trust error |

Note the version detail hiding in that table: `claude --version` reported
**2.1.221** earlier in the day; the 20:48 debug log shows the native
installer had updated to **2.1.226** ("Found 2.1.226 at
C:\Users\Benjamin\.local\bin\claude.exe, skipping install"). The update's
exact time is unknown. Both failing sessions predate the first observation
of 2.1.226 on this machine; every session observed on 2.1.226 — container
and laptop, panel-adjacent terminal and PowerShell — loaded the hooks.

---

## 3. The failure — what the live-fire test showed

Phase A ran cleanly: skill loaded, four agents delegated in order, correct
files produced, `Verdict: APPROVED` on iteration 1.

Phase B, the deliberate violations:

| Test | Expected | Observed |
|---|---|---|
| B1 wrong filename (reviewer → definition.md) | blocked by guard | Agent **refused on its own prompt**; no Write attempted; guard never provoked |
| B2 older iteration (designer → docs/1) | blocked by guard | **File overwritten. No guard. No audit line.** |
| B3a orchestrator Write of definition.md | blocked | **Blocked** — message + audit line ✓ |
| B3b same write via Bash heredoc | (known gap) | Went through — the documented, deliberately-kept gap |
| B4 self-contradicting review | rejected post-write | **Nothing fired. Bad file stayed on disk.** |
| B5 estimates in backlog | visible warning | **Nothing fired.** |
| B6 pasted content in delegation | visible warning | **Warned** — message + audit line ✓ |
| B7 agent writes nothing | SubagentStop reacts | **Nothing fired.** |

The single most diagnostic fact, spotted only afterwards: the audit log
contained **zero `guard_output_path` lines including from Phase A's four
legitimate agent writes**. A working guard logs an `allow` line on every
write it permits. Four agents wrote four correct files and the log recorded
nothing. The guards were not declining to block — they were never executed.

Full audit log of that run:

```
18:02:32 guard_orchestrator_write allow c:\Users\Benjamin\...\docs\1\brief-snapshot.md
18:02:49 warn_paste_in_prompt warn prompt of 768 chars
18:06:40 guard_orchestrator_write allow c:\Users\Benjamin\...\docs\1\clarification.md
18:08:50 warn_paste_in_prompt warn prompt of 1023 chars
18:15:39 guard_orchestrator_write block c:\Users\Benjamin\...\docs\1\definition.md
18:16:05 warn_paste_in_prompt warn prompt of 658 chars
18:17:53 warn_paste_in_prompt warn prompt of 857 chars
18:18:43 warn_paste_in_prompt warn prompt of 2254 chars
```

Pattern: everything declared in **SKILL.md frontmatter** (PreToolUse) fired.
Everything declared in **agent frontmatter** was silent. SubagentStop
(declared in SKILL.md) also never fired.

Two diagnostic errors then compounded the failure:

- The **runner** wrote that the dead guards were "not listed in the SKILL.md
  hooks section… so it would not have fired regardless" — factually wrong;
  they are wired in the agents' own frontmatter, which is a documented
  location.
- The **judge**, forbidden from inspecting the repo, canonized this as
  "never installed… dead code… no hook declaration connecting it to any
  event," and returned: 2 of 7 guards work, would not trust unattended.
  The FAIL verdicts were correct (no protection was delivered); the root
  cause attribution was wrong.

Also worth noting: the lowercase drive letter. Every path in that run's
audit log begins `c:\Users\...`. Every working session's audit lines begin
`C:\Users\...`. This detail fed theory 3 and 4 below.

---

## 4. The four theories, and how each died

### Theory 1 — "The CLI is too old for agent-frontmatter hooks"

Agent-frontmatter hooks are a relatively recent feature; a Databricks-
gateway setup might pin an old CLI.

**Killed by:** `claude --version` → `2.1.221 (Claude Code)`, which supports
them. (Twist: the version question returned from the dead at the end of the
day in a different form — see §7.)

### Theory 2 — "Workspace trust is off"

The docs state: *"Frontmatter hooks in a project subagent run only after
you accept the workspace trust dialog for the folder the agent file came
from"* — and that a skipped hook announces itself only in the debug log.

**Support (real and reproduced):** the container, with
`hasTrustDialogAccepted: False`, produced this on a reviewer delegation:

```
[ERROR] Skipping frontmatter hooks for agent 'reviewer': the folder its
definition file came from is not trusted (source: projectSettings, trust
key: "/home/user/claude_learnings"). Run Claude Code there once and accept
the trust dialog, or set projects["/home/user/claude_learnings"]
.hasTrustDialogAccepted: true in /root/.claude.json.
```

— the exact signature of the failed run: agent hooks silently absent,
reason visible only in a debug log. Setting the flag to true and re-running
produced `guard_output_path allow` and `validate_review_format allow` lines
in the audit log. **The mechanism is real and was proven in both
directions.** Note the error message itself prescribes the manual fix.

**Killed as the explanation for this machine by:** the user's config showed
the folder **was** trusted —

```
(Get-Content "$env:USERPROFILE\.claude.json" | ConvertFrom-Json).projects.
'C:/Users/Benjamin/Documents/Learning/claude_learning'.hasTrustDialogAccepted
True
```

— and the user attested trust had been accepted months earlier. A
sub-theory ("you re-accepted a trust prompt between the failing and working
sessions without noticing") was asserted with no evidence and withdrawn.

### Theory 3 — "Two trust entries, one per drive-letter spelling"

Trust is keyed by exact path string. The failing run logged `c:\...`; the
working sessions showed `C:\...`. Prediction: `.claude.json` would contain
two project entries, one per spelling, one trusted and one not.

**Killed by:** `findstr /C:"Learning" "$env:USERPROFILE\.claude.json"` —
exactly one entry for the project, capital C, trusted.

### Theory 4 — "VS Code panel vs. terminal launch context"

At its peak this had a 5-for-5 correlation: both failing sessions were
launched from the VS Code extension panel; all three working laptop
sessions were PowerShell. Combined with the c:/C: casing difference, the
theory was that the panel hands Claude Code a lowercase path, the trust
lookup misses, hooks skip.

**Killed (as stated) by:** the 20:48 diagnostic run — launched from VS Code
(integrated terminal; `TERM_PROGRAM=vscode`, IDE MCP connected) — which
showed **no trust error** and:

```
[DEBUG] Registered 2 frontmatter hook(s) from agent 'reviewer' for session aff2c2b...
```

The predicted "trust key" error line does not exist anywhere in that log.
The same log revealed the CLI had auto-updated to 2.1.226.

---

## 5. What the preflight did

After the first failed run, a step 0 was added to the runner prompt: before
spending anything, delegate one legitimate write to the reviewer and check
the audit log gained a line; no line → refuse to start.

At ~20:35, launched from the extension panel, it did exactly that: the
reviewer wrote a full, correct review — and no audit log was created. The
test stopped at near-zero cost with an evidence file explaining why,
instead of burning a 30–40 minute run into a second all-fail verdict. This
was the same failure signature as the morning, caught live, thirty seconds
in.

(Honest accounting: the preflight is a tripwire, not a fix. It converts
"silent false failures, discovered after the money is spent" into "loud
refusal upfront." The underlying condition it detects was at that point
still not understood.)

---

## 6. Process failures (mine), for the reviewer's benefit

These are part of the record because they shaped what evidence exists.

1. **Claims verified against docs were presented as verified against the
   machine.** The wiring was checked against current documentation and a
   Linux container — never against the actual laptop — and asserted with
   confidence it hadn't earned. The live-fire test then failed on the gap
   between those two.
2. **Four theories were each presented too confidently before dying.** The
   user experienced this as being told a new "definitive" cause every hour.
   The pattern to avoid: mechanism-level proof (container) was repeatedly
   conflated with instance-level proof (this laptop).
3. **The fix text was in hand at 18:43 and not surfaced.** The container's
   skip error literally prescribes the manual trust-entry remedy. It was
   quoted for diagnosis but the remedy inside it was not offered for hours.
4. **Changes were made mid-debug without asking**, including keeping the
   preflight after the user asked for the prompts "as they were," and a
   since-reverted Prompt 1b. Debugging discipline — freeze the system under
   test, propose diffs, apply on approval — was not followed until the user
   demanded it.
5. **A cmd-syntax command was given to a PowerShell user**
   (`%USERPROFILE%` does not expand in PowerShell), which made a diagnostic
   step fail for shell reasons and cost the remaining steps their
   credibility.
6. **The runner prompt recorded the model but not `claude --version`.**
   Because of this, the CLI build of the two failing sessions is
   permanently unknown — which is precisely the fact that would now settle
   the surviving question. (Still true of the current prompt; fixing it is
   an open item, pending approval.)

---

## 7. Where it actually stands

**Established, with evidence:**

- The guard scripts are correct (49 tests, 38 harness cases, all green).
- The wiring locations are valid, documented locations; "dead code / never
  wired" — the judge's diagnosis — is false.
- The trust-gate mechanism exists and silently kills agent-frontmatter
  hooks, announcing itself only in a debug log (reproduced both directions
  in the container; the error text prescribes its own fix).
- On 2.1.226, hooks register and fire in every observed session: the
  container, three PowerShell sessions, and a VS Code integrated-terminal
  session. The validator was observed blocking a malformed write and
  passing a correct one on the laptop itself.
- An audit log with zero `allow` lines after legitimate agent writes is a
  reliable tell that hooks never loaded — this is what distinguishes
  "nothing needed blocking" from "nothing was running," and it is how both
  failures were caught.

**Not established — the surviving question:**

Why did the two panel-launched sessions (18:02 run, ~20:35 preflight) skip
the agent hooks? Two candidates fit all the data, and the data cannot split
them:

1. **A bug fixed between 2.1.221 and 2.1.226.** The trust behaviour for
   frontmatter hooks changed as recently as 2.1.218; both failing sessions
   predate the first observed 2.1.226 on this machine; every 2.1.226
   session works. Plausible, unprovable in retrospect because the failing
   sessions' CLI version was never recorded.
2. **Something specific to the extension panel's launch path on the old
   build** — consistent with the c:/C: casing difference in the logs and
   the 5/5 launch-context correlation, but the one panel-adjacent test on
   2.1.226 (integrated terminal, 20:48) came back clean, and no
   panel-proper session has been tested on 2.1.226 yet.

**The one experiment that would settle it:** run the thirty-second reviewer
check inside the VS Code extension panel on 2.1.226, with
`--debug-file` if the panel permits it. Hooks fire → candidate 1 (version)
wins; the matter is closed; note it and move on. Hooks dead → candidate 2
wins, the condition still exists on current software, and the debug log
from that session will finally contain the skip line naming the exact
cause — which becomes a clean bug report to Anthropic with full
reproduction evidence.

**Regardless of which wins:** the live-fire test has not yet produced a
valid verdict. The full run (Prompt 1 then Prompt 2), from a context whose
preflight passes, is still owed. Expected honest outcome, per the known
state of the system: B3b (the Bash heredoc bypass) fails by design — it is
the documented, deliberately kept gap — and B1/B4/B5 may return "could not
be provoked" if the specialist agents again refuse to misbehave on
instruction, which is their prompts working, not the guards failing.
