# Definition: Book Lending Tracker

Criteria: `docs/1/clarification.md` (Answers section)
Brief: `docs/1/brief-snapshot.md`
Revision of: `docs/3/definition.md` — see **Changes in this revision**
Dispositions: `docs/4/dispositions.md`

---

## Problem

One person lends their own books to friends and loses track of who has what.
They want to record a loan at the moment of handing the book over, see what is
still outstanding, and be nudged about books that have been out a long time.

From the answers, the shape is fixed:

- A **command-line tool**, run in a terminal (Q1).
- The nudge is an **"overdue" section printed when the tool is run**. No
  scheduler, no daemon, no notifications that arrive on their own (Q2).
- **Loans only.** A book exists in the data because it was lent; there is no
  catalogue of the shelf (Q3).
- **Multi-device.** A loan recorded on one machine must be visible on another
  (Q4). This supersedes the earlier assumption that data need not sync.
- Returned loans are **kept as history**, not deleted (Q6).
- The reminder is **for the owner only** — no messages to borrowers (Q9).
- Success: **recording a loan is one short command**, and **no book is overdue
  without that being visible on the next run** (Q10).
- **A manual export the user can copy elsewhere** is sufficient backup (Q11).
- **Fewer fields preferred** (Q8). No pre-decided technology (Q12).

Everything else in the clarifier's assumption list stands: one user, no
accounts, tens of books, free-text borrower names, one global overdue
threshold, books only, lending out only, no ISBN/cover/API lookup, nothing to
migrate in.

---

## Approach

The whole design turns on one tension: **a CLI with no server, that must still
show the same loans on two machines.**

The approach is a **conflict-free append-only event log stored in a directory
the user already syncs.** Three properties do the work:

1. **Append-only events, never mutation.** Recording a loan appends one line.
   Recording a return appends one line. Nothing is ever rewritten in place, so
   a partial or interleaved write can never corrupt an existing record.
2. **One file per device.** Each machine writes only to `events-<device>.jsonl`
   and never touches another machine's file. Two devices can therefore never
   produce a write conflict, no matter what sync mechanism sits underneath —
   Dropbox, iCloud Drive, Syncthing, a git remote, or a USB stick. Reading is
   "merge every `*.jsonl` in the directory".
3. **State is a fold, not a file.** The list of open loans is computed on every
   run by replaying the merged events. There is no cached state to go stale or
   disagree between devices.

That combination means the tool itself contains **no sync logic it depends
on**. Sync is somebody else's problem — the user's existing file-sync
arrangement — and the data format is chosen so that whatever that arrangement
is, it cannot lose or mangle a record. A thin optional git adapter is provided
for the user who has no cloud drive, because a terminal user reliably has git.

Four principles govern everything the tool prints, waits for, and touches:

> **1. The network is never on the critical path of output.** Every command,
> read or write, completes and prints locally before any sync is attempted, so
> nothing can hang while a book is being handed over.
>
> **2. No advisory line may fire on a run where nothing is wrong.** Diagnostics
> live in `booklend doctor`. The default view carries the overdue nudge and
> nothing else, ever.
>
> **3. The tool touches only what it owns.** It writes one file per device in
> the store, and it operates a git repository only when the store directory is
> itself that repository's root.
>
> **4. A component that cannot do its job is inert and honest, never active
> and noisy.** If the git adapter lacks a precondition it does not run, does
> not warn on ordinary commands, and says exactly what is missing when asked.

The fourth principle is the one this revision turns on. A sync adapter that
fires and fails on every run is worse than one that never activates: it
produces a permanent warning line under the overdue block — the noise that
principle 2 exists to prevent — while still not syncing anything.

On top of that store sits a deliberately small command surface. The default
invocation with no arguments prints the outstanding loans with overdue ones
first, which is what satisfies the nudge requirement: the nudge is not a
feature you have to ask for, it is the thing the tool says when you type its
name.

Why not the alternatives, in short (expanded in **Decisions**): a SQLite file
syncs badly and merges not at all; a hosted API is a server, an account and an
uptime problem for a person tracking a few loans a month; a single shared
JSON file is exactly the thing that produces "conflicted copy" files.

---

## Components

### 1. CLI front end

**Responsibility.** Parse the command line, dispatch to one operation, render
the result as plain text, choose an exit code.

**Boundaries.** Contains no storage knowledge and no overdue arithmetic. It is
the only component that writes to stdout/stderr. It never prompts
interactively — every command completes from its arguments alone, so a loan
can be recorded in one line at the doorstep. It always renders before the sync
adapter is invoked.

### 2. Event store

**Responsibility.** Locate the store directory; read and merge every
`*.jsonl` file in it into a single time-ordered event stream; append new
events to this device's own file.

