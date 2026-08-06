# Agent guide

This repository is a version-controlled collection of agent skills in the open
`SKILL.md` directory format. Each skill is self-contained under `skills/`.

## Layout

- `skills/<name>/SKILL.md` — a skill (plus optional `references/`, `scripts/`,
  `agents/`).
- `global/AGENTS.md` — user-level instructions that apply to every project,
  installed into `~/.agents/AGENTS.md` and `~/.claude/CLAUDE.md`.
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

## Global (user-level) instructions

`global/AGENTS.md` holds instructions that apply to every project, not just this
repo. Installing them is opt-in and writes two small pointer files that chain
back here, so this checkout stays the single source of truth:

    ~/.claude/CLAUDE.md  ->  ~/.agents/AGENTS.md  ->  <repo>/global/AGENTS.md

```bash
./install.sh --global-instructions
```

Both pointer files are backed up before being replaced. Use
`--global-instructions copy` to write the instruction text into
`~/.agents/AGENTS.md` instead of a reference — needed for agents that do not
resolve `@path` imports, and for machines where this checkout is not present.
The `SessionStart` sync script does the same when `AGENT_GLOBAL_INSTRUCTIONS`
is set to `link` or `copy` (it forces `copy` when it installs from a clone,
because the clone is a temporary directory).

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

