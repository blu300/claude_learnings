# Clarification

Brief: docs/1/brief-snapshot.md

## Assumptions I am making unless told otherwise
- Exactly one user — you. No accounts, no login, no sharing, no roles.
- Volumes are small: tens of books, a handful of open loans, a few loans a month. Nothing needs to scale.
- A loan record is: book title, borrower name, date lent. Everything else is optional.
- Borrower names are free text typed by you, not linked to a phone contact list or address book.
- Recording a return is a single action, and returned loans stay visible as history rather than being deleted.
- "Overdue" is decided by one threshold measured in days since the loan started, the same for every book.
- The nudge is something you see when you open the app (a badge, a highlighted row) — not something that arrives unprompted while the app is closed.
- Books are only entered when they are lent; there is no separate catalogue of your whole shelf.
- No ISBN scanning, cover images, Goodreads/library API lookup, or import from an existing list.
- Only books. Not DVDs, tools, or anything else you might lend.
- Only books you lend out. Tracking books you have borrowed from others is out of scope.
- Data lives in one place under your control; there is no requirement for it to sync between devices.
- No existing data anywhere needs migrating in.

## Questions
1. [blocking] What are you actually using — a phone app you tap while handing the book over, a web page, a desktop app, or a command-line tool? This one answer changes almost everything downstream.
2. [blocking] How should the nudge reach you: a notification/email that arrives on its own, or simply an "overdue" section you see when you next open the thing? The first needs a scheduler and a delivery channel; the second needs neither.
3. [blocking] Do you want a record of your whole shelf (books exist first, loans reference them), or only records of books that are currently or previously lent out?
4. [blocking] Does this need to work on more than one device — e.g. record a loan on your phone, review it on a laptop — or is a single device with local data fine?
5. [useful] How long is "a long time" before a book counts as overdue: 30 days, 60, 90, or something you set per loan?
6. [useful] When a book comes back, do you want the loan kept as history ("Sam has borrowed four books"), or is deleting it fine?
7. [useful] Are you tracking anything today — a notes app, spreadsheet, or paper list — that has data you would want to start from?
8. [useful] Beyond title and borrower, is there anything you actually want to capture at lending time (a note, an expected return date, a photo), or is fewer fields better?
9. [useful] Should you ever be able to nudge the borrower directly (a prefilled text or email), or is the reminder purely for you?
10. [useful] What would tell you this works — e.g. "a loan is recorded in under 15 seconds without leaving the doorstep" and "no book has been out longer than my threshold without me knowing"?
11. [useful] What happens if the data is lost — is a manual export/backup you can copy somewhere enough, or does losing it matter enough to design around?
12. [useful] Is there a deadline or occasion driving this, or anything already decided (a language, a hosting arrangement, a tool you want to reuse) that the design must fit into?

## Answers

_Answered by the orchestrator acting as a stand-in for the human, for a test
run of the pipeline. Recorded here as if from the human._

1. A command-line tool, run in a terminal.
2. An "overdue" section shown when the tool is run. No scheduler, no
   notifications that arrive on their own.
3. Loans only. Books are entered when they are lent; there is no separate
   catalogue of the whole shelf.
4. Multi-device. A loan recorded on one machine must be visible on another.
5. Unanswered — the designer should pick a sensible default threshold and say
   what it chose.
6. Keep returned loans as history.
7. Unanswered.
8. Unanswered — fewer fields is preferred unless the design needs more.
9. No. The reminder is purely for the owner.
10. Recording a loan takes one short command, and no book is overdue without
    it being visible on the next run.
11. A manual export the user can copy elsewhere is enough.
12. Unanswered. No deadline and no pre-decided technology.
