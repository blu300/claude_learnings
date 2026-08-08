# RESOLVED: why the agent hooks didn't fire in the live-fire run

**Root cause: workspace trust.** Agent-frontmatter hooks are silently
skipped when the project folder isn't trusted, with the reason visible only
in the debug log. Both directions were demonstrated on 2026-08-08:

**Untrusted (reproduced in a clean container, CLI 2.1.226):**

```
[ERROR] Skipping frontmatter hooks for agent 'reviewer': the folder its
definition file came from is not trusted (source: projectSettings, trust
key: "..."). Run Claude Code there once and accept the trust dialog, or set
projects["..."].hasTrustDialogAccepted: true in ~/.claude.json.
```

Zero guard lines in `docs/hook-audit.log` — exactly the silence the
live-fire evidence recorded.

**Trusted (both the container and the Windows machine that ran the live
test):**

```
[DEBUG] Registered 2 frontmatter hook(s) from agent 'reviewer' for session ...
```

followed by the guard allowing the correct filename and
`validate_review_format.py` rejecting a malformed review — both decisions
appearing in `docs/hook-audit.log`. The wiring was correct all along; the
scripts were correct all along; the trust state at the time of the
live-fire run was the single point of failure.

## How to check trust (PowerShell — the earlier cmd syntax doesn't expand there)

```powershell
findstr /C:"claude_learning" "$env:USERPROFILE\.claude.json"
```

Open the file and check `hasTrustDialogAccepted` for this project's path.
If `false`: start `claude` in the repo interactively once and accept the
trust dialog.

## The preflight that makes this impossible to hit again

Before any live-fire run (now step 0 of the runner prompt in
`LLM as judge.md`): delegate one legitimate write to the reviewer and check
the audit log gained a line. No line → do not start the test; capture a
debug log (`claude --debug-file hookdebug.txt`) and look for the
`Skipping frontmatter hooks` error above.

## What this replaced

An earlier version of this file was a five-step diagnostic. Steps 4–5
(verbose logging, settings.json probe) were never needed: the debug log
from step 1–2 plus the trust check answered everything. No hooks were moved
to `settings.json` — the frontmatter wiring works once the folder is
trusted, on both platforms tested.