**Boundaries.** Knows about lines, files and event ordering. Knows nothing
about loans, borrowers or overdueness — it deals in opaque event records.
Appends are a single `write()` in `O_APPEND` mode of one newline-terminated
line, which is atomic against other processes on the same machine for the line
sizes involved. Malformed lines (a truncated write from a killed process, a
sync artefact) are skipped, counted, and reported by `doctor` — a corrupt line
must never make the rest of the loans invisible, and must never print noise
into the default view.

**Bootstrap.** On first run the tool creates `~/.config/booklend/` and, if the
store path is the *default* (`~/.local/share/booklend`), creates that too. A
store path given explicitly via `--store` or `BOOKLEND_STORE` that does not
exist is an **error** (exit 2), not a bootstrap: a typo, or a cloud-drive
folder that has not mounted yet, must never silently become a second empty
store while the real loans sit elsewhere. The error message names the path and
says to create it if it is genuinely new.

### 3. State fold

**Responsibility.** Replay the merged event stream into the current set of
loans. Deduplicate by event id (the same event may appear twice if a sync tool
duplicates a file). Apply the ordering and precedence rules below.

**Boundaries.** Pure function: events in, loans out. No I/O, no clock, no
config. This is what makes the behaviour testable without a filesystem.

### 4. Overdue policy

**Responsibility.** Given a loan and today's date, classify it as `out` or
`overdue`, and compute days elapsed.

**Boundaries.** One threshold in days, global to all loans, from config.
**The default is 30 days.** Chosen because the human left Q5 unanswered and a
month is the ordinary social expectation for a lent book — long enough not to
nag about a book someone is still reading, short enough that a forgotten book
surfaces while the lending is still a shared memory. It is a single config key
(`overdue_days`) and a single flag, so being wrong about it is cheap.

An overdue loan **is** an outstanding loan; `overdue` is a subset of `out`,
not a sibling of it. Views that separate them into sections say so by layout;
views that count them say so in words.

### 5. Selector resolution

**Responsibility.** Turn what the user types — `booklend back dispossessed`,
`booklend back 6f1c` — into exactly one loan.

**Boundaries.** Matches a short-id prefix first, then a case-insensitive
substring of the title, then of the borrower name. **Each command defines the
set it searches:**

| Command | Searches |
|---|---|
| `back` | open loans only |
| `amend` | all non-voided loans, open and returned |
| `void` | all non-voided loans, open and returned |
| `unvoid` | voided loans only |

Amend deliberately reaches returned loans: correcting a borrower's name on a
loan that has already come back is a normal thing to want, and `who` reads
history.

Short-id prefixes are matched against the searched set only, so the same
prefix can never resolve to a loan the command cannot act on. If zero or more
than one loan matches, the tool prints the candidates and exits non-zero. It
never guesses. This is the component that keeps "one short command" from
becoming "one short command that returned the wrong book".

### 6. Sync adapter (optional, git only)

**Responsibility.** When the store directory is a git repository with somewhere
to send commits, commit this device's new events and exchange them with the
remote — after the command has completed and its output has been printed.

**Activation contract.** All four conditions must hold. If any one fails, the
adapter does not run, prints nothing on ordinary commands, and reports the
specific unmet condition through `doctor` and `booklend sync`:

| # | Condition | Checked by |
|---|---|---|
| 1 | `<store>/.git` exists — the store is the repository *root* | directory test |
| 2 | The current branch has an upstream tracking branch | `git rev-parse --abbrev-ref @{upstream}` |
| 3 | `autosync` is on (default: on; `--no-sync` disables per run) | config |
| 4 | No rebase or merge is in progress in that repository | `.git/rebase-merge`, `.git/rebase-apply`, `.git/MERGE_HEAD` |

Condition 1 keeps the tool out of repositories it does not own: a store that
merely sits *inside* someone else's work tree (a notes repo, a dotfiles repo, a
monorepo checkout) is not activated, so the tool never rebases or pushes a
branch the user is mid-work on.

**Condition 2 is the one that makes activation mean something.** `git init`
alone produces a repository with no remote and no upstream, where every `pull`
and `push` fails with "no tracking information" / "no configured push
destination". Treating that as an activated adapter would mean a warning line
under the overdue block on every single run, forever, while nothing ever
reaches the second machine. Requiring an upstream makes the half-configured
state *inert and diagnosable* instead of *active and broken* — principle 4.

**Commit identity.** Before committing, the tool reads `git config user.name`
and `user.email`. If either is unset it supplies `booklend
<booklend@localhost>` for that one invocation via `git -c user.name=... -c
user.email=... commit`. It never writes to the user's git config. This removes
a precondition rather than detecting one: an otherwise correctly configured
store on a machine with no git identity would otherwise fail its commit on
every write, permanently and quietly.

