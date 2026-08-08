# Dispositions — Iteration 4

Prior iterations: `docs/3/dispositions.md`, `docs/2/dispositions.md`
(iteration 1 had no review, so no dispositions file exists for it).

Review responded to: `docs/3/review.md` (Verdict: CHANGES REQUESTED —
Soundness FAIL; Coverage, Decisions, Gaps and Over-reach all PASS).

This is iteration 4 of a maximum 4. No further revision is possible, so the
scope of this round was deliberately limited to closing the blocking finding
and the five non-blocking ones, with no new capability added.

## Accepted

- **Blocking 1 — the git adapter never establishes or requires a remote, so
  the design's own `git init` instruction produces an activated adapter that
  fails on every run.** Adopted because: the reviewer is right on the facts and
  right about the consequence. `git init` leaves no remote and no upstream;
  `pull --rebase` then exits with "no tracking information" and `push` with "no
  configured push destination", every run, forever. That yields exactly the two
  outcomes the reviewer names — a permanent advisory line under the overdue
  block, which is the noise principle 2 exists to forbid and which cost two
  earlier mechanisms their place in this design, and a second machine that
  never receives anything, leaving the answer to the blocking Q4 inert while
  appearing to exist. The reviewer's observation that this is the same class of
  defect as iteration 2's missing `commit`, one step further along the same
  sequence, is fair and is the reason I have restated it as a standing
  principle rather than only patching the line: **a component that cannot do
  its job is inert and honest, never active and noisy** (Approach, principle
  4).

  The three positions the review asked for are all taken:
  - *Is an upstream part of activation?* Yes. It is condition 2 of four, tested
    with `git rev-parse --abbrev-ref @{upstream}`. Unmet conditions make the
    adapter inert and silent on ordinary commands, and are reported verbatim by
    `doctor` and `booklend sync`, so the one place diagnostics live can no
    longer describe a never-syncing adapter as healthy.
  - *Are repeated failures suppressed?* Reads are silent; writes get one line.
    See the Rejected section for the mechanism I declined.
  - *What is the user told to do?* `booklend sync` now prints the `remote add`
    / `push -u` block for the first machine and the `git clone` /
    `BOOKLEND_STORE` block for the second, replacing the bare `git init`
    suggestion.

- **Blocking 1, second half — `git commit` preconditions (`user.name` /
  `user.email`).** Adopted because: the reviewer correctly identified a second,
  independent permanent-failure path with the same signature. I closed it by
  removing the precondition rather than detecting it: the tool supplies
  `booklend <booklend@localhost>` via `git -c` for that one invocation, never
  writing to the user's config. Diagnosing it would have added a fifth
  condition and a message; supplying it means the failure cannot occur.

- **Non-blocking — a timeout firing mid-rebase can wedge the store, with no
  recovery path and no `doctor` report.** Adopted because: the reviewer is
  right that this is the only path in the design that can lose a loan, and that
  is worth closing even at low probability. A rebase or merge in progress is
  now condition 4 of activation: the adapter does not commit, pull or push
  while one is outstanding, so no commit can ever land on a detached HEAD.
  Local appends continue, because recording a loan must never be blocked.
  `doctor` reports the condition with data-safe recovery steps. I did not adopt
  automatic `--continue` or `--abort`; that would be the tool making
  destructive git decisions in the one situation where it cannot know what is
  half-applied. I have also corrected one detail of the finding's reasoning —
  see Rejected.

- **Non-blocking — step 5's detection of new events is unspecified.** Adopted
  because: it is a named, user-visible output line with no defined trigger,
  which is precisely the kind of thing two implementers spell differently. It
  is now a `git rev-parse HEAD` comparison across the pull, with the count from
  `git diff --numstat <before> HEAD -- '*.jsonl'`. No re-fold is performed.

