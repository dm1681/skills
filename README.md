# skills

Version-controlled agent skills for use across machines and coding agents.
The repository uses the open `SKILL.md` directory format and keeps each skill
self-contained under [`skills/`](skills/).

## Included skills

| Skill | Purpose |
| --- | --- |
| `orchestrate-olympus` | Operate the visible, recoverable delivery control plane for `dm1681/Olympus`. |

## Install

Run the installer without options to open the guided setup. It walks through
scope, coding agents, skills, copy or link mode, optional Graphify setup, and a
final review before changing anything:

```sh
./install.sh
```

On Windows PowerShell:

```powershell
.\install.ps1
```

Both launchers prefer `uv`, which automatically uses or provisions Python 3.12
and syncs the locked environment. If `uv` is unavailable, they fall back to an
installed Python 3.9 or newer. A separate system Python installation is not
required when `uv` is present.

The interface adapts to narrow terminals and automatically uses plain text when
color or Unicode is unavailable. Its recommended default is a user-scoped copy
in `~/.agents/skills`, the shared location supported by Codex, Cursor, and
GitHub Copilot.

Passing installer options keeps the command non-interactive, which makes it
safe for scripts and CI. Use `--interactive` to open the wizard with preset
options, or `--non-interactive` to explicitly suppress it.

Install for every supported agent family. This writes one shared copy to
`.agents/skills` and one Claude-specific copy to `.claude/skills`:

```sh
./install.sh --agent all
```

Useful options:

```text
--agent universal|codex|cursor|copilot|claude|all
--scope user|project
--project-dir PATH
--skill NAME                 repeatable; defaults to all skills
--mode copy|link             copy is the cross-platform default
--graphify                   install/upgrade Graphify and register its skill
--interactive                force the guided setup wizard
--non-interactive            never prompt; useful for scripts and CI
--no-color                   disable interactive terminal colors
--target PATH                override the resolved skills directory
--force                      replace an existing differing skill after backup
--dry-run
--list
```

Examples:

```sh
# Install all skills for Claude Code.
./install.sh --agent claude

# Install shared skills into a repository.
./install.sh --scope project --project-dir /path/to/repo

# Link a checkout so local edits are immediately visible to Codex/Cursor/Copilot.
./install.sh --mode link --force

# Preview an update without changing files.
./install.sh --agent all --force --dry-run

# Install this collection plus Graphify for shared agents and Claude Code.
./install.sh --agent all --graphify

# Install both into one project's Codex skill directory.
./install.sh --agent codex --scope project --project-dir /path/to/repo --graphify
```

`uv` is recommended; Python 3.9 or newer can be used as a fallback. Existing
differing installations are never overwritten silently. With `--force`, the
old directory is moved into an adjacent `.skills-backups/` directory (outside
the scanned skills root) before the new version is installed.

### Optional Graphify installation

`--graphify` is an explicit opt-in to third-party software installation. It
requires [`uv`](https://docs.astral.sh/uv/) and runs:

```sh
uv tool install --upgrade graphifyy
graphify install --platform <selected-platform>
```

The package is `graphifyy` (two “y” characters); the installed command is
`graphify`. Project-scoped installs add `--project`. The installer uses
Graphify's generic `agents` platform for the shared `.agents/skills` target and
uses the explicit `codex`, `cursor`, `copilot`, or `claude` platform when that
agent was selected. See [`docs/graphify.md`](docs/graphify.md) for the exact
command matrix and boundaries.

## Sync on another machine

For this private repository, authenticate GitHub CLI and install from a clone:

```sh
gh auth login
gh repo clone dm1681/skills
cd skills
uv sync
./install.sh --agent all
```

To pin a machine to a release, check out its tag first:

```sh
git checkout v2.0.0
./install.sh --agent all
```

## Agent directory policy

The installer deliberately prefers `.agents/skills` wherever an agent supports
it. See [`docs/agent-support.md`](docs/agent-support.md) for the path matrix and
primary documentation links.

## Develop and validate

```sh
uv sync --locked
uv run python scripts/validate_repo.py
uv run python -m unittest discover -s tests -v
```

See [`RELEASING.md`](RELEASING.md) for the version and release process.
