# skills

Version-controlled agent skills for use across machines and coding agents.
The repository uses the open `SKILL.md` directory format and keeps each skill
self-contained under [`skills/`](skills/).

## Included skills

| Skill | Purpose |
| --- | --- |
| `orchestrate-olympus` | Operate the visible, recoverable delivery control plane for `dm1681/Olympus`. |

## Install

The default install is user-scoped and uses `~/.agents/skills`, the shared
location supported by Codex, Cursor, and GitHub Copilot:

```sh
./install.sh
```

On Windows PowerShell:

```powershell
.\install.ps1
```

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
```

Python 3.9 or newer is required. Existing differing installations are never
overwritten silently. With `--force`, the old directory is moved into an
adjacent `.skills-backups/` directory (outside the scanned skills root) before
the new version is installed.

## Sync on another machine

For this private repository, authenticate GitHub CLI and install from a clone:

```sh
gh auth login
gh repo clone dm1681/skills
cd skills
./install.sh --agent all
```

To pin a machine to a release, check out its tag first:

```sh
git checkout v0.1.0
./install.sh --agent all
```

## Agent directory policy

The installer deliberately prefers `.agents/skills` wherever an agent supports
it. See [`docs/agent-support.md`](docs/agent-support.md) for the path matrix and
primary documentation links.

## Develop and validate

```sh
python3 scripts/validate_repo.py
python3 -m unittest discover -s tests -v
```

See [`RELEASING.md`](RELEASING.md) for the version and release process.
