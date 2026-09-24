---
name: implement
description: "Interactive sessions only. Implement a piece of work from a spec or a set of tickets, either in one pass or section by section with the user following along. Use when building the work described by a spec, a ticket, or an agreed plan."
disable-model-invocation: true
version: 1.1.0
---

<!--
A fork, not a vendored copy. Upstream is mattpocock/skills
`skills/engineering/implement/SKILL.md`, forked at v1.2.3 (6acc160). This
collection supersedes that name on purpose, through the `SHADOWED_SKILLS`
entry in install.py: `--matt-skills` fetches and verifies upstream's copy and
then does not install it, so this one owns the name in every root without the
two contesting it on every update.

The pacing section below is the only addition; the rest is upstream's. The
install checks upstream's bytes against the hash recorded in that entry, so a
pin that moves over a changed upstream stops rather than passing silently --
reconcile the two and update the fork and the entry together.
-->

Implement the work described by the user in the spec or tickets.

## Ask how to pace it, before writing any code

Ask the user which they want:

- **All at once** — build the whole thing, then report on it.
- **Section by section** — build one section, stop, explain what it does and
  why it is shaped that way, and wait for the user before starting the next.

Ask once, at the start. Don't ask again unless the user changes their mind.

Section by section exists so the user can follow the work and understand what
is being created, so a section has to end somewhere there is something to
understand: a working slice, not a half-written file. Say what you are about
to build before building it, and what actually changed after.

## Then

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use /code-review to review the work.

Commit your work to the current branch.
