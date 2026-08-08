# Design: Pipeline Hardening

Hardens the four-agent design-cycle pipeline against judgement drift, state
loss, and prose-only enforcement. Three phases, ordered by cost and risk.

## Problem

The pipeline works when all agents behave as instructed, but several rules are
enforced only by prose in agent prompts. Agents drift, state falls through
cracks between iterations, and the orchestrator cannot verify what it cannot
read. The result is silent degradation: designs that converge on nothing,
information that vanishes between hops, and rules that exist in English but
not in code.

## Phase 1 — Hook enforcement

Mechanical guards that make violations fail loudly. Structural rules hard-block
(exit 2). Heuristic rules warn-only (print to stderr, exit 0).

### 1.1 Iteration cap

**File:** `scripts/iteration.py`

Add a `--max` argument to the `next` command. When the current highest
iteration equals `--max`, exit 1 and print an error. The orchestrator calls
`python3 scripts/iteration.py next --max 4`.

This replaces the prose rule "stop after 4 design iterations" with a hard
gate that the orchestrator cannot override.

### 1.2 Iteration-scoped write guard

**File:** `scripts/guard_output_path.py`

Accept an optional second positional argument: the iteration number. When
provided, the guard checks that the path is exactly `docs/<that-number>/<filename>`.
When omitted, current behaviour is preserved (any `docs/<n>/<filename>` passes).

This prevents an agent from overwriting a prior iteration's files.

**Mechanism for passing iteration number:** The orchestrator writes the current
iteration number to `docs/.current_iteration` (a single-line file) before each
delegation. The guard reads this file when no second argument is given. This
avoids depending on per-delegation env vars which the agent framework may not
support.

**Hook commands remain unchanged** — the guard gains the fallback internally:

```python
# In guard_output_path.py — when no iteration arg given, read from file
if iteration_arg is None:
    current_file = Path("docs/.current_iteration")
    if current_file.exists():
        iteration_arg = current_file.read_text().strip()
```

**Orchestrator responsibility:** Before each agent delegation, the orchestrator
runs: `echo <n> > docs/.current_iteration` (where `<n>` is the folder number
it just created or is operating in). This is a Write to a non-agent file, so
`guard_orchestrator_write.py` must also allow `docs/.current_iteration`.

### 1.3 Orchestrator write restriction

**New file:** `scripts/guard_orchestrator_write.py`

A PreToolUse hook on the SKILL.md orchestrator for Write and Edit calls.
Allows only paths matching `docs/<n>/clarification.md`. Hard-blocks everything
else.

**Hook declaration** — added to SKILL.md frontmatter (or the equivalent
allowed-tools restriction):

```yaml
hooks:
  PreToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/guard_orchestrator_write.py"'
```

### 1.4 Paste detection (warn-only)

**New file:** `scripts/warn_paste_in_prompt.py`

A PreToolUse hook on the orchestrator's Agent delegation calls. Reads the
prompt from stdin (the tool call JSON), and warns if:

