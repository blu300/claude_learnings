# Definition: Book Lending Tracker

Criteria: `docs/1/clarification.md` (Answers section)
Brief: `docs/1/brief-snapshot.md`
Revision of: `docs/2/definition.md` — see **Changes in this revision**
Dispositions: `docs/3/dispositions.md`

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

Three principles govern everything the tool prints, waits for, and touches:

> **1. The network is never on the critical path of output.** Every command,
> read or write, completes and prints locally before any sync is attempted, so
> nothing can hang while a book is being handed over.
>
> **2. The default view contains nothing that is not a fact about the user's
> loans.** Diagnostics live in `booklend doctor`, which the user runs when they
> want them. No advisory line may fire on a normal run.
>
> **3. The tool touches only what it owns.** It writes one file per device in
> the store, and it operates a git repository only when the store directory is
> itself that repository's root.

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

**Responsibility.** When the store directory is itself the root of a git
repository, commit this device's new events and exchange them with the remote
— after the command has completed and its output has been printed.

**Activation contract.** Stated in full, because it decides whether the tool
ever writes to a repository the user did not offer it:

- The adapter runs only when **`<store>/.git` exists** — the store directory
  is the repository *root*. A store that merely sits *inside* someone else's
  work tree (a notes repo, a dotfiles repo, a monorepo checkout) is **not**
  activated. The tool never rebases or pushes a repository it does not own.
- `autosync` **defaults to on**. Making the store directory a git repository
  is itself the deliberate act of opting in; there is no second switch to
  discover. `autosync = false` in config, or `--no-sync` on any single run,
  turns it off.
- If neither `<store>/.git` exists nor autosync is on, the adapter does
  nothing and says nothing on ordinary commands. The explicit `booklend sync`
  command is the exception — see below.

**Sequence.** For every command, read or write alike:

1. Read local state, do the work, append any event to this device's file.
2. Print the result. The command is now, from the user's point of view, done.
3. If activated: `git add <store>/events-<this-device>.jsonl` then
   `git commit -m "booklend: <n> event(s) from <device>"`. If there is nothing
   to stage, skip the commit and continue — read-only commands normally have
   nothing.
4. `git pull --rebase`, then `git push`. Steps 3 and 4 share one timeout
   (`sync_timeout`, default 5 seconds).
5. If step 4 brought in events the render did not include, print one line:
   `Updated: 3 new events received — re-run to see the current list.`
6. Any failure prints one warning line. The command still exits 0.

**Why the commit comes first.** `git pull --rebase` refuses to run against a
dirty working tree, and a `push` with no commit sends nothing. Staging and
committing before the pull is therefore not an ordering preference but a
correctness requirement: with it reversed, or absent, every run that produced
new data would fail at step 4 and every run that did not would push nothing.

**Boundaries.** It is never load-bearing and never on the critical path of
output. It stages **only this device's own events file** by explicit path —
never `git add -A`, never `git add .` — so unrelated files a user has put in
the store directory are left alone. Running the same commit-pull-push cycle
after *every* command, rather than pulling before reads and pushing after
writes, is what makes a device that is only ever used to record loans
converge: its next `lend` rebases onto the remote and pushes both. Users on
Dropbox/iCloud/Syncthing never encounter this component.

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
- If no entry exists for this hostname, the tool first looks in the store for
  an existing `events-<hostname>-*.jsonl`. If exactly one matches, it adopts
  that id, so an identity lost from config is recovered rather than
  duplicated. Otherwise it generates `<short-hostname>-<6 hex from
  os.urandom>` and adds a line.
- It **never modifies or removes another hostname's entry**, and it never
  prints a warning on a normal run.

This is what makes the file safe to sync. If the user syncs `~/.config` with a
dotfiles manager — the likely case for this audience — every machine finds its
own entry, keeps a stable id, and the file simply accumulates one line per
machine. The previous revision compared a single recorded hostname against the
current one and regenerated on mismatch, which under a live-synced `~/.config`
made two machines overwrite each other's identity on every run.

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

**Boundaries.** Read-only. Reports: the resolved store path; whether the git
adapter is active and, if not, why not (`store is not a git repository root` /
`autosync is off`); the hostname-to-id map and which entry is this machine's;
every `events-*.jsonl` found with the date its **last event was written**; the
count of malformed lines skipped; orphan `return` events with no matching
`lend`; and the number of voided loans.

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
  .git/                       optional; activates the sync adapter
