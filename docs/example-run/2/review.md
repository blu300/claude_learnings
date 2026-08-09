Verdict: CHANGES REQUESTED

| Dimension   | Verdict | Finding (if FAIL) |
|-------------|---------|-------------------|
| Coverage    | PASS    | — |
| Soundness   | FAIL    | The git adapter's stated sequence (`pull --rebase` then `push`, with no commit) syncs nothing and fails deterministically on a dirty tree; and the device-id hostname re-check ping-pongs under the very condition it was added to handle. |
| Decisions   | PASS    | — |
| Gaps        | FAIL    | The git adapter's activation contract is undefined: no default for `autosync`, and "inside a git work tree" means the tool will rebase and push a repository it does not own. |
| Over-reach  | PASS    | — |

## Blocking

**1. The git sync adapter never commits, so it cannot sync — and its stated
first step fails outright (Component 6, step 3).**

The sequence is specified precisely: "Read local state, do the work, append any
event locally" → print → "`pull --rebase`, then `push`, with a 5-second overall
timeout". The word "commit" does not appear anywhere in the document, and no
step stages or records the appended line as a git object.

Two consequences, both certain rather than probabilistic:

- After a `lend`, `events-<device>.jsonl` has an unstaged modification (or is
  untracked, on the first event from that device). `git pull --rebase` refuses
  to run against a dirty working tree ("cannot pull with rebase: You have
  unstaged changes"). Step 3 therefore fails on exactly the runs that produced
  new data. Step 5 catches the failure, prints one warning line and exits 0 —
  so the failure is quiet and permanent.
- Even if the pull succeeded, `push` has nothing to push, because no commit
  exists. The remote never receives an event.

This is not a cosmetic omission. The git adapter is the design's own answer to
the residual risk it identifies in Decisions ("the user has no sync mechanism
at all — is addressed by the git adapter") and in Open Question 1, against a
blocking criterion (Q4, multi-device). As written, the fallback for the one
blocking requirement is inert. The ordering also matters and must be stated:
`add` + `commit` must precede `pull --rebase`, not follow it, or the rebase
refuses to start.

**2. The hostname re-check degenerates into a per-run identity flap in the
exact scenario it exists to handle (Component 7, "The dotfiles-sync hazard").**

The rule is: "On every run, if the current hostname differs from the recorded
one, the tool prints one warning line and generates a **new** id for this
machine." The hazard it addresses is "`~/.config` is exactly the directory a
terminal user is likely to sync with a dotfiles manager".

If `~/.config` is genuinely live-synced (Dropbox/Syncthing/iCloud over
dotfiles — the case named), the mechanism does not converge:

1. Machine A runs, records `laptop-3f2a91` / hostname `laptop`.
2. Sync copies the `device` file to machine B.
3. B runs, sees hostname `desk` ≠ `laptop`, warns, generates `desk-91bc04`,
   records hostname `desk`.
4. Sync copies that back to A.
5. A runs, sees `laptop` ≠ `desk`, warns, generates a third id. Repeat forever.

Each machine acquires a new device id on essentially every run, and each id
that writes an event creates another `events-*.jsonl` in the store. The design
notes "the old device file is left in the store and still read and merged like
any other", which is true and means no data is lost — but that reasoning is
written for a one-off regeneration, not for one per run. The store accumulates
files without bound and `doctor`'s device listing becomes unreadable, which is
the one place the design puts duplicate-id detection.

It also contradicts a principle the document states twice and treats as
load-bearing: "the default view contains nothing that is not a fact about the
user's loans" (Approach) and "Nothing advisory, diagnostic or speculative is
ever printed in this view" (default view definition). A warning line that fires
on every run is precisely the always-on advisory noise the previous revision's
freshness reporter was removed for.

The finding is about the mechanism, not the goal. A device file that records
`hostname → id` pairs (each machine reads its own entry, generating one only
when its hostname is absent) gives a stable id per machine under a synced
`~/.config` and preserves the detection property. That is a small change, but
the document has to take a position on it because the whole conflict-freedom
argument is explicitly staked on device ids being distinct and stable.

**3. The git adapter's activation contract is undefined (Component 6,
Component 7).**

Two undefined points that together decide whether the tool silently writes to
repositories the user did not offer it:

- Step 3 says the adapter runs "if the store is a git repo **and autosync is
  on**". Nowhere does the document say whether `autosync` defaults to on or
  off. Component 7 lists it as a resolvable preference and stops there.
  `--no-sync` implies on-by-default; nothing states it.
- Activation is by detection, not by opt-in: "if — and only if — the store
  directory is inside a git work tree". The store default is
  `~/.local/share/booklend`, but a user who points `--store` or
  `BOOKLEND_STORE` at a folder that happens to sit inside an existing
  repository (a notes repo, a dotfiles repo, a monorepo checkout) gets
  `pull --rebase` and `push` run against that repository after every `booklend`
  invocation, including the no-argument default view. That can rebase a branch
  the user is mid-work on and push unrelated local commits.

An implementer has to choose a default and a detection scope, and the two
plausible choices differ in whether the tool mutates repositories it does not
own. Given that the adapter is justified as something that "can never fail a
command", the document should state the default and either restrict activation
to a repo whose root is the store directory, or require explicit opt-in in
config.

## Non-blocking

- **"the earliest wins" for duplicate returns is ambiguous** (Fold rules).
  Two `return` events for one loan may carry different `date` values (via
  `--on`) and different `ts` values, and the two orderings can disagree. Given
  the stated reason ("because the book came back once"), the intended key is
  presumably the `date`, but the rule names neither field, and the fold is
  specified as deterministic across devices.

- **The 5-second sync timeout is asserted.** The document is otherwise careful
  to justify designer-chosen numbers (the 30-day threshold gets a paragraph
  precisely on those grounds). The consequence here is small — output has
  already been printed, so the timeout only bounds how long the shell prompt is
  held — but the number is picked with no reasoning given.

- **`booklend sync` on a non-git store is silent.** Component 6 says that when
  the store is not a git repo the adapter "does nothing at all and never
  mentions itself". Applied to the explicit `booklend sync` command, that means
  the user asks for a sync and gets no output and exit 0. The rule is right for
  the implicit post-command step; the explicit command is the one place where
  saying "this store is not a git repo; sync is handled by your file-sync tool"
  is a fact about the user's setup rather than noise.

- **Config key names are given only for `store`.** The threshold and autosync
  preferences are referred to by flag name (`--overdue-days`, `--no-sync`) but
  their `config.ini` keys are never named, unlike `store`. Trivial to invent,
  but it is the kind of thing two implementers would spell differently.
