# skills

Version-controlled agent skills for use across machines and coding agents.
The repository uses the open `SKILL.md` directory format and keeps each skill
self-contained under [`skills/`](skills/).

## Included skills

| Skill | Purpose |
| --- | --- |
| `orchestrate-olympus` | Operate the visible, recoverable delivery control plane for `dm1681/Olympus`. |
| `semantic-pr-review` | Explain a pull request as a source-verified semantic hierarchy and interactive flowchart. |

## Orchestrate Olympus

Olympus now uses a parent-resident subagent loop. The current parent agent
session — a Codex task, Claude Code session, or another supported host — is
the Orchestrator; it starts one reusable Reviewer first, uses one-shot
Planners, reuses one Worker through implementation and repair, and can create
bounded read-only Watchers for CI or other external waits. It does not depend
on host scheduled tasks. The orchestration contract is host-neutral; the
skill's `references/host-adaptation.md` maps required capabilities and
fallbacks per agent host.

The parent stays active until a true terminal state. In autonomous dispatch
mode it continues through the eligible issue frontier, including review,
repair, presentation, merge, and post-merge reconciliation, without requiring
a timer to wake it between role handoffs.

The reusable Reviewer is the final code-review authority. After its
exact-head CLEAN signal and a stable presentation audit, Olympus moves directly
to the readiness or authorized merge audit; it does not summon a hosted cloud
review by GitHub comment.

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

Olympus also treats documentation as an agent navigation layer. Planners
identify material documentation surfaces, Workers author concise contract
comments and durable docs, and the Reviewer blocks only missing or misleading
documentation that creates a material risk of agent misuse.

## Semantic PR review

`semantic-pr-review` turns one pull request into an architectural walkthrough
and a self-contained interactive flowchart instead of a file-by-file diff
summary. It pins the immutable head SHA, derives semantic layers from
responsibilities rather than directories, and records every runtime handoff
with its transferred DTOs, optionality, containers, and evidence.

The skill is deliberately host-neutral. It uses any available read-only GitHub
integration, CLI, or local Git ref, and it requires no companion skill or
visualization surface: filesystem access, Python 3, Git, and a browser are
enough. A code graph such as Graphify is used only as an optional navigation
fast path, never as a source of truth.

Every rendered code excerpt, label, and link is derived from the analyzed Git
blob by the bundled scripts rather than hand-copied:

```sh
python3 <skill-root>/scripts/scaffold_pr_explorer.py --data pr-model.json \
  --output pr-fragment.html --repo-root /path/to/repo --source-ref <head-sha>
python3 <skill-root>/scripts/render_standalone.py --fragment pr-fragment.html \
  --output page.html --title "PR 54 Dispatch Explorer"
python3 <skill-root>/scripts/verify_pr_explorer.py pr-fragment.html \
  --standalone page.html --source-repo /path/to/repo --source-ref <head-sha> --strict
```

Strict verification compares every preview byte-for-byte with its Git blob and
fails closed when a link, label, or editor target drifts from the analyzed
snapshot. Editor deep links are emitted only for a worktree whose `HEAD` and
source bytes match that snapshot exactly.

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

# Install one skill only.
./install.sh --agent all --skill semantic-pr-review

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

Clone and install from a checkout:

```sh
git clone https://github.com/dm1681/skills
cd skills
uv sync
./install.sh --agent all
```

To pin a machine to a release, check out its tag first:

```sh
git checkout v7.1.0
./install.sh --agent all
```

Subagent autonomy lasts for the active parent task. If the host agent exits,
the machine restarts, or the task is ended, start a new parent task with the
orchestrate-olympus skill (`$orchestrate-olympus` on Codex,
`/orchestrate-olympus` on Claude Code); it recovers from GitHub and the
compact checkpoint.

## Cloud sessions (agent-agnostic)

Cloud/web sessions run in a fresh, ephemeral container that does not carry your
local user-scope skills. The agent-neutral installer
[`scripts/sync-agent-skills.sh`](scripts/sync-agent-skills.sh) copies these
skills into every agent's skill root (`~/.claude/skills` for Claude Code and the
shared `~/.agents/skills` for Codex/Cursor/Copilot) so whichever agent runs the
session discovers them. A Claude Code `SessionStart` hook
([`.claude/hooks/session-start.sh`](.claude/hooks/session-start.sh), registered
in [`.claude/settings.json`](.claude/settings.json)) runs it in web sessions;
other agents can invoke the same installer from their own startup hook.

To set another repo up the same way in one step, run
[`scripts/init-repo.sh <target-repo>`](scripts/init-repo.sh) from a checkout of
this repo. It copies the machinery, vendors the skills, and scaffolds shared
`AGENTS.md` + `CLAUDE.md` guidance (`CLAUDE.md` is a one-line `@AGENTS.md` import
so both agents share one source of truth). See
[`docs/cloud-skills-sync.md`](docs/cloud-skills-sync.md).

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