```

Resolution order for `<store>`: `--store` flag → `BOOKLEND_STORE` env →
`store` key in config → `~/.local/share/booklend` (XDG default). The default
is deliberately a *local* path: the tool works standalone out of the box, and
becomes multi-device the moment the user points it at a synced folder or runs
`git init` in it.

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

`booklend sync` runs the same commit-pull-push cycle on demand. Unlike the
implicit step, it always reports what it did — and when the adapter is not
active it says so rather than exiting silently:

```
$ booklend sync
This store is not a git repository root, so there is nothing to sync.
Your loans are files in ~/Dropbox/booklend — whatever syncs that folder
syncs them. Run `git init` there if you want booklend to sync it directly.
```

That is a fact about the user's own setup, asked for explicitly, so it does
not breach the "no advisory noise" principle — which governs the default view
and unattended steps, not a command whose entire purpose is to answer this
question.

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
and colour-blindness. Returned and voided loans are excluded. Nothing
advisory, diagnostic or speculative is ever printed in this view.

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
Sam — 4 borrowed, 1 still out, 1 overdue
  6f1c22  The Dispossessed          lent 2026-05-02   OVERDUE (98d)
  4a77e1  Solaris                   lent 2026-03-11   returned 2026-04-02
  ...
```

`who` is the only per-borrower query; `history` has no `--borrower` flag, so
there is exactly one way to ask this question. Name matching is a
case-insensitive substring, and if it matches more than one distinct borrower
string the tool lists them and exits non-zero rather than merging them.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (including "you have overdue books" — this is normal output) |
| 1 | User error: ambiguous or unmatched selector, bad date |
| 2 | Store error: directory unreadable, no writable device file |

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
drive. The adapter is a short shell-out to `git`, is inert unless the store is
a repository root, and can never fail a command.

**Commit, then pull --rebase, then push — in that order.** The previous
revision specified `pull --rebase` then `push` with no commit at all, which
was simply wrong: the pull fails against the dirty tree that a `lend` has just
created, and the push has nothing to send. Rejected as a defect rather than a
preference. Rejected alternative: commit *after* the pull, which fails for the
same reason the omission did.

**Activation requires the store to be the repository root, not merely inside
one.** Rejected alternative: activate anywhere inside a git work tree, as the
previous revision said. A user who points `BOOKLEND_STORE` at a folder inside
a notes repo or a monorepo checkout would have had every `booklend` run —
including the bare default view — rebase and push a repository they were
mid-work on. Checking for `<store>/.git` scopes the adapter to a repository
that exists because the user made it for this purpose. Staging only this
device's events file by explicit path is the second half of the same rule.

**`autosync` defaults to on.** Rejected alternative, which the reviewer
offered: require an explicit opt-in key in config. The git adapter exists to
cover the blocking multi-device requirement for a user with no cloud drive,
and a fallback that is off until you find the config key is a fallback that is
usually off — the same "the answer to the blocking requirement is inert"
failure the missing commit produced, in a different form. Running `git init`
in the store directory is already an explicit, deliberate act; that is the
opt-in, and the root-only activation rule above is what makes it safe to treat
it as one.

**A 5-second sync timeout, configurable.** Output has already been printed by
the time sync runs, so the number bounds only how long the shell prompt is
held after the user has their answer. Five seconds is long enough for a
push-pull against a small repository over a slow or newly-woken connection,
and short enough that a genuinely dead network does not feel like a hang.
`sync_timeout` makes it adjustable for anyone on a slower link.

**Sync always runs after output, for reads as well as writes.** Pulling
*before* reads would put the timeout in front of the most frequently run
command in the tool — the default view. Rejected. One rule now covers both:
local state is rendered first, the network is touched afterwards, and if the
pull brought something new the tool says so in one line and invites a re-run.
Rejected alternative: a background process, which buys a marginally nicer
first render at the cost of process lifecycle management in a tool that is
otherwise a single short script. The same choice fixes convergence for a
device used only for writing, because every command now commits and rebases
before pushing.

**No staleness or sync-health warning in any view.** An earlier revision
warned when another device's file had not changed in 14 days. At a few loans a
month a peer that has recorded nothing for six weeks is entirely normal, so
that warning would have fired permanently while sync worked perfectly — and it
printed into the same block as the overdue nudge, teaching the user to skim
exactly the output the design depends on being read. Rejected outright.
Rejected alternative: a per-run heartbeat record, which narrows the false
positive to "peer last ran" but cannot remove it — **no device can tell "peer
idle" from "peer disconnected" without a third party**, and this design
deliberately has none. `doctor` reports the raw observation, labelled as such.