- **Non-blocking — first-run bootstrap is undefined.** Adopted because: the
  reviewer is right that exit code 2 read as an error where a fresh install
  needs a creation. The rule is now asymmetric and stated in Component 2: the
  default store and `~/.config/booklend/` are created; an explicit `--store` or
  `BOOKLEND_STORE` path that does not exist is exit 2. That asymmetry is
  deliberate — a typo, or a cloud folder that has not mounted yet, must not
  silently become a second empty store, because "no loans and no error" is
  indistinguishable from having lost them.

- **Non-blocking — the identity recovery glob collides with the artefacts it
  is meant to survive.** Adopted because: the finding is exactly right and
  slightly embarrassing — the store layout in my own document lists
  `events-laptop-3f2a91 (conflicted copy).jsonl` as an expected inhabitant, and
  it matches the glob I specified, defeating the "exactly one" test in the
  scenario the recovery was written for. The scan is now the anchored pattern
  `^events-<hostname>-[0-9a-f]{6}\.jsonl$`.

- **Non-blocking — "still out" is defined disjointly in one view and
  ambiguously in another.** Adopted because: both readings really were
  consistent with the example. `who` now prints `Sam — 4 borrowed, 2 still out
  (1 overdue)`, the nesting is shown by the layout, and Component 4 states once
  that overdue is a subset of out rather than a sibling — with the default
  view's two sections noted as a partition of the same set.

## Rejected

- **The suppression mechanism implied by "whether a repeated identical sync
  failure is suppressed on ordinary runs".** Rejected because: suppressing *by
  repetition* requires remembering the last failure — a local state file, a
  comparison rule and a time window — and I am not willing to introduce
  remembered state, on the final iteration, to solve a problem that has a
  memoryless answer. Splitting by command class needs nothing: reads
  (overwhelmingly the bare default view, the most-run command and the one
  carrying the nudge) print nothing on failure, and writes — infrequent, and
  the only moment at which new data exists that has not propagated — print one
  line. Total silence would have been the simpler rule but is wrong for writes:
  letting the user believe a doorstep loan reached the other machine when it
  did not is the blocking requirement failing invisibly. The cumulative
  picture, which is what a suppression counter would have been reconstructing,
  is already in git: `doctor` reports unpushed commits and their age from
  `git log @{upstream}..HEAD`. The finding — that the document had no position
  — is accepted above; this rejects one way of taking it.

- **The claim within the rebase finding that `git rebase --abort` "resets the
  working tree and drops the events appended since".** Rejected as stated,
  because the sequence commits new events in step 4 *before* the pull in step
  5, and `git rebase --abort` returns to the pre-rebase HEAD, which already
  contains that commit. The actual loss path is narrower: a *subsequent* run
  committing onto the detached HEAD of the suspended rebase, whose commit the
  abort then discards, plus any appends made but not yet committed during the
  wedged window. This is not a reason to dismiss the finding — the path is real
  and I have closed it — but the fix follows from the precise mechanism, and
  had I adopted the stated one I would have been guarding the wrong step.

## Deferred

- None. Every finding in `docs/3/review.md` is dispositioned above.

## Note on the cap and on what remains open

The blocking finding is closed and no new capability was added, per the
instruction for a final iteration. Two things are worth stating plainly for
whoever picks this up, because there is no iteration 5 in which to raise them:

**Open question 1 has grown slightly sharper and is unresolved.** The git
fallback now requires the user to create a remote repository somewhere. That
is a hosting decision the design deliberately does not make for them, so the
answer to the blocking multi-device criterion (Q4) rests on the user having
*either* a file-sync tool *or* somewhere to host a git remote. Nothing in the
answers confirms they have either. If they have neither, no amount of revision
to this document fixes it — it needs a server, which is a different design.
This should go to the human before code is written.

**The remaining open questions (2–7) are unchanged and all minor**: a chosen
30-day default, unnamed devices, an optional shell-startup check I left out as
beyond Q2, borrower-name normalisation, a possible importer with no known
source format, and cross-device time zones. None of them changes the shape of
the solution.
