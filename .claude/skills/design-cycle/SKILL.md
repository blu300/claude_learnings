---
name: design-cycle
description: Runs the clarify, design, review and backlog pipeline. Takes a brief, questions it, loops design and review until the review is clean, then produces a backlog.
argument-hint: [path-to-brief]
disable-model-invocation: true
allowed-tools: Bash(python3 scripts/iteration.py *) Read Edit
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

You are the orchestrator. You run in the main session and you are the one
who talks to the human. The specialist agents have no question-asking tool —
deliberately, so that every question travels through a file for you to relay
and the whole exchange stays on the record.

Brief: $ARGUMENTS

## Existing iteration folders

!`python3 scripts/iteration.py list 2>/dev/null || echo "(none yet)"`

## Rules that apply throughout

- Never paste file contents into a delegation prompt. Pass file paths only.
  The agents read and write files themselves; you route paths between them.
- Never write `definition.md`, `review.md` or `backlog.md` — those belong to
  the agents. The only files you write are the **Answers** section of
  `docs/1/clarification.md` and `docs/1/brief-snapshot.md`. A hook enforces
  this; anything else is refused. (`docs/.current_iteration` is written by
  `scripts/iteration.py` itself — you never touch it.) If an agent fails to
  write its file, report the failure and stop.
- Keep your own reading to a minimum. You may read exactly these: the
  questions from `clarification.md`, `dispositions.md`, and the `Verdict:`
  line plus any `Questions for human` section from each `review.md`. You
  never read `definition.md`. Reading the design would make you a second
  reviewer with none of the reviewer's discipline.
- `clarification.md` lives in `docs/1` only, and is carried forward to every
  later iteration. It is the single record of everything the human has told
  you.
- The iteration cap is 4, and it lives in `scripts/iteration.py` itself —
  when `next` refuses to create a folder, the run is over. Stop and report.

## Procedure

### Clarify

1. Create the first iteration folder:
   `python3 scripts/iteration.py next` — it prints the folder path, e.g.
   `docs/1`. The iteration cap (4) is built into the script: once four
   folders exist, the command exits non-zero instead of creating a fifth,
   and you cannot raise the cap from the command line. The script also
   records the new folder in `docs/.current_iteration`, which is how the
   write guards know which round is active — you never write that file.
   Call this folder `<dir>`, and remember `<dir>/clarification.md` as the
   clarification path for the whole run.

   After creating `docs/1`, copy the brief to `docs/1/brief-snapshot.md`.
   From this point forward, "the brief" means the snapshot path, not the
   original — every agent receives the snapshot. This freezes the brief at
   the moment the pipeline started, so a later edit to the original file
   cannot silently change what the agents were working from mid-run.

2. Delegate to the `clarifier` agent. Give it the brief path and tell it to
   write `<dir>/clarification.md`.

3. Read that file. Present its **assumptions** in your reply, in the
   clarifier's own words — the human needs to see what will be invented
   unless they object. Then put the questions to the human in two forms:

   - **Blocking questions** go through the AskUserQuestion tool, in the
     clarifier's own words, at most four per call. Use the concrete
     choices the clarifier phrased inside each question as the selectable
     options; the tool provides its own "Other" for free text, so do not
     add one. A blocking question with no sensible preset choices is
     asked in the text reply instead, alongside the useful ones.
   - **Useful questions** follow in your reply as one numbered list. Say
     plainly that they can be skipped — singly or wholesale — and
     answered together in a single reply.

4. When the answers are in — clicked or typed — write them into the
   **Answers** section of `<dir>/clarification.md`, numbered to match the
   questions. Record skipped and unanswered questions as unanswered rather
   than guessing — the designer needs to know which assumptions still
   stand.

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
     answers to the **Answers** section of the clarification file, then go
     back to step 5 **in the same folder** — do not create a new one. The
     design was not judged wrong; it could not be judged at all, so the round
     is redone in place with the new answers rather than spending one of the
     four iterations. The designer and reviewer overwrite their files in
     `<dir>` (the questions themselves live on in the clarification file).

   - **`Verdict: CHANGES REQUESTED`** — create the next folder with
     `python3 scripts/iteration.py next`, set `<dir>` to it, and go back to
     step 5, passing the previous iteration's `review.md` path. If the
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