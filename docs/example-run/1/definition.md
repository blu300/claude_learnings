# Definition: Book Lending Tracker

Criteria: `docs/1/clarification.md` (Answers section)
Brief: `docs/1/brief-snapshot.md`

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
can be recorded in one line at the doorstep.

### 2. Event store

**Responsibility.** Locate the store directory; read and merge every
`*.jsonl` file in it into a single time-ordered event stream; append new
events to this device's own file.

**Boundaries.** Knows about lines, files and event ordering. Knows nothing
about loans, borrowers or overdueness — it deals in opaque event records.
Appends are a single `write()` in `O_APPEND` mode of one newline-terminated
line, which is atomic against other processes on the same machine for the line
sizes involved. Malformed lines (a truncated write from a killed process, a
sync artefact) are skipped with a warning on stderr rather than aborting the
run — a corrupt line must never make the rest of the loans invisible.

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
and a single flag, so being wrong about it is cheap.

### 5. Selector resolution

**Responsibility.** Turn what the user types — `booklend back dispossessed`,
`booklend back 6f1c` — into exactly one loan.

**Boundaries.** Matches a short-id prefix first, then a case-insensitive
substring of the title, then of the borrower name, searching **open loans
only** for return. If zero or more than one loan matches, it prints the
candidates and exits non-zero. It never guesses. This is the component that
keeps "one short command" from becoming "one short command that returned the
wrong book".

### 6. Sync adapter (optional, git only)

**Responsibility.** If — and only if — the store directory is inside a git
work tree, best-effort `pull --rebase` before a read command and
`add/commit/push` after a write command.

**Boundaries.** It is never load-bearing. The local write always lands and is
always confirmed to the user **before** sync is attempted. Sync runs with a
short timeout (5 seconds); any failure prints one warning line and exits the
command successfully. `--no-sync` skips it. If the store is not a git repo the
adapter does nothing at all and never mentions itself. Users on Dropbox/iCloud
/Syncthing simply never encounter this component.

### 7. Freshness reporter

**Responsibility.** Record when this device last successfully saw another
device's data, and warn in the default view when that is stale (default: 14
days).

**Boundaries.** One line of output, computed from file modification times and
the last successful sync marker. It exists because the success criterion is
"no book is overdue without it being visible on the next run" — and a device
whose sync quietly broke three weeks ago would otherwise satisfy that
criterion while showing stale truth. It warns; it never blocks.

### 8. Config and identity

**Responsibility.** Resolve the store path, overdue threshold, autosync
preference, and this device's identity.

**Boundaries.** Two locations, deliberately distinct:

- `~/.config/booklend/config.ini` — user preferences. Never synced.
- `~/.config/booklend/device` — a generated device id. **Must never live
  inside the store directory**, because a synced device id would make two
  machines write the same file and destroy the whole conflict-freedom
  argument.

### 9. Export

**Responsibility.** Emit the full loan set to stdout as JSON or CSV.

**Boundaries.** Read-only, writes to stdout only, never to a file — the user
redirects. Note that the store directory *is already* a complete, plain-text,
copyable backup; export exists for reading the data somewhere else (a
spreadsheet), which is what Q11 asks for.

---

## Data and interfaces

### Store layout

```
<store>/                      e.g. ~/Dropbox/booklend/  or  ~/git/booklend-data/
  events-laptop-3f2a.jsonl    written only by that device
  events-desk-91bc.jsonl      written only by that device
  events-laptop-3f2a (conflicted copy).jsonl   ← still read and merged
```

Resolution order for `<store>`: `--store` flag → `BOOKLEND_STORE` env →
`store` key in config → `~/.local/share/booklend` (XDG default). The default
is deliberately a *local* path: the tool works standalone out of the box, and
becomes multi-device the moment the user points it at a synced folder.

### Event records

One JSON object per line, UTF-8, no nesting beyond one level.

```json
{"id":"e-8a41...","type":"lend","ts":"2026-08-08T14:03:11Z","device":"laptop-3f2a","loan":"6f1c...","title":"The Dispossessed","borrower":"Sam","date":"2026-08-08","note":null}
{"id":"e-b2d7...","type":"return","ts":"2026-09-30T09:12:40Z","device":"desk-91bc","loan":"6f1c...","date":"2026-09-30"}
{"id":"e-04f9...","type":"amend","ts":"...","device":"...","loan":"6f1c...","fields":{"borrower":"Sam Patel"}}
{"id":"e-77c2...","type":"void","ts":"...","device":"...","loan":"6f1c...","reason":"typo"}
```

| Field | Meaning |
|---|---|
| `id` | Unique per event. Used for deduplication. |
| `ts` | UTC instant, used only for ordering. |
| `date` | Local calendar date (`YYYY-MM-DD`) — the human fact "lent on". |
| `loan` | The loan this event concerns. Generated at `lend` time. |

