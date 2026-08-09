# Dispositions — Iteration 3

Prior iterations: `docs/2/dispositions.md` (iteration 1 had no review, so no
dispositions file exists for it).

Review responded to: `docs/2/review.md` (Verdict: CHANGES REQUESTED —
Soundness FAIL, Gaps FAIL).

## Accepted

- **Blocking 1 — the git adapter never commits, and `pull --rebase` fails on
  the dirty tree a `lend` just created.** Adopted because: this is a defect,
  not a judgement call, and the reviewer traced both consequences correctly.
  With no commit the push sends nothing, and the pull refuses to start against
  unstaged changes — so the adapter would have failed on exactly the runs that
  produced data, warned once, exited 0, and stayed broken silently. That the
  adapter is the design's own answer to the residual risk under a *blocking*
  criterion (Q4) makes it worse, as the reviewer says. Component 6 now
  specifies `add <own events file>` → `commit` → `pull --rebase` → `push`, and
  states the ordering as a correctness requirement with the reason attached, so
  it cannot be reordered by an implementer who thinks it is stylistic.

- **Blocking 2 — the hostname re-check ping-pongs under a live-synced
  `~/.config`.** Adopted because: the reviewer's five-step trace is right, and
  the mechanism was mine, introduced in iteration 2 in response to iteration
  1's finding. It fails worst in the precise scenario it was added for, and it
  breaks the design's own twice-stated rule against advisory output on a normal
  run — the same rule that got the freshness reporter deleted one round
  earlier. I adopted the reviewer's suggested shape (a `hostname → id` map,
  each machine reading its own row, generating only when its row is absent).
  I added one thing beyond the suggestion: if a row is missing but exactly one
  `events-<hostname>-*.jsonl` already exists in the store, the tool adopts that
  id instead of minting a new one, so an identity lost to a concurrent config
  sync is recovered rather than duplicated. The residual — two machines sharing
  both a hostname and a synced config — is now stated as a limit rather than
  papered over.

- **Blocking 3 — the git adapter's activation contract is undefined.** Adopted
  because: both halves are real. `autosync` had no stated default at all, and
  "inside a git work tree" would have let the tool rebase and push a
  repository the user never offered it — including from the bare default view,
  against a branch they were mid-work on. That directly contradicts the
  adapter's own justification that it "can never fail a command". The contract
  is now stated in full: activation requires `<store>/.git` to exist, staging
  is by explicit path to this device's own file only, and `autosync` defaults
  to on. I took one of the reviewer's two offered remedies and declined the
  other — see Rejected. I also added a third principle to Approach ("the tool
  touches only what it owns") so this constraint is visible above the component
  that implements it.

- **Non-blocking — "the earliest wins" for duplicate returns is ambiguous.**
  Adopted because: the reviewer is right that `--on` lets the `date` and `ts`
  orderings disagree, and a fold specified as deterministic across devices
  cannot leave the key unnamed. The rule now reads: earliest `date` wins,
  because the calendar day the book came back is the fact being recorded; ties
  break on `(ts, id)`, which is total and identical everywhere. Naming `ts`
  would have let a late-entered correct date lose to an early-entered wrong
  one.

- **Non-blocking — the 5-second sync timeout is asserted.** Adopted because:
  it costs one sentence and yields a config key. I note a partial reservation
  for the record — the parity with the 30-day threshold is not exact, since 30
  days is a product decision the human explicitly declined to make (Q5) while
  the timeout is an implementation constant with no user-visible semantics
  beyond how long the prompt is held, which the reviewer itself concedes. I do
  not think every constant in a design needs a paragraph. But this one is
  cheap to justify and better for being tunable, so `sync_timeout` is now a
  config key with its reasoning stated.

- **Non-blocking — `booklend sync` on a non-git store is silent.** Adopted
  because: the reviewer drew the right line. "Say nothing" is correct for the
  implicit post-command step and wrong for a command whose entire purpose is to
  answer "did my data go anywhere?". `booklend sync` now explains that the
  store is not a git repository root, names the folder, and points at
  `git init`. The document states why this does not breach the no-noise
  principle: that principle governs the default view and unattended steps, not
  a question the user asked directly.

- **Non-blocking — config key names are given only for `store`.** Adopted
  because: the reviewer is right that this is exactly what two implementers
  spell differently. Component 7 now has a table naming `store`,
  `overdue_days`, `autosync` and `sync_timeout` with defaults and their flag
  equivalents.

## Rejected

- **The alternative offered under Blocking 3 of requiring explicit opt-in in
  config for the git adapter.** Rejected because: the reviewer offered two
  remedies — restrict activation to a repository whose root is the store, *or*
  require an explicit config opt-in — and I took the first. A fallback that is
  off until the user finds an undocumented config key is a fallback that is
  usually off, which is the same failure mode as Blocking 1 wearing different
  clothes: the design's answer to the blocking multi-device requirement sits
  there inert while appearing to exist. Running `git init` in the store
  directory is already a deliberate, explicit act by the user, and the
  root-only activation rule is precisely what makes it safe to read that act as
  consent. Requiring both would be belt-and-braces on the safety question at
  the cost of the requirement the component exists to serve. The finding
  itself — that the contract was undefined — is accepted above; this rejects
  one of the two proposed ways to define it.

## Deferred

- None. Every finding in `docs/2/review.md` is dispositioned above.

## Why full acceptance was appropriate

Every finding in this review is accepted; only one of two alternative remedies
offered inside a finding is rejected. That warrants an explanation, because
uniform agreement is the shape capitulation also takes.

The honest reason is that iteration 2 crossed from describing intent into
specifying mechanism, and mechanism is checkable in a way that intent is not.
Two of the three blocking findings are not disagreements about judgement at
all: a git sequence with no `commit` in it does not sync, and `pull --rebase`
against a dirty tree does not run — those are facts about git, and my sequence
was wrong about both. The identity ping-pong is the same kind of error, and
worse in origin, because I introduced that mechanism in iteration 2 in
response to iteration 1's finding and did not trace it through the very
scenario I wrote it for. When a reviewer points at a mechanism that
demonstrably does not work, there is nothing to defend; defending it would be
theatre.

The third blocking finding and three of the four non-blocking ones are
omissions rather than errors — an unstated default, an unnamed key, an
unnamed tiebreak field, a silent command. Omissions are cheap to concede
because conceding them costs nothing but words and leaves no design decision
overturned.

Where there was a genuine choice to make, I did make one against the review:
the reviewer's Blocking 3 offered two remedies and I declined the one that
would have left `autosync` off by default, because it reintroduces in a
subtler form the exact defect Blocking 1 identified. I also declined, in
substance, the reviewer's iteration-1 heartbeat remedy (recorded in
`docs/2/dispositions.md`) and its iteration-1 device-id detection mechanism,
and I have logged a standing reservation above about the demand that every
designer-chosen constant carry a justification paragraph. So the pattern
across three rounds is agreement on findings and independence on remedies,
which is the division I would expect when the reviewer is reading carefully
and I am the one who has to make the parts fit together.
