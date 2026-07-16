# skills

Version-controlled agent skills for use across machines and coding agents.
The repository uses the open `SKILL.md` directory format and keeps each skill
self-contained under [`skills/`](skills/).

## Included skills

| Skill | Purpose |
| --- | --- |
| `orchestrate-olympus` | Operate the visible, recoverable delivery control plane for `dm1681/Olympus`. |

Olympus now uses a parent-resident subagent loop. The current Codex task is the
Orchestrator; it starts one reusable Reviewer first, uses one-shot Planners,
reuses one Worker through implementation and repair, and can create bounded
read-only Watchers for CI or other external waits. It does not depend on Codex
scheduled tasks.

The parent stays active until a true terminal state. In autonomous dispatch
mode it continues through the eligible issue frontier, including review,
repair, presentation, merge, and post-merge reconciliation, without requiring
a timer to wake it between role handoffs.

The reusable Reviewer is the final code-review authority. After its
exact-head CLEAN signal and a stable presentation audit, Olympus moves directly
to the readiness or authorized merge audit; it does not summon Codex Cloud by
GitHub comment.

For substantive PR feedback from a person, app, or bot, the Reviewer replies in
the source thread with an evidence-based **AGREE** or **DISAGREE** assessment,
concise reasoning, and whether the item was **SENT** to the Worker as a tracked
finding. The Worker acts only on promoted findings and does not reply directly
to external commenters.

When the Reviewer agrees with feedback but keeps it out of the current Worker
lane, it evaluates whether the observation deserves durable follow-up. A
qualified item is deduplicated and created by the parent Orchestrator as a
self-contained `needs-triage` issue, then linked from the original assessment.
It is not assigned or marked `ready-for-agent`, and it cannot widen or block
the current PR.

When tracked `graphify-out/` exists and an Olympus lane changes indexed files,
the Worker runs the public incremental Graphify refresh after ordinary tests
and before the final push. The Reviewer verifies freshness, graph health,
privacy, and tracked output at that exact head. Post-merge Graphify handling is
verification-only; unexpected final-`main` drift uses a separate maintenance
lane rather than a direct write to `main`.

Olympus also treats documentation as an agent navigation layer. Planners
identify material documentation surfaces, Workers author concise contract
comments and durable docs, and the Reviewer blocks only missing or misleading
documentation that creates a material risk of agent misuse.

## Install

Run the installer without options to open the guided setup. It walks through
scope, coding agents, skills, copy or link mode, optional Graphify setup, and a
final review before changing anything. It also offers to install the Matt
Pocock engineering skills required by Olympus, with **Yes** as the recommended
default:

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

In an interactive terminal, use Up and Down to move between options, Space to
toggle or choose the focused option, and Enter to confirm. Multi-select screens
keep every checked option when you press Enter. Redirected input and terminals
without raw-key support automatically use numbered prompts instead.

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
--matt-skills                install all Matt Pocock skills required by Olympus
--no-matt-skills             preset the interactive prerequisite choice to No
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

# Non-interactively install Olympus and all required Matt Pocock skills.
./install.sh --agent all --matt-skills

# Install both into one project's Codex skill directory.
./install.sh --agent codex --scope project --project-dir /path/to/repo --graphify
```

`uv` is recommended; Python 3.9 or newer can be used as a fallback. Existing
differing installations are never overwritten silently. With `--force`, the
old directory is moved into an adjacent `.skills-backups/` directory (outside
the scanned skills root) before the new version is installed.

### Required Olympus engineering skills

Olympus orchestration uses Matt Pocock's `implement`, `tdd`, and `code-review`
workflows. The guided installer therefore asks to install the complete
[`mattpocock/skills`](https://github.com/mattpocock/skills) collection and
defaults to **Yes**. Declining is allowed so the installer never forces a
third-party download, but Olympus orchestration remains incomplete until these
skills are installed.

For scripts and CI, opt in explicitly with `--matt-skills`. This requires
Node.js 18 or newer and runs the upstream cross-agent installer non-
interactively:

```sh
npx --yes skills@latest add mattpocock/skills --skill '*' \
  --agent <selected-agent> --copy --yes
```

The upstream CLI runs inside a temporary project. This installer then copies
the discovered skills into the exact selected roots, including the preferred
user-scoped `~/.agents/skills` directory, while applying the same conflict
backup policy used for bundled skills. After installation, run
`/setup-matt-pocock-skills` once inside the Olympus repository. See
[`docs/matt-pocock-skills.md`](docs/matt-pocock-skills.md) for the agent mapping
and operational boundary.

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
git checkout v6.4.0
./install.sh --agent all
```

Subagent autonomy lasts for the active parent task. If Codex exits, the machine
restarts, or the task is ended, start a new parent task with
`$orchestrate-olympus`; it recovers from GitHub and the compact checkpoint.

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
