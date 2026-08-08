# The coordinator's guard has a gap

Found while writing `LLM as judge.md`. Not fixed. Written down so it is a
decision rather than an oversight.

---

## The short version

The coordinator is supposed to be unable to write the design. It can. It just
has to use a shell command instead of the normal way of writing a file.

The four specialist agents are **not** affected. Their guards hold.

---

## What the rule was meant to do

The coordinator runs the pipeline and talks to you. It is deliberately kept
away from the design document, so that it cannot start having opinions about a
design it is supposed to be routing rather than judging.

`scripts/guard_orchestrator_write.py` enforces that. The coordinator may write
exactly three files:

- the answers into `clarification.md`
- `docs/1/brief-snapshot.md` (the frozen copy of your brief)
- `docs/.current_iteration` (which round is active)

Anything else is refused.

## Why it doesn't hold

The rule is attached to two tools — the ones Claude normally uses to write and
edit files. It watches those and nothing else.

A shell command is a third way to write a file, and the rule never looks at it.
So this is refused:

```
Write to docs/1/definition.md          -> blocked
```

and this is not:

```
echo "..." > docs/1/definition.md      -> allowed, silently
```

Same outcome, different route, no guard on the second route.

## So what can the coordinator actually do?

Anything the shell can do, to any file your user account can touch. Not just
the design document — it could create files anywhere in the project, overwrite
existing ones, or delete them. The guard is simply not in the path.

That is broader than "it might peek at the design". The guard's *purpose* is
narrow; the gap around it is not.

## Why the agents are fine

This is worth being clear about, because it is the same guard design and it
works there.

Each specialist agent declares:

```yaml
tools: Read, Write, Grep, Glob
```

There is no shell in that list, and `tools:` is a hard restriction — the agent
cannot call anything outside it, whatever its prompt says. So there is no
second route for an agent to take. Their guard only needs to cover the two
tools they actually have.

The coordinator is different because it is a *skill*, and a skill's
`allowed-tools:` does not restrict anything. It pre-approves tools so they
don't prompt; it does not take any tool away. The coordinator therefore has
whatever tools the session has, shell included.

**So the gap is not really a bug in the guard script. It is what happens when
a restriction that works for agents is assumed to work for a skill.**

## How serious is it?

Depends entirely on whether a human is watching.

**With a human present, default permissions.** An unexpected shell command
normally asks your approval first. You would see it and could say no. The
permission system covers for the guard.

**Unattended.** No one to ask, nothing to decline. The guard is the only thing
standing there, and it isn't looking at the shell. This is the case the guards
exist for.

**One thing that needs checking.** The skill pre-approves two shell commands so
they don't prompt:

```
allowed-tools: Bash(python3 scripts/iteration.py *) Bash(echo *)
```

`Bash(echo *)` may well match `echo "..." > docs/1/definition.md`, since that
is still an `echo` command. If it does, the coordinator can write any file with
**no guard and no permission prompt**, even with a human sitting there.

I have not tested this. It is a reasonable reading of how the matching works,
not an observed fact. It should be one of the first things the live-fire test
checks.

## What would fix it

Roughly in order of effort:

1. **Say so in the guide.** Write down that the blinding rule covers the normal
   write tools and not the shell. Costs nothing, and an honest limit beats a
   guarantee that isn't true.
2. **Narrow the pre-approval.** Drop `Bash(echo *)` — it exists for convenience
   and it is the widest thing in the list.
3. **Cover the shell in the guard.** Add `Bash` to what the rule watches and
   have the script inspect the command for redirects into files it protects.
   This is real work and will never be airtight — there are many ways to write
   a file from a shell.

Option 3 is the only one that closes it, and it closes it imperfectly. Options
1 and 2 are cheap and honest.

## The general lesson

A guard that watches by tool name only protects the tools it names.

That is fine when the thing being guarded can't reach any other tool — which is
exactly why it works for the agents. It stops being fine the moment the guarded
thing has a route the guard doesn't watch.

Before trusting a guard, ask: *what else could accomplish the same thing, and is
the guard looking at that too?*

## Why this was found so late

Two rounds of review went through this repo and neither caught it. Both were
asking "does the documentation describe the guards accurately?" Neither asked
"do the guards actually hold?"

Those are different questions. The second one only came up when someone sat
down to write a test that had to break things on purpose — which is the
argument for having such a test at all.
