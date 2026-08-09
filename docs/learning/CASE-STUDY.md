# Case study — the day the guards didn't load

Everything earlier in the learning path proves the guard *scripts* are
correct: the unit tests feed them fake inputs, `verify_hooks.py` shows them
deciding, and the recorded run shows the pipeline producing files. This
document is about the thing none of that can prove — whether Claude Code
actually *runs* the guards — and about the day it silently didn't.

It is written to be read after the rest of the path. The full forensic
record, with timestamps, verbatim quotes and every dead-end theory, is in
[`hook_error.md`](../../hook_error.md) at the repo root; this is the
readable version, and the lessons.

---

## What happened

The live-fire test (`LLM as judge.md`, the optional capstone) was run for
real: a session executed the pipeline, then deliberately broke each rule to
prove each guard fires. The result looked like a disaster — five of the
seven protections never reacted. Files that should have been refused were
written. Warnings that should have appeared didn't. A separate judge
session read the evidence and concluded: *would not trust these guards
unattended.*

Here is the uncomfortable part: **the scripts were fine.** Every unit test
passed before, during and after. The wiring — which script is attached to
which event — was correct too. What failed was the step you can't see:
Claude Code never *loaded* the guards into the session. A guard that is
never loaded produces no block, no warning, no error, and no log line. From
the outside, it looks exactly like a polite run where nothing needed
blocking.

That sentence is the whole case study. Everything else is how we found it,
why it took a day, and what changed so it cannot hide again.

## The one clue that mattered

Every guard in this repo writes one line to `docs/hook-audit.log` for every
decision it makes — including **allow** decisions. That design choice, made
long before this incident, turned out to be the key to it.

In the failed run, the four agents wrote four legitimate files. A working
write-guard logs an `allow` line for each. The log had **zero** — not zero
blocks, zero *anything* from the agents' guards. Nothing was declining to
block; nothing was running at all.

> **Lesson 1 — silent failure looks identical to success.** A protection
> that never loads behaves exactly like a protection that was never
> provoked. You cannot tell them apart from the session transcript. You
> need a mechanical record the protection itself writes — and it must
> record the boring "allow" decisions, because *those* are what prove it
> was alive.

## The wrong turns

Four theories were proposed over the day, each stated with too much
confidence, each killed by the next piece of evidence: the CLI is too old
(it wasn't); the folder isn't trusted (it was); there are two trust
entries, one broken (there was one, fine); it's the VS Code launch method
(closest — but the "proof" tested the wrong launch method).

The repeated mistake had a shape worth naming: things proven in a clean
Linux container were presented as if proven on the actual Windows laptop.
The *mechanism* was real — in the container, an untrusted folder really
does silently skip agent hooks — but that never proved it was what happened
on *this* machine, whose folder was trusted.

> **Lesson 2 — "it can happen" is not "it is what happened."** Reproducing
> a mechanism somewhere else tells you the mechanism exists. Only evidence
> from the failing machine tells you it's your root cause.

## The actual causes (there were three)

**1. The main one: a name-matching bug in Claude Code (reported by others,
never fixed).** Claude Code only loads a project's agent guards after you
have trusted the project folder, and it looks the trust record up by the
folder's path *as text*. On this machine the trust record says
`C:\Users\...` — capital C. Launching Claude Code from the VS Code side
panel hands it the same folder as `c:\Users\...` — small c. To an
exact-text comparison those are different folders, so Claude Code silently
concluded "not trusted" and skipped every agent guard. Sessions launched
from PowerShell got the capital C and worked. Same machine, same folder,
same config — the drive letter's *case* decided whether the guards existed.
(GitHub issues #45195, #46586 and #18122 describe this; all closed
unfixed.)

**2. A quieter one: one guard was plugged into a socket that doesn't
exist.** The check that runs when an agent finishes ("did you actually
write your file?") was declared in the *skill's* configuration — a location
the documentation doesn't support for that event. The supported place is
each *agent's* own file. Result: that check had never run in **any**
session, working or failing. Nobody noticed, because — see Lesson 1 — a
check that never runs is silent, and its audit lines were simply absent
from every log anyone had ever looked at.

**3. A self-inflicted one, found during the cleanup:** running the unit
tests wrote junk lines into the real `docs/hook-audit.log`, because three
test files didn't isolate themselves properly. The evidence file the whole
methodology depends on was being polluted by the test suite itself.

> **Lesson 3 — audit your wiring against the documentation, not against
> your intentions.** Configuration that is *ignored* fails exactly like
> configuration that is *wrong*, minus the error message.

## What changed in this repo

Each fix maps to a way the failure hid:

- **The mis-socketed check moved to the documented location** — a `Stop`
  hook in each agent's file — and got smarter on the way: each agent must
  now produce *its own* file, so an agent that writes nothing is caught
  even when the folder already contains other agents' files.
- **A second, independent layer of guards was added** in
  `.claude/settings.json` (`scripts/guard_docs_writes.py` and copies of the
  two after-write validators). Hooks declared there load in *every*
  session, however it was launched — so even if the trust lookup fails
  again, the most important rules still hold. This layer is deliberately
  weaker: it cannot know *which* agent is writing (that knowledge only
  exists in the per-agent wiring), so it enforces only the agent-independent
  rules — right folder, right iteration, no touching the iteration cursor
  or the audit log itself. Defense in depth means accepting that the backup
  layer catches less, and writing down exactly what it misses.
- **The guards now log their "nothing to check" decisions too.** Several
  code paths used to exit silently when there was nothing to do — which is
  indistinguishable from never having run. Now every path leaves a line.
- **The expensive test got a cheap tripwire.** Step 0 of the live-fire
  runner now performs one small delegation and greps the audit log for a
  line from *each* hook class before the real test spends anything — and
  it records `claude --version` and how the session was launched, because
  the single fact that would have settled the whole investigation (which
  CLI build the failing sessions ran) was never captured and is now
  unknowable forever.
- **The tests isolate themselves** and can no longer pollute the real
  audit log.
- **Windows got treated as the real target it is.** A review of the new
  guard found that on Windows's case-insensitive filesystem,
  `docs/.Current_Iteration` *is* `docs/.current_iteration` — so an
  exact-text comparison in the new guard was a working bypass. The same
  class of bug as the root cause, in code written to defend against the
  root cause, caught before it shipped. Comparisons are now
  case-insensitive.

> **Lesson 4 — record the environment before you need it.** Version
> numbers, launch context, timestamps: capturing them costs one line at the
> start of a run. Not capturing them can cost you the answer permanently.

> **Lesson 5 — put a thirty-second check in front of every thirty-minute
> run.** The preflight converts "silent false failure, discovered after the
> money is spent" into "loud refusal upfront, naming the broken layer."

> **Lesson 6 — exact-string comparisons and case-insensitive filesystems
> are natural enemies.** The root cause was a case comparison; so was the
> bypass found in the fix. If your code compares paths as text and your
> users run Windows, fold the case first.

## What is still true

The deepest lesson survives all the fixes: **this repo's guards live or die
by a loading step that belongs to the harness, not to the repo.** The unit
tests cannot see it. Only a live session can — which is why the live-fire
test exists, why its preflight now checks every layer by name, and why the
audit log records allows and not just blocks. If you take one habit from
this case study into your own projects, take that one: make your
protections prove they are alive, on every run, in writing.
