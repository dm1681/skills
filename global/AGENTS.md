# Global agent instructions

These apply to every project on this machine, in addition to any project-level
`AGENTS.md` or `CLAUDE.md`. This file is the single source of truth: the
installer points `~/.agents/AGENTS.md` and `~/.claude/CLAUDE.md` at it rather
than copying it, so edits here take effect everywhere without reinstalling.

Install with `./install.sh --global-instructions` (see the repo `AGENTS.md`).

## Visualization-driven development

When building a new feature, first ask whether a visualization could illustrate its effect — a plot, an overlay, a rendered artifact, a before/after chart, anything lookable or watchable. If one would:

1. **Build the visualization first, before implementing the feature.** Generate it against expected, synthetic, or baseline data so it cements your understanding and states an explicit *hypothesis*: what should the result look like if the feature works?
2. **Then implement** the feature.
3. **Then regenerate the same visualization for real**, against actual output, and compare it to the hypothesis to confirm or refute it.

Treat the visualization as the feature's hypothesis-and-check, not an afterthought. Prefer watchable/lookable artifacts (overlays, rendered media, charts, side-by-side before/after) over terminal tables when the effect is spatial or temporal. Tell the user where the artifact is saved so they can look at it.

### Prefer videos to convey understanding

Beyond static plots, **generate videos** (before, after, or both side-by-side) whenever they would help the user *understand* the effect — and that is most of the time, not the exception. A playhead sweeping an analysis, an overlay riding the actual footage, an animated before/after — these convey temporal and spatial behavior that a still frame cannot, and they are how the user catches errors a static artifact would hide.

- **Default to producing a video when the effect is temporal, spatial, or sequential** (signals over time, tracking/overlays on media, transitions, simulations, state evolution). Only skip it when a video genuinely adds nothing over a still (e.g. a one-shot categorical snapshot) — and say so explicitly when you skip.
- A "before" video shows the old/baseline/naive behavior; an "after" shows the new/correct behavior; **both, side-by-side or sequential, is ideal** for proving a change did what was intended.
- Make videos *honest*: label what each panel is, and if an artifact is later found to be wrong or misleading, leave it but annotate/caption it as not-entirely-correct rather than silently deleting it.
- Always tell the user the path, and surface the file so they can watch it.
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
