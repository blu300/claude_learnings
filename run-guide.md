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

(The completed run committed under `docs/example-run/` is a specimen to
*read* — it lives outside the numbered range, so it doesn't count against
the iteration cap and you can run the pipeline without touching it. If an
earlier attempt left `docs/1`, `docs/2`, … or a `docs/.current_iteration`
cursor behind, clear those first:
`Remove-Item docs\1, docs\2, docs\3, docs\4 -Recurse -ErrorAction SilentlyContinue`
and `Remove-Item docs\.current_iteration -ErrorAction SilentlyContinue`.)

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
   orchestrator: the blocking ones arrive one panel at a time with
   clickable choices (pick one, or use "Other" to type your own), and the
   useful-but-skippable ones follow as a numbered list you can answer in
   one reply or ignore. After that the design–review loop runs on its own: each round lands in a numbered
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

### Afterwards

Your run's output in `docs/1`, `docs/2`, … is transient and untracked by
git — read it, keep it, or clear it out:

```powershell
Remove-Item docs\1, docs\2, docs\3, docs\4 -Recurse -ErrorAction SilentlyContinue
Remove-Item docs\.current_iteration, docs\hook-audit.log -ErrorAction SilentlyContinue
```

The committed specimen in `docs/example-run/` stays where it is — that
one belongs to the repo, not to your run.

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

How the log actually gets written — no logger process, one shared
function, every line of its code explained — is its own short read:
[`docs/learning/audit.md`](docs/learning/audit.md).

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

2. Is this folder **trusted**? The first time you open a folder, Claude
   Code asks "do you trust the files in this folder?" — and hooks
   declared inside the project only load after you've said yes. Decline
   it (or never see it) and every guard here is skipped *silently*: no
   error, no message, nothing. Check what's actually recorded — Claude
   Code keeps its answer per folder in a file called `.claude.json` in
   your home directory:

   ```powershell
   $cfg = Get-Content "$env:USERPROFILE\.claude.json" -Raw | ConvertFrom-Json
   $cfg.projects.PSObject.Properties.Name |
     Where-Object { $_ -match '(?i)claude_learning' } |
     ForEach-Object { "$_  ->  trusted: $($cfg.projects.$_.hasTrustDialogAccepted)" }
   ```

   Reading the output:
   - `trusted: True` → trust is fine; move on to item 3.
   - `trusted: False`, or no line at all → run `claude` in the project
     folder once, accept the trust dialog, and re-test.
   - **Two lines that differ only in the drive letter's case**
     (`C:/...` and `c:/...`) → you are looking at the panel bug from
     item 3; note which one says `True`.

3. Did you launch from the VS Code side panel? On this machine that path
   has silently skipped frontmatter hooks before: the panel hands Claude
   Code the folder as `c:\...` (small c), the trust record says `C:\...`
   (capital C), and the exact-text lookup misses — so a folder you *did*
   trust is treated as untrusted. The full story, the five-minute
   experiment, and the workaround (a second trust entry spelled with the
   small c): `hook_error.md` §8.5. Quick fix meanwhile: launch from
   PowerShell or the VS Code integrated terminal, both proven good.

**A write you meant to make was blocked by "the project docs guard".**
That's `guard_docs_writes` doing its job on `docs/<n>/` files. If you're
doing deliberate maintenance outside a pipeline run, the block message
names the escape: delete the stale `docs\.current_iteration` cursor left
by an aborted run, or make the edit via Bash (the documented gap exists
for exactly this).

**`/design-cycle` refuses immediately.** Four iteration folders
(`docs/1`–`docs/4`) already exist — leftovers from an earlier run hitting
the cap. Clear them (section 2); the specimen in `docs/example-run/` is
not the culprit, it doesn't count.

**A different planning skill takes over instead of the pipeline** (e.g.
superpowers' "writing-plans" starts making specs). Two things are going
on. First, the pipeline can *never* start itself — its skill declares
`disable-model-invocation: true`, so it only runs when you literally type
`/design-cycle <brief>`; asked in plain words to "plan X", Claude picks
from the skills that *are* allowed to volunteer, which means whatever
plugins are installed on your machine. Always start pipeline work with
the slash command. Second, this project's settings now disable the
superpowers plugin inside this repo (`"enabledPlugins": {"superpowers":
false}` in `.claude/settings.json`); if it still appears, run `/plugins`
in a session to check the plugin's exact installed name and adjust that
key to match (e.g. `superpowers@<marketplace-name>`).

**`python3` not recognised in PowerShell.** Use `python` or `py -3`.
The hook commands themselves are fine as-is — they run under Git Bash.

**Junk lines in the audit log after running tests.** Shouldn't happen
anymore (the tests isolate themselves); if you see it, the log is
disposable — delete it and re-run.
