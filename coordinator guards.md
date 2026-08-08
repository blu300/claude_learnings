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
   Real work, and never airtight — there are many ways to write a file from a
   shell, and a guard that lists them is always one trick behind.
4. **Make the coordinator an agent.** The proper fix. Its own section below.

Options 1 and 2 are cheap and honest. Option 3 patches the symptom. Option 4
removes the cause.

## Option 4 — make the coordinator an agent

Everything above treats the gap as a hole to be plugged. It isn't. It is a
consequence of the coordinator being a session, so the real fix is to stop it
being one.

Move the coordinator into `.claude/agents/coordinator.md` and give it the same
kind of tool list the other four have:

```yaml
tools: Read, Write, Grep, Glob
```

No shell in the list, and `tools:` is a hard restriction — an agent cannot call
anything outside it. There is no second route to close, because there is no
second route. The existing `guard_orchestrator_write.py` then covers everything
the coordinator can actually do, and the blinding rule finally holds.

### "But agents can't talk to the human"

This is the objection that makes people drop the idea, and it does not survive
contact with the rest of the design.

It is true that Claude Code strips the ask-the-user tool from every subagent,
even when the agent's `tools:` field lists it. An agent cannot put a question to
you directly.

But **no agent in this pipeline ever does.** The clarifier does not ask you
anything — it writes its questions to a file and stops. Something else reads
that file and puts the questions to you. Passing questions through a file is
not a workaround for agents; it is how the whole system already works.

So a coordinator-agent gets questions to you exactly the way the clarifier
does:

```
coordinator-agent writes the question down, and finishes
        ↓
your session reads it and asks you
        ↓
you answer
        ↓
your session starts the coordinator-agent again, with your answer
        ↓
it carries on from where it stopped
```

Your session is still involved — it has to be, since it is the only thing that
can talk to you. But it is no longer *the coordinator*. It is a messenger
carrying text in both directions. It has no procedure to follow, no design to
be tempted by, and nothing to drift from. The judgement moves into an agent
that can be restricted; the shell access stays with something that has no
reason to write anything.

### What it costs

Not free, and worth being honest about:

- **A restart per exchange.** An agent finishes when it reports. Every question
  ends the coordinator-agent and starts it again. More round trips, more
  tokens.
- **The session still needs instructions.** Something has to tell it to relay
  rather than improvise, so a thin skill remains. Much smaller, but not zero —
  and it still has shell access. The gap narrows a great deal; it does not
  vanish.
- **Nesting.** The coordinator-agent would spawn the other four. Agents can
  spawn agents up to a depth limit and this sits inside it, but **this has not
  been tested here.** Treat it as the first thing to check before committing to
  the redesign.

### Should you do it?

If the point is to learn the concepts, no. The guard already stops the failure
that actually happens — a coordinator that forgets the rule and reaches for the
normal write tool. Getting round it takes a deliberately odd way of writing a
file, which is not what drifting looks like.

If the point were to run this unattended and trust the blinding rule, then yes.
Option 4 is the only one that makes the rule true rather than mostly true.

## The general lesson

A guard that watches by tool name only protects the tools it names.

That is fine when the thing being guarded can't reach any other tool — which is
exactly why it works for the agents. It stops being fine the moment the guarded
thing has a route the guard doesn't watch.

Before trusting a guard, ask: *what else could accomplish the same thing, and is
the guard looking at that too?*

And when the answer is "quite a few things", watching each route is the losing
move. Take the capability away instead — which is option 4, and which is just
the guide's first lesson coming back around: **restrict by capability, not by
instruction.** A guard that watches for misuse is always one trick behind. A
tool the agent does not have cannot be misused at all.

The irony is that this repo already knew that. It is why the four specialists
have no shell. The coordinator escaped the lesson only because it was not an
agent, and nobody re-asked the question for the one component built a different
way.

## Why this was found so late

Two rounds of review went through this repo and neither caught it. Both were
asking "does the documentation describe the guards accurately?" Neither asked
"do the guards actually hold?"

Those are different questions. The second one only came up when someone sat
down to write a test that had to break things on purpose — which is the
argument for having such a test at all.