**Identity is a hostname → id map, not a single recorded hostname.** The
previous revision stored one hostname and regenerated the id whenever the
current hostname differed. Under the live-synced `~/.config` that the rule was
written to protect against, that oscillates: each machine sees the other's
hostname, regenerates, and syncs the change back, so both acquire a new id on
every run, spawn a new events file, and print a warning line on every run —
violating the design's own rule against always-on advisory output. Rejected. A
map lets each machine read its own row and ignore the rest, which is stable
under sync by construction. Rejected alternative: keeping identity out of
`~/.config` entirely by deriving it from a platform machine id
(`/etc/machine-id`, `IOPlatformUUID`), which is stable but platform-specific
in a tool whose portability argument is that it has no platform code.

**A global 30-day threshold, not per-loan.** Per-loan dates would mean asking a
question at the doorstep, and the clarifier's assumption of one global
threshold went unchallenged. Configurable in one place, overridable per run.

**Default view is the no-argument invocation.** Rejected `booklend list` as
the primary path. The nudge has to be the thing that happens when you type the
tool's name, or it depends on the user remembering which subcommand shows it —
and forgetting is the problem this exists to solve.

**`history` shows everything; `who` is the only per-borrower query.** The
alternative — `history --borrower NAME` alongside `who NAME` — gives two
spellings of one question, and neither could be justified against the other.
Rejected. `history` answers "what has happened", `who` answers "what has this
person had", and the second carries the count summary that Q6's own phrasing
asks for.

**Duplicate returns resolve on `date`, not `ts`.** The rule records the day
the book came back, and `--on` lets the two orderings disagree; naming `ts`
would let a late-entered correct date lose to an early-entered wrong one.
`(ts, id)` remains as the tiebreak so the fold stays total and identical on
every device.

**Selector ambiguity is an error, not a best guess.** Rejected fuzzy
best-match. Returning the wrong book silently corrupts the one thing the tool
is for; printing two candidates costs the user one extra keystroke. Each
command's search set is enumerated in Component 5 rather than left to the
implementer.

**`amend`, `void` and `unvoid` rather than edit or delete.** Rejected in-place
editing: it breaks the append-only property that makes concurrent devices
safe. Rejected hard delete: it breaks the "returned loans stay as history"
answer. `unvoid` exists because `void` would otherwise be the one irreversible
operation in a design whose stated purpose for having correction commands at
all was to keep the user out of the raw file.

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
   ships a git adapter as a fallback — but if the answer is "none of these,
   the two machines never see each other", the multi-device requirement cannot
   be met without introducing a server, which would be a materially different
   design. **This is the single assumption most worth confirming.**

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
   which makes the divergence visible but does not fix it. Unclear whether it
   matters at tens of loans; a `booklend rename "Sam" "Sam Patel"` sweep is
   the obvious fix if it does.

6. **Nothing to import** was assumed, and Q7 was left unanswered. If there is
   a spreadsheet or notes file after all, a one-off importer is a small
   addition — but it is not designed here because no source format is known.

7. **Time zones across devices.** Loan dates are recorded as the local
   calendar date of the recording device. For a user whose devices are in one
   place this is invisible. It is stated rather than solved.

---

## Changes in this revision

**Blocking:**

- **The git adapter now commits** (Soundness FAIL 1). The sequence is
  `add <own events file>` → `commit` → `pull --rebase` → `push`, with the
  ordering stated as a correctness requirement rather than a preference. The
  previous revision's sequence would have failed on every run that produced
  data and pushed nothing on every run that did not, leaving the design's own
  fallback for the blocking multi-device requirement inert.
- **Identity is now a hostname → id map** (Soundness FAIL 2). Each machine
  reads its own row and never touches another's, so a synced `~/.config` —
  the exact case the mechanism exists for — gives a stable id per machine
  instead of a per-run identity flap, an unbounded pile of events files, and a
  warning line on every run.
- **The activation contract is stated in full** (Gaps FAIL). `autosync`
  defaults to on; the adapter runs only when `<store>/.git` exists, so a store
  that happens to sit inside an unrelated repository is never rebased or
  pushed; and staging is by explicit path to this device's own file.

**Non-blocking:** duplicate returns now resolve on the earliest `date` with
`(ts, id)` as the tiebreak; the 5-second timeout is justified and made
configurable as `sync_timeout`; `booklend sync` on a non-git store now
explains itself instead of exiting silently; and every config key is named in
one table.

**Disagreed with:** the alternative offered under Gaps of requiring an
explicit config opt-in for the git adapter. I took the other option the
reviewer offered — root-only activation — and left `autosync` on by default;
reasoning in **Decisions** and in `docs/3/dispositions.md`.
