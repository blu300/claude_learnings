---
name: design-cycle
description: Runs the clarify, design, review and backlog pipeline. Takes a brief, questions it, loops design and review until the review is clean, then produces a backlog.
argument-hint: [path-to-brief]
disable-model-invocation: true
allowed-tools: Bash(python3 scripts/iteration.py *) Bash(echo *) Read Edit
hooks:
  PreToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/guard_orchestrator_write.py"'
    - matcher: "Agent"
      hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/warn_paste_in_prompt.py"'
  SubagentStop:
    - hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/check_subagent_output.py"'
---

# Design cycle

You are the orchestrator. You run in the main session so that you can put
questions to the human; delegated agents cannot ask questions, they can only
write them to a file for you to relay.

Brief: $ARGUMENTS

## Existing iteration folders

!`python3 scripts/iteration.py list 2>/dev/null || echo "(none yet)"`

## Rules that apply throughout

- Never paste file contents into a delegation prompt. Pass file paths only.
  The agents read and write files themselves; you route paths between them.
- Never write `definition.md`, `review.md` or `backlog.md` — those belong to
  the agents. The only files you write are the **Answers** section of
  `clarification.md`, `docs/1/brief-snapshot.md`, and
  `docs/.current_iteration`. A hook enforces this; anything else is refused.
  If an agent fails to write its file, report the failure and stop.
- Keep your own reading to a minimum. You may read exactly these: the
  questions from `clarification.md`, `dispositions.md`, and the `Verdict:`
  line plus any `Questions for human` section from each `review.md`. You
  never read `definition.md`. Reading the design would make you a second
  reviewer with none of the reviewer's discipline.
- `clarification.md` lives in `docs/1` only, and is carried forward to every
  later iteration. It is the single record of everything the human has told
  you.
- Stop after 4 design iterations even if the review is still not clean.

## Procedure

### Clarify

1. Create the first iteration folder:
   `python3 scripts/iteration.py next --max 4` — it prints the folder path,
   e.g. `docs/1`. The `--max 4` gate makes the iteration cap a hard stop the
   orchestrator cannot override: once four folders exist, the command exits
   non-zero instead of creating a fifth. Call this folder `<dir>`, and
   remember `<dir>/clarification.md` as the clarification path for the whole
   run.

   After creating `docs/1`, copy the brief to `docs/1/brief-snapshot.md`.
   From this point forward, "the brief" means the snapshot path, not the
   original — every agent receives the snapshot. This freezes the brief at
   the moment the pipeline started, so a later edit to the original file
   cannot silently change what the agents were working from mid-run.

   Before each delegation, record which iteration is active so the write
   guards can scope their checks: `echo <n> > docs/.current_iteration`
   (where `<n>` is the current folder number). Do this every time you set or
   change `<dir>`.

2. Delegate to the `clarifier` agent. Give it the brief path and tell it to
   write `<dir>/clarification.md`.

3. Read that file. Put its assumptions and questions to the human in your
   reply, in the clarifier's own words. Ask the blocking questions first and
   say plainly that the useful ones can be skipped.

4. Wait for the human. When they reply, write their answers into the
   **Answers** section of `<dir>/clarification.md`, numbered to match the
   questions. Record unanswered questions as unanswered rather than
   guessing — the designer needs to know which assumptions still stand.

   When a new answer contradicts one already in the file (this happens when a
   later reply supersedes an earlier one), do not overwrite the old answer.
   Strike it through with `~~old answer~~` and add `**Superseded by #<n>**`,
   then write the new answer as entry `<n>`. The designer must see both the
   original assumption and its correction, and the link between them.

### Design and review

5. Delegate to the `designer` agent. Tell it:
   - the brief path,
   - the clarification path,
   - the review file from the previous iteration, if there is one,
   - that it must write its output to `<dir>/definition.md`.

   On iterations after the first, resume the same designer instance rather
   than spawning a fresh one, so it keeps the reasoning behind its earlier
   choices.

6. Delegate to the `reviewer` agent. Tell it to read `<dir>/definition.md`,
   the brief and the clarification path, and to write `<dir>/review.md`. If
   any `dispositions.md` files exist from this or earlier iterations, pass all
   their paths too, so the reviewer does not re-raise findings the designer
   already rejected with sound reasoning. Always spawn a fresh reviewer —
   never resume one — so each review starts cold.

7. Read the `Verdict:` line of `<dir>/review.md` and act on it:

   - **`Verdict: QUESTIONS`** — stop the loop. Put the questions to the human,
     in the reviewer's own words, and wait. When they reply, append the
     answers to the **Answers** section of the clarification file, then create
     the next folder, set `<dir>` to it, and go to step 5.

   - **`Verdict: CHANGES REQUESTED`** — create the next folder with
     `python3 scripts/iteration.py next --max 4`, set `<dir>` to it, and go
     back to step 5, passing the previous iteration's `review.md` path. If the
     command exits non-zero, the cap is reached: stop and report the design
     did not converge within four iterations.

   - **`Verdict: APPROVED`** — go to step 8.

### Backlog

8. Delegate to the `backlog-writer` agent. Tell it to read the approved
   `<dir>/definition.md` and write `<dir>/backlog.md`.

9. Read the final iteration's `dispositions.md`, if it exists. Report to the
   human: the number of iterations, the paths to the approved definition and
   the backlog, and any findings the designer accepted rather than resolved
   (the **Accepted** section of that file). The dispositions log is where you
   get this — you still do not read the design to find it.

## When you stop

Report plainly. Do not summarise the design or the backlog back to the human
— they can open the files. Say what happened and where the output is.