The split between `ts` and `date` matters: "since when" is a day in the user's
life, not an instant, and it must not shift because they lent a book at 11pm.

Four event types is the complete set. `amend` and `void` exist because an
append-only log with no correction path forces the user to edit the file by
hand, which is exactly when data gets lost.

### Fold rules

- Events sorted by `(ts, id)`. The `id` tiebreak makes the ordering identical
  on every device even when two events share a timestamp.
- Duplicate `id` → the second and later copies are ignored.
- `lend` creates the loan; a repeated `lend` for an existing `loan` is ignored.
- `amend` overwrites the named fields, later events winning.
- `return` sets the return date; if two devices both record a return, the
  **earliest** wins, because the book came back once.
- `void` hides the loan from every view. The events stay in the file.
- A `return` whose `lend` is missing is retained as an orphan and reported by
  `booklend doctor`; it is never silently dropped.

Because every event names its `loan`, clock skew between devices can only
misorder events *within* one loan, and the precedence rules above make each of
those cases deterministic anyway.

### Loan (the folded record)

`loan_id`, `short_id` (first 6 chars), `title`, `borrower`, `lent_on`,
`returned_on | null`, `note | null`, `voided`.

Derived at render time: `days_out`, `status ∈ {out, overdue, returned}`.

Four stored fields, one optional — matching the "fewer fields" preference.

### Command surface

```
booklend                                  default view: overdue, then out
booklend lend "The Dispossessed" Sam      the one short command
booklend lend "Title" Sam --on 2026-08-01 --note "hardback"
booklend back dispossessed                record a return
booklend back 6f1c22 --on 2026-09-30
booklend history [--borrower Sam] [--all]
booklend who Sam                          everything Sam has ever had
booklend amend 6f1c22 --borrower "Sam Patel"
booklend void 6f1c22
booklend export [--json|--csv]
booklend sync                             explicit git sync
booklend doctor                           store health, orphans, freshness
```

Global flags: `--store`, `--overdue-days`, `--no-sync`, `--no-color`.

### Default view

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
overdue in text as well as colour, so the signal survives piping,
`NO_COLOR`, and colour-blindness.

Returned loans are excluded from the default view and reachable through
`history` / `who`.

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
drive. The adapter is roughly thirty lines shelling out to `git`, is inert
when the store is not a repo, and can never fail a command. Rejected
alternative: auto-sync as a hard prerequisite of every command — that makes
the doorstep command depend on the network, which breaks the primary
requirement.

**Confirm the write before syncing it.** The alternative — sync, then confirm
— gives a truer confirmation but can hang for seconds while a book is being
handed over. Recording locally is the durable part; propagating is not.

**Python 3, standard library only.** Rejected Go and Rust, whose single static
binary is genuinely better for a multi-device tool, because each device would
need a build or a release pipeline for its platform. Rejected shell, which
cannot parse JSON or do date arithmetic without becoming worse than either.
Python is present on macOS and every Linux, needs no dependency resolution,
and the whole tool is a few hundred lines. Config is INI via `configparser`
rather than TOML so that older Python 3 versions work without `tomllib`.

**A global 30-day threshold, not per-loan.** Per-loan dates would mean asking a
question at the doorstep, and the clarifier's assumption of one global
threshold went unchallenged. Configurable in one place, overridable per run
with `--overdue-days`.

**Default view is the no-argument invocation.** Rejected `booklend list` as
the primary path. The nudge has to be the thing that happens when you type the
tool's name, or it depends on the user remembering which subcommand shows it —
and forgetting is the problem this exists to solve.

**Selector ambiguity is an error, not a best guess.** Rejected fuzzy
best-match. Returning the wrong book silently corrupts the one thing the tool
is for; printing two candidates costs the user one extra keystroke.

**`amend` and `void` rather than edit or delete.** Rejected in-place editing:
it breaks the append-only property that makes concurrent devices safe.
Rejected hard delete: it breaks the "returned loans stay as history" answer
and there is no other undo.

**No compaction, ever.** At a few loans a month the log reaches a few thousand
lines in a lifetime. Rejected periodic rewriting, which is the one operation
that could lose data and the only reason a device would need to modify another
device's file.

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

5. **Should a borrower's name be normalised?** Free-text names (Q, assumption
   4) mean "Sam", "sam" and "Sam Patel" are three people to `booklend who`.
   Matching is case-insensitive on substring, which covers the common case,
   but nothing merges genuine variants. Unclear whether this matters at tens
   of loans.

6. **Nothing to import** was assumed, and Q7 was left unanswered. If there is
   a spreadsheet or notes file after all, a one-off importer is a small
   addition — but it is not designed here because no source format is known.

7. **Time zones across devices.** Loan dates are recorded as the local
   calendar date of the recording device. For a user whose devices are in one
   place this is invisible. It is stated rather than solved.
