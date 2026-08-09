# Run guide — how to actually run things

The learning path (README.md) explains *why* everything in this repo
exists. This page is the practical companion: *how* to run each piece,
what you should see, and what to do when you don't see it.

Commands are shown for **PowerShell on Windows** — the machine this repo
is actually tested on. On macOS/Linux the same commands work with the
obvious swaps (`/` for `\`, `rm` for `Remove-Item`, `tail -f` for
`Get-Content -Wait`). One Windows note up front: if `python3` isn't
recognised in PowerShell, use `python` or `py` — inside Claude Code
sessions `python3` works either way, because hooks run under Git Bash.

---

## 1. The two commands that must always be green

```powershell
python -m pytest tests/ -q      # the unit tests
python scripts/verify_hooks.py  # the demonstration harness
```

Both should pass completely — the expected counts are printed in
README.md, and CI runs exactly these two commands on every push. Neither
touches your real `docs/` state; every case builds its own throwaway
folder. Run them whenever you like.

If `pytest` is missing: `pip install pytest`.

The second command is the one worth *reading*, not just running: for
every hook it prints the JSON going in, the exit code coming out, and the
message an agent would see.

---

## 2. Running the pipeline for real (`/design-cycle`)

### Before you start — move the museum piece aside

The repo ships with a completed run committed under `docs/1`–`docs/4` as
a specimen to read. The iteration cap (4) counts *folders*, so with all
four present a fresh run refuses at step one. Park them first:

```powershell
mkdir C:\temp\pipeline-backup -Force
Move-Item docs\1, docs\2, docs\3, docs\4 C:\temp\pipeline-backup\
Remove-Item docs\.current_iteration, docs\hook-audit.log -ErrorAction SilentlyContinue
```

### Run it

1. Start Claude Code **from PowerShell, inside the project folder**:
   `claude`. (Why PowerShell: it's the launch method proven to load the
   guards on this machine — see section 6.)
2. First time on this branch it will ask you to approve the hooks found
   in `.claude/settings.json`. Approve — nothing fires until you do.
3. Write a one-paragraph brief into a file (or use the committed
   `brief.md`), then invoke the skill the way a human is meant to:

   ```
   /design-cycle brief.md
   ```

4. Stay nearby. The clarifier's questions come back to *you* through the
   orchestrator; answer them like a normal user. After that the
   design–review loop runs on its own: each round lands in a numbered
   folder (`docs/1`, `docs/2`, …), and the run ends with an approved
   design and a backlog, or stops at four iterations and says so.

### Watch it work (optional, recommended)

In a **second** PowerShell window:

```powershell
Get-Content docs\hook-audit.log -Wait
```

This prints every hook decision as it happens — guards allowing and
blocking, warnings firing, the flight recorder noting each delegation.
It is the single best way to *see* the machinery this repo teaches.

### Afterwards — put the museum piece back

```powershell
Move-Item C:\temp\pipeline-backup\* docs\
git checkout -- docs/
Remove-Item docs\.current_iteration, docs\hook-audit.log -ErrorAction SilentlyContinue
```

Your own run's folders are yours to keep or delete — but don't commit
them over the specimen.

---

## 3. Testing the flight recorder

The recorder (`scripts/session_log.py`) writes one audit-log line per
session event — session start/end, each delegation, compaction, tool
failures. Here's how to see it work, from the bottom up.

### Step 1 — by hand, no Claude involved

The recorder is just a script that reads one event as JSON and writes one
line. Be the harness yourself for a moment:

```powershell
'{"agent_type": "reviewer"}' | python scripts/session_log.py SubagentStart
Get-Content docs\hook-audit.log
```

You should see one line like:

```
2026-08-09T18:22:04+00:00 session_log SubagentStart agent_type=reviewer
```

JSON in, one line out — that's the whole mechanism. Delete the log before
the live test so it starts clean: `Remove-Item docs\hook-audit.log`.

### Step 2 — live: watch it record a real session

Open two PowerShell windows in the project folder.

- **Window 1:** `claude` (approve the settings hooks if asked).
- **Window 2:** `Get-Content docs\hook-audit.log -Wait`

Before you type anything at all, Window 2 should already show:

```
... session_log SessionStart source=startup
```

That line is the recorder proving the settings-level hooks loaded. **If
it's missing, stop here and read section 6** — nothing else in this test
will work either.

### Step 3 — make events happen, one at a time

In the Claude session, while watching Window 2:

1. **Say anything** ("hello"). When the reply finishes → a
   `session_log Stop` line.
2. **Paste 2000+ characters of anything.** A warning appears on screen
   about pasted content, and a `warn_paste_in_user_prompt warn` line
   lands in the log.
3. **Trigger a delegation.** Ask: *"Use the reviewer agent to read
   README.md and reply with its first line only — write nothing."*
   Expect `SubagentStart agent_type=reviewer`, then `SubagentStop`, plus
   a `check_subagent_output allow` line ("no cursor — nothing to check").
4. **Demonstrate the famous gap.** Ask Claude to run this in Bash:
   `echo 2 > docs/.current_iteration`. No write-guard can see that — it's
   the documented Bash bypass (B3b in the live-fire test) — but a
   `session_log FileChanged` line appears anyway, because the *file
   changing on disk* is visible even when the tool call isn't. Detection
   where prevention isn't available. Clean up in Window 2:
   `Remove-Item docs\.current_iteration`.
5. **Exit the session** (`/exit`) → a final `SessionEnd` line.

### Step 4 — the bonus that matters on this machine

Repeat Step 2 once, launching from the **VS Code side panel** instead of
PowerShell. If the `SessionStart` line appears there too, the
settings-level layer survives panel launches — one of the open questions
from the hook-loading investigation (`hook_error.md` §8.5). Note what you
saw either way.

When you're done: `Remove-Item docs\hook-audit.log`. The log is
deliberately untracked by git — deleting it is always safe.

---

## 4. Reading the audit log

One line per decision, four columns:

```
<utc-timestamp> <script> <decision> <detail>
```

Who writes what:

| Script column | It is | Decisions you'll see |
|---|---|---|
| `guard_output_path`, `guard_orchestrator_write`, `guard_docs_writes` | the write guards | `allow` / `block` |
| `validate_review_format` | the review checker | `allow` / `block` |
| `check_subagent_output` | the did-you-write-your-file check | `allow` / `block` |
| `warn_paste_in_prompt`, `warn_paste_in_user_prompt`, `warn_estimates_in_backlog` | heuristic warnings | `warn` (only when they fire) |
| `session_log` | the flight recorder | the event name, e.g. `SessionStart` |

Three reading rules, all learned the hard way (see the case study):

- **`allow` lines are the proof of life.** A guard that permits a write
  still logs it. Legitimate writes with no `allow` lines mean the guards
  never ran.
- **Warn hooks only log when they warn** — their silence proves nothing.
- **An empty log after a session did real work is itself a finding**, and
  it is bad news: the hooks never loaded. Section 6.

Because some rules run in two layers (agent frontmatter *and*
`.claude/settings.json`), one action can legitimately produce two lines.
Duplicates are normal, not a bug.

---

## 5. The live-fire test

The full "prove the guards fire in a real session" exercise lives in
[`LLM as judge.md`](LLM%20as%20judge.md) — two prompts, a runner and a
judge, ~30–40 minutes, costs real usage. Before spending that, its step 0
preflight runs a thirty-second check that every hook class is actually
loaded, and refuses to start if one isn't — never skip it. Run it from
PowerShell first (the proven-good launch method); the panel-launch
experiment in `hook_error.md` §8.5 is a separate, deliberate exercise.

---

## 6. When something doesn't work

**No audit lines at all, ever.** The hooks aren't loading. In order:
1. Did you approve the hooks when Claude Code asked? (It asks once per
   change to `.claude/settings.json`.)
2. Has this folder's workspace-trust dialog been accepted? Project hooks
   don't load in untrusted folders — silently.
3. Did you launch from the VS Code side panel? On this machine that path
   has silently skipped frontmatter hooks before, due to a
   capital-C/small-c mismatch in the trust lookup. The full story, the
   five-minute experiment, and the workaround: `hook_error.md` §8.5.
   Quick fix meanwhile: launch from PowerShell or the VS Code integrated
   terminal.

**A write you meant to make was blocked by "the project docs guard".**
That's `guard_docs_writes` doing its job on `docs/<n>/` files. If you're
doing deliberate maintenance outside a pipeline run, the block message
names the escape: delete the stale `docs\.current_iteration` cursor left
by an aborted run, or make the edit via Bash (the documented gap exists
for exactly this).

**`/design-cycle` refuses immediately.** All four iteration folders
exist — the committed specimen counts against the cap. Park it first
(section 2).

**`python3` not recognised in PowerShell.** Use `python` or `py -3`.
The hook commands themselves are fine as-is — they run under Git Bash.

**Junk lines in the audit log after running tests.** Shouldn't happen
anymore (the tests isolate themselves); if you see it, the log is
disposable — delete it and re-run.