**Sequence.** For every command, read or write alike:

1. Read local state, do the work, append any event to this device's file.
2. Print the result. The command is now, from the user's point of view, done.
3. If not activated, stop here.
4. `git add <store>/events-<this-device>.jsonl`, then commit with the identity
   rule above. If there is nothing to stage, skip the commit and continue —
   read-only commands normally have nothing.
5. Record `git rev-parse HEAD` as `before`. Run `git pull --rebase`, then
   `git push`. Steps 4 and 5 share one timeout (`sync_timeout`, default 5s).
6. If `git rev-parse HEAD` now differs from `before`, the pull brought
   something in. Print one line, with the count taken from
   `git diff --numstat <before> HEAD -- '*.jsonl'` added lines:
   `Updated: 3 new events received — re-run to see the current list.`
   HEAD comparison is the trigger; no re-fold is performed.

**What is printed when sync fails.** Nothing, on read commands — the default
view stays clean, which is principle 2 and the reason two earlier mechanisms
were deleted. **One warning line on write commands** (`lend`, `back`, `amend`,
`void`, `unvoid`), because a write is the moment the user has data that has
not propagated, and letting them believe a doorstep loan reached the other
machine when it did not is the blocking requirement failing invisibly. Write
commands are infrequent, so this cannot become the always-on noise principle 2
forbids. The full state is always available from `doctor`.

**Boundaries.** Never load-bearing, never on the critical path of output. It
stages **only this device's own events file** by explicit path — never `git
add -A`, never `git add .`. Running the same commit-pull-push cycle after
*every* command, rather than pulling before reads and pushing after writes, is
what makes a device used only to record loans converge: its next `lend`
rebases onto the remote and pushes both. Users on Dropbox/iCloud/Syncthing
never encounter this component.

**Why condition 4 exists.** `sync_timeout` is expected to fire occasionally on
a slow link. If the kill lands during the rebase rather than the fetch,
`.git/rebase-merge` survives and the repository is left mid-rebase on a
detached HEAD. Everything committed in step 4 of earlier runs is safe there —
`git rebase --abort` returns to a HEAD that already contains it — but a *later*
run that committed onto the detached HEAD would have its commit discarded by
that abort. Condition 4 removes that path entirely: while a rebase is in
progress the adapter does not commit, does not pull and does not push. Local
appends continue normally, because recording the loan must never be blocked;
they are simply not committed until the user clears the rebase. `doctor`
reports the condition and gives the data-safe recovery: copy the events files
aside, run `git rebase --abort`, restore the copies, run `booklend sync`.

### 7. Config and identity

**Responsibility.** Resolve the store path, overdue threshold, sync
preferences, and this device's identity.

**Config file.** `~/.config/booklend/config.ini`, section `[booklend]`:

| Key | Default | Also settable as |
|---|---|---|
| `store` | `~/.local/share/booklend` | `--store`, `BOOKLEND_STORE` |
| `overdue_days` | `30` | `--overdue-days` |
| `autosync` | `true` | `--no-sync` (per run) |
| `sync_timeout` | `5` (seconds) | — |

**Identity.** The conflict-freedom argument rests entirely on two machines
never sharing a device id, so identity is specified rather than assumed.

`~/.config/booklend/devices.ini` maps hostname to device id:

```ini
[devices]
laptop = laptop-3f2a91
desk   = desk-91bc04
```

- On every run, the tool looks up **its own hostname** in this file. If an
  entry exists, that is its id — permanently and without comment.
- If no entry exists for this hostname, the tool looks in the store for files
  matching the anchored pattern `^events-<hostname>-[0-9a-f]{6}\.jsonl$`. The
  pattern is anchored and exact so that sync artefacts such as
  `events-laptop-3f2a91 (conflicted copy).jsonl` do not match — they would
  otherwise break the "exactly one" test in precisely the situation the
  recovery exists for, since the same file-sync tool that drops a config line
  is the one that makes conflicted copies. If exactly one file matches, the
  tool adopts that id, so an identity lost from config is recovered rather
  than duplicated. Otherwise it generates `<short-hostname>-<6 hex from
  os.urandom>` and adds a line.
- It **never modifies or removes another hostname's entry**, and it never
  prints a warning on a normal run.

This is what makes the file safe to sync. If the user syncs `~/.config` with a
dotfiles manager — the likely case for this audience — every machine finds its
own entry, keeps a stable id, and the file simply accumulates one line per
machine.

**Stated limits.** Two machines that share a hostname *and* a synced config
would share an id; nothing here detects that, and `doctor` can only show the
map. If a concurrent sync drops one machine's line, that machine reacquires
its id from the store on the next run, or at worst creates one extra events
file — bounded churn, never a lost loan.

### 8. Export

**Responsibility.** Emit the full loan set to stdout as JSON or CSV.

**Boundaries.** Read-only, writes to stdout only, never to a file — the user
redirects. Note that the store directory *is already* a complete, plain-text,
copyable backup; export exists for reading the data somewhere else (a
spreadsheet), which is what Q11 asks for.

### 9. Doctor

**Responsibility.** Report, on demand, everything the tool knows about the
health of its own store. This is where all diagnostics live, and the only
place they live.

**Boundaries.** Read-only. Reports:

- the resolved store path and how it was resolved;
- **sync status**: whether the adapter is active, and if not, *which* of the
  four conditions failed, in those words — `store is not a git repository
  root` / `branch has no upstream — nothing to push to` / `autosync is off` /
  `a rebase is in progress` (with the data-safe recovery steps);
- when active: the upstream it tracks, and **how many local commits are
  unpushed and since when**, taken from `git status -sb` / `git log
  @{upstream}..HEAD`. This is the honest answer to "has my data actually gone
  anywhere?" and needs no state file of its own, because git already keeps it;
- the hostname-to-id map and which entry is this machine's;
- every `events-*.jsonl` found with the date its **last event was written**;
- the count of malformed lines skipped, orphan `return` events with no
  matching `lend`, and the number of voided loans.

**What it deliberately does not claim.** The per-file dates are labelled "last
event written", not "last synced". A single device cannot distinguish "the
other machine has not lent a book lately" from "sync has stopped working" —
both look identical from here, and at a few loans a month the innocent case is
the normal one. `doctor` therefore reports the observation and leaves the
inference to the user, rather than converting it into a warning that would be
wrong most of the time.

---

## Data and interfaces

### Store layout

```
<store>/                      e.g. ~/Dropbox/booklend/  or  ~/git/booklend-data/
  events-laptop-3f2a91.jsonl  written only by that device
  events-desk-91bc04.jsonl    written only by that device
  events-laptop-3f2a91 (conflicted copy).jsonl   ← still read and merged
  .git/                       optional; with an upstream, activates the adapter
  .gitattributes              optional; see setup below
