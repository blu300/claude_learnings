Verdict: CHANGES REQUESTED

| Dimension   | Verdict | Finding (if FAIL) |
|-------------|---------|-------------------|
| Coverage    | PASS    | — |
| Soundness   | FAIL    | The git adapter never establishes or requires a remote. The document's own onboarding instruction (`git init`) produces an activated adapter whose `pull`/`push` fail on every run — a permanent warning line on ordinary commands and no multi-device sync, which is the blocking requirement the adapter exists to serve. |
| Decisions   | PASS    | — |
| Gaps        | PASS    | — |
| Over-reach  | PASS    | — |

## Blocking

**1. `git init` is not enough to sync, and the design treats it as if it were
(Component 6 activation contract, lines 176–186; `booklend sync` output, lines
405–410; Decisions "autosync defaults to on", lines 525–533).**

The word "remote" appears twice in the document (line 171, "exchange them with
the remote"; line 197, `git push`) and is never established, required, or
checked. Activation is defined purely as "`<store>/.git` exists" plus
`autosync` on, and `autosync` defaults to on. The only onboarding instruction
the tool ever gives the user is line 409:

```
Run `git init` there if you want booklend to sync it directly.
```

`git init` creates a repository with no remote and no upstream branch. A user
who follows that instruction reaches the following steady state, on every
single invocation including the bare default view:

- Step 3 succeeds (`add` + `commit`, or nothing to stage on a read).
- Step 4 fails: `git pull --rebase` exits non-zero with "There is no tracking
  information for the current branch." (`git push` likewise: "No configured
  push destination.")
- Step 6 fires: "Any failure prints one warning line."

Two consequences, both certain rather than probabilistic:

- **The adapter is inert for the path the design prescribes.** The git adapter
  is the design's stated answer to the residual risk under the blocking Q4
  ("the user has no sync mechanism at all — is addressed by the git adapter",
  line 500). Following the tool's own advice yields a local repository that
  never reaches a second machine. The second machine, meanwhile, has no
  instruction at all: nothing in the document tells the user to `git clone` the
  store on device B, or to `git remote add` on device A, and the store
  directory on B must already exist as that clone for anything to work. This is
  the same class of defect as iteration 2's missing `commit` — the answer to
  the blocking criterion appears to exist and does nothing — in a different
  place in the same sequence.

- **It reintroduces the always-on advisory line the design has twice deleted
  mechanisms to avoid.** Principle 2 (lines 71–74) states "No advisory line may
  fire on a normal run", and the default-view definition repeats it: "Nothing
  advisory, diagnostic or speculative is ever printed in this view" (line 436).
  The freshness reporter was removed in iteration 2 and the identity re-check in
  iteration 3 on exactly this ground. A `booklend` with no arguments, in a
  remoteless git store, prints a sync warning below the overdue block forever.

The same gap covers `git commit` preconditions: on a machine with no
`user.name`/`user.email` configured, step 3 fails on every write, again with one
warning line and exit 0, again permanently. Nothing in the document detects
either state. `doctor`'s enumerated reasons for inactivity are only "store is
not a git repository root" and "autosync is off" (lines 281–283) — neither of
which is what has actually gone wrong, so the one place the design puts
diagnostics reports the adapter as *active and healthy* while it has never
synced anything.

The finding is not that git is the wrong choice. It is that the activation
contract, which this revision rewrote specifically to be stated "in full",
still omits the precondition that decides whether the adapter can do its job.
The document needs to take a position on: whether an upstream/remote is part of
activation (and what `doctor` and `booklend sync` say when it is absent);
whether a repeated identical sync failure is suppressed on ordinary runs; and
what the user is actually told to do on each of the two machines to reach a
working state.

## Non-blocking

- **A timeout that fires mid-rebase can wedge the store, and there is no
  recovery path** (Component 6 step 4; `sync_timeout`). Steps 3 and 4 share one
  5-second timeout, which by the design's own reasoning is expected to fire on
  a slow or newly-woken connection. If the kill lands after the fetch and
  during the rebase, `.git/rebase-merge` survives; every later run's
  `git pull --rebase` then fails with "there is already a rebase-merge
  directory", and its `git commit` lands on the detached HEAD of the suspended
  rebase. A user who resolves this the obvious way — `git rebase --abort` —
  resets the working tree and drops the events appended since. The probability
  is low (the fetch normally consumes the budget), but this is the one path in
  the design that can lose a loan, and `doctor` does not report an in-progress
  rebase.

- **Step 5's detection of new events is unspecified** (line 198). "If step 4
  brought in events the render did not include" is a printed, user-visible
  behaviour, but the document does not say how it is determined — comparing
  `HEAD` before and after the pull, counting lines, or re-folding. Trivial to
  choose, but it is a named output line with no defined trigger.

- **First-run bootstrap is undefined.** Nothing states whether the tool creates
  `~/.local/share/booklend`, `~/.config/booklend/`, or a missing `--store`
  target. Exit code 2 covers "directory unreadable, no writable device file",
  which reads as an error where the first run of a fresh install would need a
  creation. An implementer must guess whether a non-existent store is an error
  or a bootstrap.

- **The identity recovery glob collides with the artefacts it is meant to
  survive** (lines 244–248). If the config row is missing, the tool scans for
  `events-<hostname>-*.jsonl` and adopts the id "if exactly one matches". The
  store layout on line 305 shows `events-laptop-3f2a91 (conflicted copy).jsonl`
  as an expected inhabitant. That file matches the same glob, so the "exactly
  one" test fails and a new id is minted — in precisely the scenario (an active
  file-sync tool that both drops config lines and makes conflicted copies)
  where the recovery exists. The stated limit ("bounded churn, never a lost
  loan") still holds, but the recovery is weaker than the text claims.

- **"still out" is defined disjointly in one view and ambiguously in another.**
  The default view puts `OVERDUE` and `OUT` in separate sections, so they are
  disjoint. `who` prints "Sam — 4 borrowed, 1 still out, 1 overdue" (line 458),
  where it is not stated whether the overdue book is counted in "still out".
  Both readings are consistent with the example.
