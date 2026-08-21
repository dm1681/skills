# Global agent instructions

These apply to every project on this machine, in addition to any project-level
`AGENTS.md` or `CLAUDE.md`.

**Source of truth: `global/AGENTS.md` in the dm1681/skills checkout.** If you
are reading this text as `~/.agents/AGENTS.md` or `~/.claude/CLAUDE.md`, you
are reading an installed copy. Never edit it in place — change the checkout's
`global/AGENTS.md` and rerun `./install.sh --global-instructions`, because an
in-place edit is backed up and overwritten by the next install. This applies
to agents asked to "always remember" something globally: the durable place for
that instruction is the checkout, not the installed file.

Install with `./install.sh --global-instructions` (see the repo `AGENTS.md`).
`--global-instructions` (link, the default) writes pointer files that `@`-import
this one, so edits take effect without reinstalling; `--global-instructions
copy` writes the text into `~/.agents/AGENTS.md`, which then needs a reinstall
after every change.

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

## Workflows

When authoring a Workflow script, choose `model` and `effort` per `agent()`
call to match that agent's own task — never leave the tier to inherit by
default. Cheap mechanical stages (grep, list, transform, extract) get a small
model and `effort: 'low'`; hard reasoning stages (design judging, adversarial
verification, synthesis, root-cause analysis) get the strong model and
`effort: 'high'` or above. Record the pairing in `meta.phases` (add `model` to
the phase entry) and state the tiering in the summary so it can be overridden
before the run.

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