```

Resolution order for `<store>`: `--store` flag → `BOOKLEND_STORE` env →
`store` key in config → `~/.local/share/booklend` (XDG default). The default
is deliberately a *local* path: the tool works standalone out of the box, and
becomes multi-device the moment the user points it at a synced folder or
completes the git setup below.

### Event records

One JSON object per line, UTF-8, no nesting beyond one level.

```json
{"id":"e-8a41...","type":"lend","ts":"2026-08-08T14:03:11Z","device":"laptop-3f2a91","loan":"6f1c...","title":"The Dispossessed","borrower":"Sam","date":"2026-08-08","note":null}
{"id":"e-b2d7...","type":"return","ts":"2026-09-30T09:12:40Z","device":"desk-91bc04","loan":"6f1c...","date":"2026-09-30"}
{"id":"e-04f9...","type":"amend","ts":"...","device":"...","loan":"6f1c...","fields":{"borrower":"Sam Patel"}}
{"id":"e-77c2...","type":"void","ts":"...","device":"...","loan":"6f1c...","reason":"typo"}
{"id":"e-91b0...","type":"unvoid","ts":"...","device":"...","loan":"6f1c..."}
```

| Field | Meaning |
|---|---|
| `id` | Unique per event. Used for deduplication. |
| `ts` | UTC instant, used only for ordering. |
| `date` | Local calendar date (`YYYY-MM-DD`) — the human fact "lent on". |
| `loan` | The loan this event concerns. Generated at `lend` time. |

The split between `ts` and `date` matters: "since when" is a day in the user's
life, not an instant, and it must not shift because they lent a book at 11pm.

Five event types is the complete set. `amend`, `void` and `unvoid` exist
because an append-only log with no correction path forces the user to edit the
file by hand, which is exactly when data gets lost — and a `void` that could
not be undone would recreate that problem for anyone who mistypes a selector.

### Fold rules

- Events sorted by `(ts, id)`. The `id` tiebreak makes the ordering identical
  on every device even when two events share a timestamp.
- Duplicate `id` → the second and later copies are ignored.
- `lend` creates the loan; a repeated `lend` for an existing `loan` is ignored.
- `amend` overwrites the named fields, later events winning.
- `return` sets the return date. If two devices both record a return for one
  loan, the winner is the event with the **earliest `date`** — the calendar
  day the book came back, which is the fact being recorded; `--on` may make
  that a different ordering from `ts`. If two returns carry the same `date`,
  the tie is broken by `(ts, id)`, which is total and identical on every
  device.
- `void` / `unvoid` set and clear the voided flag, later events winning.
- A `return` whose `lend` is missing is retained as an orphan and reported by
  `doctor`; it is never silently dropped.

Because every event names its `loan`, clock skew between devices can only
misorder events *within* one loan, and the precedence rules above make each of
those cases deterministic anyway.

### Loan (the folded record)

`loan_id`, `short_id` (first 6 chars), `title`, `borrower`, `lent_on`,
`returned_on | null`, `note | null`, `voided`.

Derived at render time: `days_out`, `status ∈ {out, overdue, returned}`.

Four stored fields, one optional — matching the "fewer fields" preference.

### Visibility of voided loans

Stated once, and applying everywhere: a voided loan is **excluded from every
view** — default, `history`, `who`, `export` — except `history
--include-voided`, where it appears marked `[voided]`, and `doctor`, which
counts them. Its events remain in the file permanently. `history
--include-voided` is how a user finds the short id of a loan they voided by
mistake, in order to `unvoid` it.

### Command surface

```
booklend                                  default view: overdue, then out
booklend lend "The Dispossessed" Sam      the one short command
booklend lend "Title" Sam --on 2026-08-01 --note "hardback"
booklend back dispossessed                record a return
booklend back 6f1c22 --on 2026-09-30
booklend history [--since DATE] [--include-voided]
booklend who Sam                          one person's whole record
booklend amend 6f1c22 --borrower "Sam Patel"
booklend void 6f1c22
booklend unvoid 6f1c22
booklend export [--json|--csv]
booklend sync                             explicit git sync
booklend doctor                           store health and diagnostics
```

Global flags: `--store`, `--overdue-days`, `--no-sync`, `--no-color`.

### `booklend sync` and the two-machine setup

`booklend sync` runs the same commit-pull-push cycle on demand and always
reports what it did. When the adapter is not activated it names the unmet
condition and gives the instructions that reach a working state — the tool's
onboarding lives here, because this is the command the user runs when asking
"why isn't my other machine seeing this?".

Not a repository at all:

```
$ booklend sync
This store is not a git repository, so booklend has nothing to sync.
Your loans are files in ~/Dropbox/booklend — whatever syncs that folder
syncs them. To have booklend sync it directly, see `booklend sync --help`.
```

A repository with no upstream — the state `git init` alone leaves behind:

```
$ booklend sync
This store is a git repository but its branch has no upstream, so there is
nowhere to push. booklend is not syncing it.

  On this machine, once you have created an empty remote repository:
    cd ~/git/booklend-data
    git remote add origin <url>
    git push -u origin main

  On your other machine:
    git clone <url> ~/git/booklend-data
    export BOOKLEND_STORE=~/git/booklend-data
