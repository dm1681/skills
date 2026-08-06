# Agent guide

This repository is a version-controlled collection of agent skills in the open
`SKILL.md` directory format. Each skill is self-contained under `skills/`.

## Layout

- `skills/<name>/SKILL.md` — a skill (plus optional `references/`, `scripts/`,
  `agents/`).
- `scripts/sync-agent-skills.sh` — agent-neutral installer that copies skills
  into every user-scope skill root (`~/.claude/skills` and the shared
  `~/.agents/skills`).
- `scripts/init-repo.sh` — scaffold another repo to use the cloud skills sync.
- `.claude/hooks/session-start.sh` + `.claude/settings.json` — Claude Code web
  `SessionStart` hook that runs the installer in cloud sessions.
- `install.py` / `install.sh` / `install.ps1` — installer for local machines.
  Owns root resolution, backups, receipts, and the scripted command line.
- `skills_tui.py` — Textual interface. The only interactive one; both entry
  points open it. One shell, two modes: a dashboard, and a guided flow for a
  first install. Performs installs through `install.install_one`, so the rules
  live in one place. Its colour contract is documented at the top of the file
  and is load-bearing — one hue means one thing, and red is reserved for
  failure so a healthy run contains none.
- `skills_cli.py` — the `skills` command. `setup-path` writes launcher shims
  into a `PATH` directory so `skills install NAME` works from any project and
  defaults to a repo-level install of the current directory.
- `scripts/validate_repo.py`, `tests/` — validation and unit tests.

## Working in this repo

- Environment: `uv sync --locked` (Python 3.12 via uv; 3.9+ fallback).
- `textual` is the one runtime dependency, and only the dashboard needs it.
  Every scripted path must keep working without it — say so plainly instead of
  raising an `ImportError`.
- Validate skills: `uv run python scripts/validate_repo.py`.
- Run tests: `uv run python -m unittest discover -s tests`.
- Run both before committing. See `RELEASING.md` for versioning and releases.

## Cloud sessions and new repos

Cloud/web sessions start from a fresh, ephemeral container without your local
`~/.claude/skills`. Options, lightest first: enable skills on claude.ai
(auto-load, zero files), a cloud environment setup script (zero per-repo files),
or the per-repo `SessionStart` hook. Scaffold another repo with
`scripts/init-repo.sh <target-repo>`; package skills for claude.ai upload with
`scripts/package-skills.sh`. See
[`docs/cloud-skills-sync.md`](docs/cloud-skills-sync.md).

## Conventions

- `AGENTS.md` is the single source of agent guidance; `CLAUDE.md` imports it
  (`@AGENTS.md`) so Claude Code and other agents share the same content. Edit
  `AGENTS.md`, never duplicate into `CLAUDE.md`.
- Update `docs/agent-support.md` and the installer mapping together when agent
  skill-directory conventions change.

## Review agents

An agent performing a review — pull request, code, or document — announces
itself before it starts.

- Post a "review started" comment first, before reading the diff or forming any
  findings. Put it on the review target: the PR thread for a pull request, the
  issue or document thread otherwise. If the target has no comment surface, say
  it in the session output instead.
- State who is reviewing, the exact revision under review (full head SHA for a
  PR), and that findings will follow in a later comment.
- One start comment per review round. When re-reviewing after new commits, post
  a fresh start comment naming the new head SHA instead of editing the old one,
  so the thread records every round.

---

# Personal global instructions

_Merged from `~/.claude/CLAUDE.md` on 20260727-193413. These apply to all projects (not just this repo)._

## Global instructions

These apply to all projects, in addition to any project-level `CLAUDE.md`.

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
