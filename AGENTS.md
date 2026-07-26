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
- `install.py` / `install.sh` — guided/CLI installer for local machines.
- `scripts/validate_repo.py`, `tests/` — validation and unit tests.

## Working in this repo

- Environment: `uv sync --locked` (Python 3.12 via uv; 3.9+ fallback).
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