```

`booklend sync --help` carries the same two blocks plus the optional
`.gitattributes` line `*.jsonl merge=union`, which makes any residual
concurrent append merge by concatenation instead of conflicting. It is
optional because each device writes its own file, so a conflict needs a sync
artefact to occur at all; and the tool does not write the file itself, since
that is the user's repository configuration to make.

Nothing above breaches principle 2: it is printed only in response to a
command whose entire purpose is to answer this question.

### The three views, defined

**Default (no arguments)** — the nudge. Open loans only, overdue first.

```
$ booklend
OVERDUE (2)                                            threshold 30 days
  ! 6f1c22  The Dispossessed          Sam        lent 2026-05-02   98 days
  ! 22ab90  Piranesi                  Ellie      lent 2026-06-30   39 days

OUT (1)
    9d0e14  A Wizard of Earthsea      Tom        lent 2026-08-01    7 days
```

Ordered oldest-first within each section. Overdue is always first, always
printed, never paginated and never suppressed — that is the mechanism behind
"no book is overdue without it being visible on the next run". `!` marks
overdue in text as well as colour, so the signal survives piping, `NO_COLOR`,
and colour-blindness. Returned and voided loans are excluded. The two sections
partition the outstanding loans: a loan in `OVERDUE` is not repeated under
`OUT`. Nothing advisory, diagnostic or speculative is ever printed in this
view.

**`history`** — the whole record. **Every non-voided loan, open and
returned**, most recently lent first, with a status column:

```
$ booklend history
  9d0e14  A Wizard of Earthsea      Tom      lent 2026-08-01   out
  22ab90  Piranesi                  Ellie    lent 2026-06-30   OVERDUE (39d)
  6f1c22  The Dispossessed          Sam      lent 2026-05-02   OVERDUE (98d)
  4a77e1  Solaris                   Sam      lent 2026-03-11   returned 2026-04-02
