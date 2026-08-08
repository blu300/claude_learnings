# Debugging: why didn't the agent hooks fire?

What we already know from the live-fire run — the question is narrow:

| Layer | Status |
|---|---|
| The guard scripts themselves | Proven (49 tests, 38 harness cases) |
| Hooks in **SKILL.md frontmatter** (PreToolUse) | Proven live on this machine — fired, logged |
| Hooks in **agent frontmatter** (all four agents) | Never executed — zero audit lines all run |
| **SubagentStop** from SKILL.md | Never fired |

The docs' only explanation for silently-skipped agent-frontmatter hooks on
v2.1.218+ is workspace trust: *"Frontmatter hooks in a project subagent run
only after you accept the workspace trust dialog for the folder the agent
file came from"* — and a skipped hook says so **only in the debug log**.
These steps confirm or kill that theory, then test the alternative wiring
before anything is migrated.

Run everything from the repo root on the machine that ran the live test.

---

## Step 1 — capture a debug log of one delegation

```
claude --debug-file hookdebug.txt
```

In that session, paste exactly:

```
Use the reviewer subagent to write the single line "test" to docs/1/review.md
```

Let it finish, then exit the session. (`--debug` alone writes to
`~/.claude/debug/<session-id>.txt` and prints nothing — the file flag is
easier.)

## Step 2 — read the log

```
findstr /i "hook" hookdebug.txt
```

Interpret:

- **You see `Hook PreToolUse:Write ...` lines mentioning `guard_output_path`**
  → agent-frontmatter hooks DO run on this machine. The live-fire failure was
  something about that session, not the wiring. Report the lines.
- **No hook lines at all for the reviewer's write** → the frontmatter hooks
  were skipped. Continue to Step 3.

## Step 3 — check workspace trust

Trust is stored per-project in `~/.claude.json`:

```
findstr /C:"claude_learning" "%USERPROFILE%\.claude.json"
```

Open `%USERPROFILE%\.claude.json`, find the entry for this project path, and
look at `hasTrustDialogAccepted`.

- `false` or missing → this is the smoking gun. Start `claude` in the repo,
  accept the trust dialog when it appears, then repeat Steps 1–2.
- `true` → trust is not the explanation. Continue to Step 4.

## Step 4 — verbose matcher detail

More granular logging shows whether the hooks were even *loaded and
considered*:

```
set CLAUDE_CODE_DEBUG_LOG_LEVEL=verbose        (cmd)
$env:CLAUDE_CODE_DEBUG_LOG_LEVEL="verbose"     (PowerShell)
```

Repeat Steps 1–2. Verbose adds hook matcher counts and query matching — if
the reviewer's hooks never appear even at this level, the harness is not
reading the agent frontmatter `hooks:` key at all on this machine.

## Step 5 — test settings.json wiring BEFORE migrating anything

No hooks get moved on faith. This probe proves (or disproves) that a
settings-level hook fires for a subagent's tool call on this machine.

Create `.claude/settings.local.json` (gitignored, local-only) containing:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -c \"open('settings-hook-proof.txt','a').write('fired\\n')\""
          }
        ]
      }
    ]
  }
}
```

Start a fresh `claude` session and repeat the Step 1 delegation. Then:

```
type settings-hook-proof.txt
```

- **File exists with `fired` lines** → settings-level hooks reach subagent
  tool calls here. Migrating the four dead hooks to `.claude/settings.json`
  is now evidence-backed, not doc-backed.
- **No file** → settings wiring doesn't reach subagents on this machine
  either, the docs' claim fails locally, and migration would be pointless —
  the next suspect is the harness build itself (report exactly what Steps
  1–4 showed).

Delete `.claude/settings.local.json` and `settings-hook-proof.txt` when done.

## What to report back

1. The `findstr` output from Step 2 (and Step 4 if reached).
2. The `hasTrustDialogAccepted` value from Step 3.
3. Whether `settings-hook-proof.txt` appeared in Step 5.

Those three facts decide the fix. Nothing gets rewired before they're in.
