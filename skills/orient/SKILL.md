---
name: orient
description: Give the owner their bearings in a thread by answering three questions - where are we, how did we get here, where are we going - at the altitude of the goal, not of the last commands. Use when the owner asks "where are we", "how did we get here" or "where are we going", returns to a thread after a break, or asks for the thread's story or arc.
version: 1.0.0
---

# Orient

Answer three questions about this thread so the owner can hold its train of
thought. The leading word is **altitude**: each answer places the work relative
to the goal the owner came in with. The current state of files, git or tests
is evidence for a claim, never the answer itself.

## Before writing

Reread the thread from its first message. Find:

- **The goal as first stated**, and every point where it grew, narrowed or
  moved. The goal at the end is often larger than the one at the start; that
  growth is part of the story.
- **The turns in understanding**: each moment a belief changed — something
  turned out to mean less than it seemed, a result exposed a hidden cause, an
  approach was ruled out. A turn is a change in what we know, not an action
  taken.
- **What is still unsettled**: open questions, untested assumptions, the parts
  of the goal nothing has touched yet.

Done when every turn has its cause, and the goal's growth is traced from the
first message to now.

## The three answers

**Where are we?** The position relative to the goal, as it now stands: what is
settled, what is trustworthy now that was not before, and what the goal still
needs that has not been tested. Name the goal's growth when it grew.

**How did we get here?** The turns in understanding, numbered, three or four of
them. Each turn states what we believed, what changed it, and what that made
important next — so each turn explains the one after it. Compress runs of
routine actions into the turn they served.

**Where are we going?** The direction and what is unsettled on the way: the
open parts of the goal, the decisions waiting on the owner, and how the next
work connects to the larger purpose. A to-do item belongs here only as an
instance of that direction.

## Calibrating the altitude

The answer is at the right altitude when the owner could retell the thread's
logic from it alone, without having seen the commands. Test each sentence:
does it say *why* or *what it means for the goal*? A sentence that only reports
a state (`main` is at a commit, N tests pass) gets folded into a claim it
supports or cut.

Fit the length to the thread: a short thread gets a short arc. Keep concrete
details — a commit, a file, a number — where they are the evidence for a
turn; they anchor the story without becoming it.

When the owner asks for a higher altitude, place the thread inside the
project's arc the same way: the project's goal, the turns this thread added to
it, and where the project goes next.
