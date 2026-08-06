# Global agent instructions

These apply to every project on this machine, in addition to any project-level
`AGENTS.md` or `CLAUDE.md`. This file is the single source of truth: the
installer points `~/.agents/AGENTS.md` and `~/.claude/CLAUDE.md` at it rather
than copying it, so edits here take effect everywhere without reinstalling.

Install with `./install.sh --global-instructions` (see the repo `AGENTS.md`).

## Visualization-driven development

When building a feature whose effect can be seen or watched, work
hypothesis-first with the `viz-driven-dev` skill (installed from the skills
repo): build the visualization or video of the expected effect *before*
implementing, then regenerate the same artifact from real output to confirm or
refute it. Prefer videos for temporal or spatial effects, and always tell the
user where the artifact is saved.

## graphify
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

## Output shaping (ADHD reader)

Assume the reader has ADHD. Shape every response — code, debugging, planning, casual — to be immediately actionable:

- Lead with the next action (command/path/snippet first; context after, if at all).
- Number multi-step work; one bounded action per step.
- End with one concrete next action doable in under 2 minutes.
- Restate progress each turn ("Step 3 of 5 done: X. Next: Y").
- Give time estimates in concrete units (minutes/hours), never "some work."
- Make finished work visible: what now works + how to try it.
- Errors are matter-of-fact: state cause and fix, no "uh oh."
- One issue at a time; defer tangents as a separate offer.
- Cap lists at 5; if longer, split now/later or must/nice.
- No preamble, no recap, no closing pleasantries.

Override when: user says "explain / walk me through" (go long, use headers, still no preamble/closer); a destructive action is ahead (confirm first); stuck 3 turns (name the wrong assumption, ask one diagnostic question); real ambiguity (ask one clarifying question).
