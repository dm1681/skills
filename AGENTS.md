# Agent guide

This repository is a version-controlled collection of agent skills in the open
`SKILL.md` directory format. Each skill is self-contained under
`skills/<name>/` — entrypoint `SKILL.md`, plus optional `references/`,
`scripts/`, and `agents/`. `install.py` (with `install.sh` / `install.ps1`
wrappers) installs them locally, `skills_tui.py` is the interactive dashboard,
`skills_cli.py` provides the PATH-callable `skills` command, and
`scripts/sync-agent-skills.sh` serves cloud sessions.

## Working in this repo

- Environment: `uv sync --locked` (Python 3.12 via uv; 3.9+ fallback).
- `textual` is the one runtime dependency, and only the dashboard needs it.
  Every scripted path must keep working without it — say so plainly instead of
  raising an `ImportError`.
- Validate skills: `uv run python scripts/validate_repo.py`. Errors fail the
  run; warnings are the skill conventions (entrypoint length, "Use when"
  trigger phrasing) — fix those too.
- Run tests: `uv run python -m unittest discover -s tests`.
- Run both before committing. See `RELEASING.md` for versioning and releases.

## Gotchas the file tree does not show

- Every install path goes through `install.install_one`, so the rules live in
  one place; the TUI never re-implements install logic.
- The TUI's colour contract (documented at the top of `skills_tui.py`) is
  load-bearing: one hue means one thing, and red is reserved for failure, so a
  healthy run contains none.
- The dashboard separates `YOUR SKILLS` (this checkout's own, diffable,
  installed as copy or link) from `EXTERNAL TOOLS` (placed by their own CLI;
  they honour `--scope` but not `--mode`). Register a new external tool in
  `install.EXTERNAL_TOOLS` and wire it in `SkillsApp.external_installers`; a
  test pins the two together.

## Cloud sessions and new repos

Cloud/web sessions start from a fresh container without your local skills.
Options, lightest first: enable skills on claude.ai, a cloud environment setup
script, or the per-repo `SessionStart` hook (scaffold one with
`scripts/init-repo.sh <target-repo>`). See
[`docs/cloud-skills-sync.md`](docs/cloud-skills-sync.md).

## Global (user-level) instructions

`global/AGENTS.md` holds instructions that apply to every project, not just
this repo. Installing them is opt-in and writes two pointer files that chain
back here, so this checkout stays the single source of truth:

    ~/.claude/CLAUDE.md  ->  ~/.agents/AGENTS.md  ->  <repo>/global/AGENTS.md

Install with `./install.sh --global-instructions`; both pointer files are
backed up before being replaced. Use `--global-instructions copy` for agents
that do not resolve `@path` imports and for machines without this checkout.
The `SessionStart` sync script honours `AGENT_GLOBAL_INSTRUCTIONS=link|copy`,
forcing `copy` when it installs from a temporary clone.

## Conventions

- `AGENTS.md` is the single source of agent guidance; `CLAUDE.md` imports it
  (`@AGENTS.md`) so Claude Code and other agents share the same content. Edit
  `AGENTS.md`, never duplicate into `CLAUDE.md`.
- Update `docs/agent-support.md` and the installer mapping together when agent
  skill-directory conventions change.

## Review agents

An agent performing a review — pull request, code, or document — announces
itself before it starts. Post a "review started" comment on the review target
before reading the diff or forming any findings (or say it in the session
output when the target has no comment surface), stating who is reviewing, the
exact revision under review (full head SHA for a PR), and that findings will
follow in a later comment. One start comment per review round; when
re-reviewing after new commits, post a fresh start comment naming the new head
SHA instead of editing the old one, so the thread records every round.