```

`--since DATE` limits by lent date. `--include-voided` adds voided loans,
marked. There is no `--all` flag: bare `history` already shows everything
except voided loans, so `--all` had no meaning and has been removed.

**`who NAME`** — one person's record, plus the summary that Q6 asked for in
its own words ("Sam has borrowed four books"):

```
$ booklend who Sam
Sam — 4 borrowed, 2 still out (1 overdue)
  6f1c22  The Dispossessed          lent 2026-05-02   OVERDUE (98d)
  9d0e14  A Wizard of Earthsea      lent 2026-08-01   out
  4a77e1  Solaris                   lent 2026-03-11   returned 2026-04-02
  ...
```

"Still out" counts every unreturned loan, and the parenthesised overdue count
is a **subset** of it, never a separate group — the nesting is shown by the
layout so the two numbers cannot be read as disjoint. `who` is the only
per-borrower query; `history` has no `--borrower` flag, so there is exactly
one way to ask this question. Name matching is a case-insensitive substring,
and if it matches more than one distinct borrower string the tool lists them
and exits non-zero rather than merging them.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (including "you have overdue books" — this is normal output) |
| 1 | User error: ambiguous or unmatched selector, bad date |
| 2 | Store error: explicit store path missing, directory unreadable, no writable device file |

---

## Decisions

**JSON Lines append-only log, not SQLite.** SQLite is the obvious choice for a
local CLI and would be better in every way except the one that matters: it is
a binary file that a file-sync tool can only replace wholesale. Two devices
that both write produce either a lost update or an unmergeable "conflicted
copy". A line-oriented text log merges by concatenation, survives a truncated
write, can be repaired in any editor, and can be diffed. Rejected SQLite.

**One file per device, not one shared file.** A single shared `events.jsonl`
would still be append-only, but two devices appending between syncs produce
two divergent versions of the same path, and every sync tool resolves that by
picking one — silently losing loans. Per-device files make concurrent writes
structurally impossible rather than merely unlikely. The cost is that reading
means globbing a directory, which at this data volume is free.

**Sync delegated to the user's existing tool, not built in.** Building sync
means a server, an account, a secret, and an uptime obligation for someone
tracking a few loans a month. Rejected. The design instead makes the data
*safe to sync with anything*, which is a weaker promise honestly kept rather
than a stronger one poorly kept. The residual risk — that the user has no sync
mechanism at all — is addressed by the git adapter and raised in Open
Questions.

**Git adapter included, but never required.** Rejected alternative: leave sync
entirely out. The human answered "multi-device" as blocking, and a design that
answers it with "arrange that yourself" is thin for a user who has no cloud
drive. The adapter is a short shell-out to `git`, is inert unless its four
conditions hold, and can never fail a command.

**An upstream is part of activation, not an assumption.** `git init` produces
a repository with no remote, and the previous revision activated on
`<store>/.git` alone while telling the user to run exactly that command. The
result would have been a `pull` and `push` failing on every invocation: a
permanent warning line under the overdue block, and a second machine that
never receives anything — the design's answer to the blocking multi-device
requirement present on paper and inert in practice, which is the same defect
as iteration 2's missing `commit` one step further along the same sequence.
Rejected. Checking `@{upstream}` costs one command and converts the
half-configured state from *active and broken* into *inert and diagnosable*.
Rejected alternative: activate anyway and let the failures speak — that is
precisely the always-on advisory noise that got two earlier mechanisms
deleted.

**Onboarding lives in `booklend sync`, and the tool does not automate it.**
Rejected alternative: have the tool run `git remote add` or `git clone`
itself. Choosing a host, creating an empty remote and having credentials
available are decisions and secrets that belong to the user; a tool that
guesses at them fails in ways it cannot explain. What the tool owes the user
is the exact commands for *both* machines at the moment they ask why sync is
not happening, which is what `booklend sync` now prints.

**Commit identity is supplied, not required.** Rejected alternative: detect a
missing `user.name`/`user.email` and report it as a fifth unmet condition.
Supplying `booklend <booklend@localhost>` via `-c` for that one invocation
removes the failure mode entirely instead of diagnosing it, and never touches
the user's git config. A store whose commits are authored by the tool is
unremarkable; a store that silently stopped committing is not.

**Sync failures are silent on reads and reported on writes.** Rejected
alternative: warn on every failing run, which is the noise principle 2
forbids. Rejected alternative: suppress repeated identical failures with a
counter in a local state file — that adds a state file, a comparison rule and
a time window on the last iteration, to solve a problem git already answers.
Splitting by command class needs no memory at all: reads (overwhelmingly the
bare default view) stay clean, and writes — infrequent, and the only moment
new data exists that has not propagated — get one line, because letting the
user believe a doorstep loan reached the other machine when it did not is the
blocking requirement failing invisibly. The cumulative picture is always one
`booklend doctor` away, derived from `git log @{upstream}..HEAD` rather than
from anything the tool has to remember.

**Activation requires the store to be the repository root, not merely inside
one.** A user who points `BOOKLEND_STORE` at a folder inside a notes repo or a
monorepo checkout would otherwise have every `booklend` run — including the
bare default view — rebase and push a repository they were mid-work on.
Staging only this device's events file by explicit path is the second half of
the same rule.

**`autosync` defaults to on.** Rejected alternative: require an explicit
opt-in key in config. A fallback that is off until the user finds a config key
is a fallback that is usually off. Completing the remote setup is already an
explicit, deliberate act, and it is now condition 2 of activation — so the
default being on can no longer cause anything to happen to a repository the
user has not deliberately prepared.

**Commit, then pull --rebase, then push — in that order.** `git pull --rebase`
refuses to run against the dirty tree a `lend` has just created, and a `push`
with no commit sends nothing. The ordering is a correctness requirement, not a
preference.

**A rebase in progress blocks sync entirely.** `sync_timeout` is expected to
fire occasionally, and a kill landing during the rebase rather than the fetch
leaves a detached HEAD. Anything already committed survives a later
`git rebase --abort`; what would not survive is a *subsequent* run's commit
landing on that detached HEAD. Rejected alternative: attempt to continue or
abort the rebase automatically, which is the tool making destructive git
decisions on the user's behalf in the one situation where it cannot know what
is half-applied. Refusing to touch the repository, continuing to append
locally, and printing the data-safe recovery in `doctor` closes the only path
in the design that could lose a loan.

**A 5-second sync timeout, configurable.** Output has already been printed by
the time sync runs, so the number bounds only how long the shell prompt is
held after the user has their answer. Five seconds is long enough for a
push-pull against a small repository over a slow or newly-woken connection,
and short enough that a dead network does not feel like a hang.

**Sync always runs after output, for reads as well as writes.** Pulling
*before* reads would put the timeout in front of the most frequently run
command in the tool. Rejected. Local state is rendered first, the network is
touched afterwards, and if the pull brought something new the tool says so in
one line and invites a re-run — triggered by a `HEAD` comparison across the
pull, which needs no bookkeeping of its own.

**No staleness or sync-health warning in any view.** An earlier revision
warned when another device's file had not changed in 14 days. At a few loans a
month a peer that has recorded nothing for six weeks is entirely normal, so
that warning would have fired permanently while sync worked perfectly.
Rejected outright. Rejected alternative: a per-run heartbeat record, which
narrows the false positive to "peer last ran" but cannot remove it — **no
device can tell "peer idle" from "peer disconnected" without a third party**,
and this design deliberately has none.

**Identity is a hostname → id map, not a single recorded hostname.** Storing
one hostname and regenerating on mismatch oscillates under a synced
`~/.config`: each machine sees the other's hostname, regenerates, syncs the
change back, and both acquire a new id every run. Rejected. A map lets each
machine read its own row and ignore the rest. The recovery scan is an anchored
exact pattern rather than a glob, so that a `(conflicted copy)` artefact —
made by the same sync tool that would drop a config line — cannot defeat the
"exactly one match" test.

**A missing explicit store path is an error; only the default store is
created.** Rejected alternative: create whatever path is given. A mistyped
`--store`, or a cloud folder that has not mounted yet, would silently become a
second empty store — the user sees no loans and no error, which is
indistinguishable from having lost them.

**A global 30-day threshold, not per-loan.** Per-loan dates would mean asking a
question at the doorstep, and the clarifier's assumption of one global
threshold went unchallenged.

**Default view is the no-argument invocation.** Rejected `booklend list` as
the primary path. The nudge has to be the thing that happens when you type the
tool's name, or it depends on the user remembering which subcommand shows it —
and forgetting is the problem this exists to solve.

**`history` shows everything; `who` is the only per-borrower query.** The
alternative — `history --borrower NAME` alongside `who NAME` — gives two
spellings of one question, and neither could be justified against the other.

**Duplicate returns resolve on `date`, not `ts`.** The rule records the day
the book came back, and `--on` lets the two orderings disagree; naming `ts`
would let a late-entered correct date lose to an early-entered wrong one.

**Selector ambiguity is an error, not a best guess.** Returning the wrong book
silently corrupts the one thing the tool is for; printing two candidates costs
the user one extra keystroke.

**`amend`, `void` and `unvoid` rather than edit or delete.** Rejected in-place
editing: it breaks the append-only property that makes concurrent devices
safe. Rejected hard delete: it breaks the "returned loans stay as history"
answer.

**No compaction, ever.** At a few loans a month the log reaches a few thousand
lines in a lifetime. Rejected periodic rewriting, which is the one operation
that could lose data and the only reason a device would need to modify another
device's file.

**Python 3, standard library only.** Rejected Go and Rust, whose single static
binary is genuinely better for a multi-device tool, because each device would
need a build or a release pipeline for its platform. Rejected shell, which
cannot parse JSON or do date arithmetic without becoming worse than either.
Python is present on macOS and every Linux, needs no dependency resolution,
and the whole tool is a few hundred lines. Config is INI via `configparser`
rather than TOML so that older Python 3 versions work without `tomllib`.

**Export writes to stdout only.** Rejected a `--output` flag; shell
redirection already does this, and the store directory is itself the backup.

---

## Open questions

1. **Does the user actually have a file-sync mechanism?** The multi-device
   answer (Q4) is blocking, but the human did not say *how* their machines
   share files. This design works with any of Dropbox/iCloud/Syncthing/git and
   ships a git adapter as a fallback — but the git path now requires the user
   to create a remote repository somewhere, which is a hosting decision this
   design does not make for them. If the answer is "no cloud drive and nowhere
   to host a remote", the multi-device requirement cannot be met without
   introducing a server, which would be a materially different design.
   **This is the single assumption most worth confirming before building.**

2. **Is 30 days right?** Chosen by me because Q5 was unanswered. Stated here
   explicitly so it can be overruled cheaply.

3. **Which devices, and how is the tool installed on each?** "Multi-device"
   was answered but the devices were not named. Two laptops is trivial; a
   laptop and a phone is not — a phone has no ordinary terminal, and if a
   phone is in scope the CLI answer (Q1) and the multi-device answer (Q4)
   pull against each other.

4. **Should a shell-startup check exist?** The success criterion is satisfied
   by the default view, but it only fires when the user runs the tool. A
   `booklend check --quiet` returning non-zero when something is overdue would
   let the user wire the nudge into their shell profile. I have deliberately
   left it out as beyond what Q2 asked for, but it is the cheapest available
   improvement to the actual complaint in the brief ("I forget").

5. **Should a borrower's name be normalised?** Free-text names (assumption 4)
   mean "Sam", "sam" and "Sam Patel" are three people to `who`. Matching is a
   case-insensitive substring and refuses to merge distinct strings silently,
   which makes the divergence visible but does not fix it. A `booklend rename`
   sweep is the obvious fix if it matters.

6. **Nothing to import** was assumed, and Q7 was left unanswered. If there is
   a spreadsheet or notes file after all, a one-off importer is a small
   addition — but it is not designed here because no source format is known.

7. **Time zones across devices.** Loan dates are recorded as the local
   calendar date of the recording device. For a user whose devices are in one
   place this is invisible. It is stated rather than solved.

---

## Changes in this revision

**Blocking (Soundness):**

- **An upstream tracking branch is now condition 2 of activation.** Without
  one the adapter does not run, prints nothing on ordinary commands, and
  reports `branch has no upstream — nothing to push to` through `doctor` and
  `booklend sync`. This removes both consequences the reviewer traced: the
  permanent warning line under the overdue block, and `doctor` reporting a
  never-syncing adapter as healthy.
- **The onboarding instruction is now complete and covers both machines.**
  `booklend sync` prints the `remote add` / `push -u` block for the first
  machine and the `git clone` / `BOOKLEND_STORE` block for the second, in
  place of the previous bare `git init` suggestion, which by itself reached a
  state that could never sync.
- **The commit precondition is removed rather than diagnosed.** A missing
  `user.name`/`user.email` no longer fails every write; the tool supplies
  `booklend <booklend@localhost>` for that invocation only, without touching
  the user's git config.
- **Failure reporting is defined by command class:** silent on reads,
  one line on writes, full picture in `doctor` derived from
  `git log @{upstream}..HEAD`.

**Non-blocking:** a rebase or merge in progress is now condition 4 of
activation, so no commit can land on a detached HEAD and the one loan-losing
path is closed, with data-safe recovery steps in `doctor`; step 6's trigger is
specified as a `HEAD` comparison with the count from `git diff --numstat`;
bootstrap is defined (the default store is created, an explicit missing path
is exit 2); the identity recovery scan uses an anchored exact pattern so
`(conflicted copy)` artefacts cannot defeat it; and `who` now prints
`2 still out (1 overdue)`, with overdue stated as a subset of out in
Component 4 and in the view definition.

**Partial disagreement:** I accepted the finding about repeated sync failures
but not the suppression mechanism implied by it (a remembered failure state);
and I corrected one detail of the rebase finding's reasoning — committed
events survive `git rebase --abort`, so the loss path is narrower than stated,
though it is real. Both are recorded in `docs/4/dispositions.md`.

**Note on the cap.** This is iteration 4 of 4; there is no further revision.
The design is complete against the answered criteria. Open question 1 is the
one item I would want confirmed with the human before any code is written,
because it is the only one that could change the shape of the solution rather
than its details.
