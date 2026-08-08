Verdict: CHANGES REQUESTED

| Dimension   | Verdict | Finding (if FAIL) |
|-------------|---------|-------------------|
| Coverage    | PASS    | — |
| Soundness   | FAIL    | The Freshness reporter (Component 7) cannot distinguish "sync is broken" from "the other device has not lent a book lately", so at the stated data volumes its steady state is a permanent false warning. |
| Decisions   | PASS    | — |
| Gaps        | FAIL    | `history` — the sole realisation of the answered Q6 requirement — has no defined default contents, and `--all` is never defined. |
| Over-reach  | PASS    | — |

## Blocking

**1. Component 7 (Freshness reporter) warns permanently in the normal case.**

The component is defined as: "Record when this device last successfully saw
another device's data, and warn in the default view when that is stale
(default: 14 days) ... computed from file modification times and the last
successful sync marker."

For the primary deployment path (Dropbox/iCloud/Syncthing — the design says
these users "simply never encounter" the git adapter) there is no sync
operation to mark, so the only available signal is the mtime of the other
device's `events-*.jsonl`. That mtime records when the other device last
*wrote an event*, not when sync last worked. The criteria fix the volume at
"a few loans a month" with "a handful of open loans" (clarification
assumption 2). A second device that has recorded nothing for six weeks —
entirely normal at that rate — has a six-week-old file, and the tool will
print the staleness warning on every single run, forever, with sync working
perfectly.

This is worse than merely useless. The warning is printed in the default
view, which is the same output that carries the overdue nudge, and the design
stakes the whole nudge mechanism on that view being trusted and read
("never paginated and never suppressed"). A line that is always wrong trains
the user to skim the block it lives in.

The defect is in the mechanism, not the wording: absence of new data is
indistinguishable from absence of sync when the data rate is this low. Fixing
it requires a positive signal — e.g. each device touching or appending a
dated heartbeat record to *its own* file on every run, which is compatible
with the one-file-per-device rule — or the component should be removed.
Removing it is a defensible answer: Q10's criterion is satisfied by the
default view, and Component 7 is not something the criteria asked for.

**2. `history` is undefined, and it is the only place the Q6 answer lands.**

Q6 was answered "Keep returned loans as history." The design takes that
position (Fold rules keep `returned_on`; the default view excludes returned
loans "and [they are] reachable through `history` / `who`"). But the command
surface gives only:

```
booklend history [--borrower Sam] [--all]
```

Nothing in the document says what `booklend history` with no flags shows —
returned loans only, or every loan open and closed — and `--all` is never
defined anywhere. Those two unknowns interact: if bare `history` already
shows everything, `--all` has no meaning; if it shows returned loans only,
`--all` presumably adds open ones, but that is a guess. Nor is it stated
whether voided loans appear (Fold rules say `void` "hides the loan from every
view", which would include history, but the interaction is not called out).

An implementer cannot build the history command from this document without
inventing its contract, and it is the sole delivery mechanism for an answered
blocking-adjacent criterion. Define the default contents, define `--all`, and
say whether `history` and `who` differ in more than argument shape.

## Non-blocking

- **The 14-day freshness default is asserted.** The 30-day overdue threshold
  gets a paragraph of reasoning (Component 4) precisely because it was picked
  by the designer rather than the human; 14 days is picked the same way and
  gets nothing. If Component 7 survives, give it the same treatment.

- **A mistaken `void` is unrecoverable.** Decisions says `amend`/`void` exist
  because "an append-only log with no correction path forces the user to edit
  the file by hand, which is exactly when data gets lost." But `void` "hides
  the loan from every view", there is no `unvoid` command and no
  `--include-voided` flag on any view, so a loan voided by mistake — a
  mistyped selector on `booklend void` — can only be recovered by editing the
  JSONL by hand. That is the exact outcome the decision was written to
  prevent.

- **Selector scope is defined only for `back`.** Component 5 says the
  selector searches "open loans only for return". It does not say what
  `amend` and `void` search. Since `amend` exists partly to fix a borrower
  name and returned loans are retained, whether a returned loan is matchable
  by `amend` is a real question left to the implementer.

- **Device-id uniqueness is load-bearing but unspecified.** The entire
  conflict-freedom argument ("Two devices can therefore never produce a write
  conflict") rests on two machines never sharing a device id. Component 8
  argues only about *location* (must not be inside the store). It does not say
  how the id is generated, and nothing detects a violation. A terminal user
  who syncs `~/.config` with a dotfiles manager — a common enough setup in
  exactly this audience — gets one id on both machines and silently
  reintroduces the failure mode the design was built to eliminate. A one-line
  `doctor` check (two events with the same `device` value written from files
  the tool did not create, or a recorded hostname mismatch) would close it.

- **Reads block on the network; writes do not, and only the write case is
  justified.** Component 6 pulls "before a read command" with a 5-second
  timeout. The default no-argument view is a read command and is the most
  frequently run thing in the tool, so the common case can hang for five
  seconds. Decisions justifies the ordering choice for writes ("Confirm the
  write before syncing it") but never considers the read side, where the same
  latency argument applies with more force.

- **A write-only device never converges.** Sync pulls before reads and pushes
  after writes. A push that is rejected as non-fast-forward prints a warning
  and exits 0; recovery depends on a subsequent *read* running the rebase. A
  device used only to record loans at the doorstep would keep failing to push
  indefinitely. In practice the user runs the default view often, so this is
  unlikely rather than impossible — but the recovery path is implicit and
  worth stating.

- **`who Sam` and `history --borrower Sam` appear to be the same query.**
  Neither is justified against the other in Decisions, which is otherwise
  scrupulous about rejected alternatives. Q6's own phrasing ("Sam has
  borrowed four books") makes `who` reasonable to have; having both without
  comment is the loose end.
