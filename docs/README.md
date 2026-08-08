# docs

One numbered folder per round of the design cycle. Nothing here is written by
hand; `scripts/iteration.py` creates the folders and the agents write the files.

```
docs/
├── 1/
│   ├── brief-snapshot.md  your brief, frozen at the start of the run
│   ├── clarification.md   questions from the clarifier, answers from you
│   ├── definition.md      written by the designer agent
│   └── review.md          written by the reviewer agent
├── 2/
│   ├── definition.md      revised against docs/1/review.md
│   ├── dispositions.md    what the designer did with each review finding
│   └── review.md
└── 3/
    ├── definition.md
    ├── dispositions.md
    ├── review.md          Verdict: APPROVED
    └── backlog.md         written by the backlog-writer agent
```

`clarification.md` exists only in `docs/1` and is carried forward to every
later iteration — it is the single record of everything you have told the
pipeline, including answers to questions the reviewer raised later on.

The tree above is **illustrative** — it shows what a converged run looks like.
The run actually committed to this repo under `docs/1`–`docs/4` did *not*
converge: it hit the four-iteration cap with the review still asking for
changes, so there is no approved review and no `backlog.md` on disk. See
`docs/VERIFY.md` for what that run showed.

`backlog.md` appears only in the folder whose review was approved. The full
history stays on disk, so the argument that produced the final design is
readable after the fact.

Run a cycle with `/design-cycle path/to/brief.md`.