- The prompt exceeds 2000 characters, OR
- The prompt contains 3+ markdown headers (`^#{1,3} `), OR
- The prompt contains a fenced code block (`` ``` ``).

Prints a warning to stderr. Exits 0 (warn-only).

### 1.5 Estimate detection (warn-only)

**New file:** `scripts/warn_estimates_in_backlog.py`

A PostToolUse hook on the backlog-writer agent for Write calls. Reads the
written file and warns if it matches patterns:

- Time units: `\b\d+\s*(hours?|days?|weeks?|points?|sp)\b`
- Estimate headers: `estimate|effort|sizing`

Prints a warning to stderr. Exits 0 (warn-only).

### 1.6 Reviewer verdict format validation

**New file:** `scripts/validate_review_format.py`

A PostToolUse hook on the reviewer for Write calls. Reads the written
`review.md` and hard-blocks (exit 2) if:

- The first line is not one of the three valid verdict strings.
- The structured scoring section is missing (see Phase 3 for format).
- Any dimension lacks an explicit PASS or FAIL.
- The verdict is APPROVED but any dimension is scored FAIL.
- The verdict is CHANGES REQUESTED but all dimensions are scored PASS.

On block, tells the reviewer what failed validation so it can rewrite.

---

## Phase 2 — State loss fixes

Structural changes to how information flows between agents and iterations.

### 2.1 Litigation log (dispositions.md)

**Who writes it:** The designer.

**When:** On every iteration after the first (i.e. whenever the designer
receives a review to respond to).

**File location:** `docs/<n>/dispositions.md` — same iteration folder as the
design it accompanies.

**Format:**

```markdown
# Dispositions — Iteration <n>

Prior iterations: docs/<n-1>/dispositions.md (if exists)

## Accepted
- [Finding from review] — adopted because: <reason>

## Rejected
- [Finding from review] — rejected because: <reason>

## Deferred
- [Finding from review] — cannot address without: <what's missing>
```

**Changes required:**

- `designer.md`: Instruct the designer to write `dispositions.md` alongside
  `definition.md` on revision iterations. Reference the previous iteration's
  dispositions file to maintain continuity.
- `guard_output_path.py` for the designer: The designer's hook runs the guard
  twice — once per allowed filename. Two separate hook entries in `designer.md`:

  ```yaml
  hooks:
    PreToolUse:
      - matcher: "Write|Edit"
        hooks:
          - type: command
            command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/guard_output_path.py" definition.md'
          - type: command
            command: 'python3 "${CLAUDE_PROJECT_DIR}/scripts/guard_output_path.py" dispositions.md'
  ```

  The write passes if *either* guard exits 0. This requires updating the hook
  runner semantics to OR multiple guards (if not already supported), or
  replacing the two hooks with a single invocation that accepts multiple
  filenames as arguments:
  `guard_output_path.py definition.md dispositions.md` — pass if the path
  matches any of the listed filenames. This is the simpler implementation.
- `reviewer.md`: Instruct the reviewer to read `dispositions.md` from the
  current iteration (if it exists) before reviewing. Add: "If a finding was
  previously raised and rejected with reasoning you cannot refute, do not
  re-raise it."
- `SKILL.md`: Pass the dispositions path to the reviewer alongside the design
  and criteria.

### 2.2 Contradiction handling in clarification.md

**Who does it:** The orchestrator.

**When:** When appending answers from a QUESTIONS verdict or from a human reply
that contradicts an earlier answer.

**How:** Before writing a new answer, the orchestrator reads the existing
Answers section. If the new answer contradicts a prior one (the orchestrator
makes this judgement — it's one of the few places its reading is justified):

```markdown
## Answers
1. ~~On-demand only~~ **Superseded by #7**
...
7. [blocking] Batch processing is required for enterprise accounts,
   on-demand for all others.
```

The designer sees both the original (struck) and the replacement, with the
link between them explicit.

### 2.3 Brief snapshot

**When:** At the start of the pipeline, before the clarifier runs.

**What:** The orchestrator copies the brief to `docs/1/brief-snapshot.md`.

**Downstream effect:** All agents receive `docs/1/brief-snapshot.md` as "the
brief path" rather than the original. The original is never referenced again
by any agent.

**Changes required:**

- `SKILL.md` step 2: After creating the first iteration folder, copy the brief.
  All subsequent references to "the brief path" become the snapshot path.
- `guard_orchestrator_write.py`: Also allow writing `docs/1/brief-snapshot.md`
  (once, at pipeline start).

### 2.4 Fix step 9 (orchestrator reporting)

**Problem:** The orchestrator is told to report "anything the reviewer raised
that was accepted rather than fixed" but is also told not to read the design.

**Fix:** The orchestrator reads `dispositions.md` from the final iteration
(not the design). This file explicitly lists accepted/rejected findings. Remove
the contradictory instruction. Update SKILL.md step 9:

```
9. Read <dir>/dispositions.md (if it exists). Report to the human: the number
   of iterations, the paths to the approved definition and the backlog, and
   any findings the designer accepted rather than resolving (from the
   Accepted section of dispositions.md).
```

Update the prose rule in SKILL.md to explicitly state what the orchestrator may
read: `clarification.md` and `dispositions.md` only. The orchestrator still
never reads `definition.md` or `review.md` (beyond the verdict line).

No read-guard hook is added — Claude Code hooks fire on Write/Edit, not Read.
The rule remains prose-enforced for reads, but is now precise rather than
ambiguous.

---

## Phase 3 — Judgement drift mitigations

Prompt changes and structural scoring to reduce inconsistency.

### 3.1 Reviewer rubric and structured scoring

**Changes to `reviewer.md`:**

Add an approval rubric after the "How to review" section:

```markdown
## Scoring

After completing your review, score each dimension:

| Dimension   | Verdict | Finding (if FAIL) |
|-------------|---------|-------------------|
| Coverage    | PASS/FAIL | ... |
| Soundness   | PASS/FAIL | ... |
| Decisions   | PASS/FAIL | ... |
| Gaps        | PASS/FAIL | ... |
| Over-reach  | PASS/FAIL | ... |

Derive your verdict mechanically:
- Any FAIL → `Verdict: CHANGES REQUESTED`
- All PASS → `Verdict: APPROVED`
- Cannot score because criteria are ambiguous → `Verdict: QUESTIONS`

A dimension is FAIL when it has at least one blocking finding. Non-blocking
findings do not cause FAIL.

## Approval threshold

A design is APPROVED when:
- Every criterion from the brief/clarification is addressed (Coverage PASS)
- The approach will work under the stated constraints (Soundness PASS)
- Every significant choice is justified, not merely asserted (Decisions PASS)
- Nothing is left undefined that would block implementation (Gaps PASS)
- Nothing is designed that the criteria did not ask for (Over-reach PASS)

"Addressed" means the design takes a position. It does not mean the position
is perfect.
```

The structured scoring table is validated by the Phase 1 hook
(`validate_review_format.py`).

### 3.2 Clarifier blocking/useful rubric

**Changes to `clarifier.md`:**

Replace "Be sparing" with:

```markdown
## Blocking vs useful

A question is **blocking** when:
- The designer would have to invent an answer, AND
- Getting that invention wrong means rework (not just suboptimality).

Everything else is **useful**. When in doubt, mark it useful — a useful
question the human skips costs nothing; a blocking question the human ignores
stops the pipeline.
```

### 3.3 Designer deference visibility

**Changes to `designer.md`:**

Add after the "Handling review feedback" section:

```markdown
## Self-check on deference

If you accepted every finding from the review (or rejected none), add a
paragraph at the end of the **Changes in this revision** section titled
"Why full acceptance was appropriate" explaining why every point happened to
be correct this time. If you cannot write that paragraph honestly, go back
and find at least one point where your original reasoning was sound and
defend it.
```

This does not mechanically prevent capitulation, but it makes total deference
require an explicit justification — which is visible in `dispositions.md` for
the reviewer and the orchestrator to read.

### 3.4 Backlog granularity heuristic

**Changes to `backlog-writer.md`:**

Add after the decomposition rules:

```markdown
## Story sizing heuristic

A well-sized story is completable in 1–3 working days by one person who knows
the codebase. Use these signals:

- If the tasks under a story span more than 3 files in unrelated parts of the
  system, it is probably two stories.
- If you cannot write concrete acceptance criteria, the story is too vague —
  either break it down or move it to Unallocated with a note on what's missing.
- If the story is a single obvious change (rename, config tweak, one-line
  fix), it should be a task under a broader story, not a story itself.

When you cannot judge size because you lack codebase context, say so in a note
on the story rather than guessing.
```

---

## Components and file inventory

### New files

| File | Purpose | Phase |
|------|---------|-------|
| `scripts/guard_orchestrator_write.py` | Restricts orchestrator to clarification.md | 1 |
| `scripts/warn_paste_in_prompt.py` | Warns on pasted content in delegation | 1 |
| `scripts/warn_estimates_in_backlog.py` | Warns on estimates in backlog output | 1 |
| `scripts/validate_review_format.py` | Validates structured scoring in reviews | 1 |

### Modified files

| File | Changes | Phase |
|------|---------|-------|
| `scripts/iteration.py` | Add `--max` arg to `next` command | 1 |
| `scripts/guard_output_path.py` | Accept optional iteration-number arg; accept comma-separated filenames for designer | 1, 2 |
| `.claude/agents/reviewer.md` | Add rubric, structured scoring, read dispositions | 1, 3 |
| `.claude/agents/designer.md` | Write dispositions.md, deference self-check | 2, 3 |
| `.claude/agents/clarifier.md` | Blocking/useful rubric | 3 |
| `.claude/agents/backlog-writer.md` | Granularity heuristic | 3 |
| `.claude/skills/design-cycle/SKILL.md` | Iteration cap flag, brief snapshot, pass dispositions path, fix step 9, hook declarations | 1, 2 |

---

## Decisions

| Choice | Alternative rejected | Why |
|--------|---------------------|-----|
| Hard-block structural rules, warn-only heuristic rules | Hard-block everything | False positives on heuristics (paste detection, estimate detection) would halt the pipeline with no human present to unblock |
| Hard-block everything with `--force` escape | — | Model would force everything; defeats the purpose |
| Designer writes dispositions.md | Orchestrator writes it by parsing the design | Designer already has the context; no fragile parsing. Accept the bias trade-off (reviewer can disagree with the framing) |
| Litigation log as separate file | Pass previous review to the reviewer | Separate file preserves "judge what's on the page" principle for the design itself |
| Brief snapshot (copy once) | Diff brief each iteration | Simpler; late edits being invisible is acceptable for v1. Can add a diff-and-warn hook later |
| Structured scoring with mechanical verdict derivation | Prose rubric only | Removes the verdict itself as a source of drift; pushes drift to per-dimension judgement which is more observable |
| 1–3 day story heuristic | No sizing guidance | Unbounded granularity produced wildly inconsistent backlogs; a heuristic at least anchors expectations |

## Open questions

- **Concurrent pipelines:** The `docs/.current_iteration` file introduces a
  race if two pipelines run in the same directory simultaneously. This is
  unlikely (one design cycle at a time is the expected workflow) but would
  break silently. A future fix could namespace by pipeline run ID.
- **Dispositions format evolution:** If the pipeline runs many times, should
  dispositions from all iterations live in a single file (append-only) or one
  per iteration (current design)? One per iteration is simpler but the reviewer
  must be told to read all prior ones, not just the latest. Current decision:
  one per iteration, reviewer reads all that exist.

---

## What this does NOT fix

- **The model gaming the scoring to hit APPROVED** — it can score PASS on
  everything without genuine evaluation. This is an inherent limit; the
  structured format at least makes sloppy reviews grep-able after the fact.
- **Clarifier question quality** — the rubric calibrates blocking/useful but
  doesn't prevent useless questions. The existing memory instruction (learn
  which questions got ignored) is the best lever here.
- **Orchestrator transcription lossy for nuanced answers** — the contradiction
  marking helps, but a human answer with three conditions will still get
  simplified. This is a fundamental limit of the relay pattern; the only real
  fix would be the human writing directly into the file, which is outside
  pipeline scope.
