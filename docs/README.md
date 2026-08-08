# docs

One numbered folder per round of the design cycle. Nothing here is written by
hand; `scripts/iteration.py` creates the folders and the agents write the files.

```
docs/
├── 1/
│   ├── clarification.md   questions from the clarifier, answers from you
│   ├── definition.md      written by the designer agent
│   └── review.md          written by the reviewer agent
├── 2/
│   ├── definition.md      revised against docs/1/review.md
│   └── review.md
└── 3/
    ├── definition.md
    ├── review.md          Verdict: APPROVED
    └── backlog.md         written by the backlog-writer agent
```

`clarification.md` exists only in `docs/1` and is carried forward to every
later iteration — it is the single record of everything you have told the
pipeline, including answers to questions the reviewer raised later on.

`backlog.md` appears only in the folder whose review was approved. The full
history stays on disk, so the argument that produced the final design is
readable after the fact.

Run a cycle with `/design-cycle path/to/brief.md`.