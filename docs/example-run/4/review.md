Verdict: CHANGES REQUESTED

| Dimension   | Verdict | Finding (if FAIL) |
|-------------|---------|-------------------|
| Coverage    | PASS    | — |
| Soundness   | FAIL    | The two-machine setup block that this revision added as the fix for iteration 3's blocking finding does not work as printed: `git push -u origin main` is issued against a repository that, by the design's own activation rule, can never contain a commit; and machine B is told to set the store with a shell-session-only `export`, whose loss silently produces the freshly-created empty default store the design elsewhere calls indistinguishable from data loss. |
| Decisions   | PASS    | — |
| Gaps        | PASS    | — |
| Over-reach  | PASS    | — |

## Blocking

**1. The first-machine setup block cannot succeed, because condition 2
guarantees the repository has no commits (lines 486–501; activation table
lines 199–208; sequence step 3, line 229).**

`booklend sync` on a repository with no upstream prints:

```
    cd ~/git/booklend-data
    git remote add origin <url>
    git push -u origin main
```

Trace the state the user is actually in when they see it. They ran `git init`
in the store. Condition 2 (`@{upstream}` resolves) fails, so by the activation
contract the adapter "does not run", and the sequence stops at step 3 *before*
step 4's `git add`/`commit`. Therefore booklend has never committed anything in
this repository, and the events files are untracked. `main` is an unborn
branch. `git push -u origin main` fails with `error: src refspec main does not
match any` — certainly, not probabilistically. No upstream is created, so the
next `booklend sync` prints the identical block again. The user is in a loop
against instructions the document describes as "the exact commands for *both*
machines" (line 630).

This is the same shape as the finding this revision was written to close: the
tool's only onboarding path terminates in a state that cannot sync. It is
milder — the failure is loud rather than silent — but it is the one path by
which a git-only user reaches the blocking multi-device answer (Q4), and the
design has no other. The missing step is an initial `git add`/`git commit`
before the push (the "stage only this device's file" rule at line 253 governs
the adapter, not the user's own bootstrap commit, so there is no conflict in
telling them to stage everything once).

Two smaller defects in the same block: the branch is hardcoded as `main`,
though `git init` yields `master` on git < 2.28 and wherever
`init.defaultBranch` is unset; and nothing tells the user what to do if the
`.jsonl` files predate the repository, which is the normal case since the
default store is local (line 379) and the user moves to git afterwards.

**2. Machine B is told to set the store with `export`, and losing it lands in
the exact silent-empty-store state the design forbids (line 500 vs. Component 2
bootstrap, lines 129–135, and Decisions lines 714–718).**

The second-machine block ends:

```
    git clone <url> ~/git/booklend-data
    export BOOKLEND_STORE=~/git/booklend-data
```

`export` lives for one shell. In the next terminal, resolution falls through to
`~/.local/share/booklend` (line 377). Per the bootstrap rule, the default store
*is created if absent* — so the user gets an empty list, no warning, and exit
0. That is verbatim the outcome the design's own Decisions section calls
unacceptable: "the user sees no loans and no error, which is indistinguishable
from having lost them" (lines 717–718). The asymmetry the design chose
(explicit path missing → exit 2, default path missing → create) was designed to
prevent exactly this, and the onboarding text routes the user around it by
making the explicit path depend on an environment variable that evaporates.

The config file has a `store` key for precisely this (line 281), and the
instruction does not mention it. Either the block should set `store` in
`~/.config/booklend/config.ini`, or the document should say where the `export`
is expected to be persisted. As written, the design's answer to a blocking
criterion works only inside the terminal session in which it was set up.

## Non-blocking

- **`hostname` and `<short-hostname>` are used interchangeably in Component 7
  (lines 289–308).** `devices.ini` is described as keyed on "hostname" with the
  example keys `laptop`/`desk`; generation is `<short-hostname>-<6 hex>`; the
  recovery scan is `^events-<hostname>-[0-9a-f]{6}\.jsonl$`. On a machine
  reporting `laptop.local`, a scan built from the full hostname will not match
  the file generated from the short one, and the anchored-pattern fix from this
  revision silently stops working. Picking one form throughout resolves it.

- **`booklend export` has no default format** (line 462: `[--json|--csv]`, both
  optional). Neither the JSON shape nor the CSV column set is stated; both are
  derivable from the folded Loan record (lines 433–436), but the default is not.

- **The field set `amend` may change is never enumerated.** Only `--borrower`
  appears (lines 390, 459). Whether `--title`, `--on` and `--note` are amendable
  is a fork an implementer must guess, and it interacts with the fold rule
  "`amend` overwrites the named fields".

- **Event `id` and `loan` id generation is unspecified.** Both are load-bearing
  — `id` for cross-device deduplication, `loan` for `short_id` (first 6 chars)
  and hence for selector collisions. The properties needed (globally unique
  without coordination) are implied by the design but never stated.

- **The exit code of `booklend sync` when the adapter is inert is unstated.**
  The table (lines 573–578) covers user error and store error; sync failures are
  defined never to fail an ordinary command, but `sync` is the command whose
  entire purpose is the thing that did not happen, and either 0 or non-zero is
  defensible.
