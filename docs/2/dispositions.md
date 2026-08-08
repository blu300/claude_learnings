# Dispositions — Iteration 2

Prior iterations: none (iteration 1 had no review to respond to, so no
`docs/1/dispositions.md` exists).

Review responded to: `docs/1/review.md` (Verdict: CHANGES REQUESTED —
Soundness FAIL, Gaps FAIL).

## Accepted

- **Blocking 1 — Component 7 (Freshness reporter) warns permanently in the
  normal case.** Adopted because: the reviewer's reasoning is correct and the
  consequence is worse than the defect. At "a few loans a month" a peer file
  unchanged for six weeks is the *normal* state, so the warning fires forever
  while sync works. It printed into the default view, which is the same output
  carrying the overdue nudge, so an always-wrong line would train the user to
  skim the one block the entire design stakes itself on. Component 7 is
  deleted. The underlying observation survives in `doctor` as a labelled fact
  ("last event written: 41 days ago") with an explicit statement that it is
  not a sync-health signal. Remedy differs from both of the reviewer's
  suggestions — see Rejected.

- **Blocking 2 — `history` is undefined and it is the only place the Q6 answer
  lands.** Adopted because: the reviewer is straightforwardly right that an
  implementer could not build the command. `history` with no flags now shows
  every non-voided loan, open and returned, most recently lent first, with a
  status column, and a worked example is in the document. `--all` is deleted
  rather than defined, because once bare `history` shows everything there is
  nothing left for it to add — the reviewer identified exactly this
  interaction. Voided-loan visibility is now stated once as a rule covering
  every view, with `history --include-voided` as the single exception.

- **Non-blocking — the 14-day freshness default is asserted without
  reasoning.** Adopted because: the reviewer's parity argument was right (30
  days got a paragraph precisely because I chose it; 14 got nothing). Resolved
  by deletion — the component that used the number is gone, so no unjustified
  default remains.

- **Non-blocking — a mistaken `void` is unrecoverable.** Adopted because: the
  reviewer caught my own stated rationale contradicting itself. I justified
  `amend`/`void` on the grounds that a log without a correction path forces
  hand-editing, then made `void` the one operation with no correction path.
  Added an `unvoid` command, an `unvoid` event type, and `history
  --include-voided` so the user can find the id of a loan they voided by
  mistake.

- **Non-blocking — selector scope is defined only for `back`.** Adopted
  because: it is a real fork an implementer would have to guess at, and the
  answer is not uniform. Component 5 now tabulates the search set per command:
  `back` sees open loans, `amend` and `void` see all non-voided loans
  including returned ones, `unvoid` sees only voided ones.

- **Non-blocking — device-id uniqueness is load-bearing but unspecified.**
  Adopted because: the reviewer identified the exact scenario that breaks the
  central claim of the design, and the audience for a terminal tool is the
  audience most likely to sync `~/.config`. Generation is now specified
  (`<short-hostname>-<6 random hex>`), the device file records the hostname it
  was generated on, a hostname mismatch triggers a warning and a fresh id, and
  `doctor` lists ids in use. I implemented detection by hostname rather than
  the reviewer's suggested "events written from files the tool did not create"
  test, because a tool cannot reliably tell which files it created — the
  detection would not have worked. The finding is accepted; the mechanism
  differs.

- **Non-blocking — reads block on the network and only the write case is
  justified.** Adopted because: this was an inconsistency I should have caught.
  I argued latency for writes and then put a 5-second timeout in front of the
  most frequently run command in the tool. There is now one rule for reads and
  writes alike: render locally, then sync, then report in one line if the pull
  brought something new.

- **Non-blocking — a write-only device never converges.** Adopted because: the
  reviewer was right that the recovery path was implicit. The same change fixes
  it — every command, including a `lend`, now runs `pull --rebase` before
  `push`, so a device used only at the doorstep converges on its next use. The
  behaviour is now stated rather than left to be inferred.

- **Non-blocking — `who Sam` and `history --borrower Sam` are the same
  query.** Adopted because: the reviewer correctly noted that a Decisions
  section otherwise scrupulous about alternatives had two spellings of one
  question with no justification for either. Resolved by removing `--borrower`
  from `history`. `who` remains as the sole per-borrower query and carries the
  count summary that Q6's own phrasing ("Sam has borrowed four books") asks
  for.

## Rejected

- **The heartbeat remedy proposed for Blocking 1** ("each device touching or
  appending a dated heartbeat record to its own file on every run"). Rejected
  because: it relabels the false positive rather than removing it. A heartbeat
  changes the signal from "peer last lent a book" to "peer last ran the tool" —
  but a laptop the user simply did not open for six weeks is still
  indistinguishable from a laptop whose sync died. The two cases are not
  separable from a single device without a third party that both devices can
  reach, and this design deliberately has no such party; that is the whole
  point of delegating sync to the user's own file-sync tool. Adopting the
  heartbeat would also add a new file type to a store whose simplicity is
  load-bearing, and would turn every read command into a write, causing sync
  churn on every invocation of the most-run command. I took the reviewer's
  alternative disposal instead — removal — and put the raw, honestly labelled
  observation in `doctor`, where the user draws the inference at the moment
  they have a reason to. This is a rejection of the proposed mechanism, not of
  the finding: the finding itself is accepted above.

## Deferred

- None. Every finding in `docs/1/review.md` is dispositioned above.
