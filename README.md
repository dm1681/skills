# skills

Version-controlled agent skills for use across machines and coding agents.
The repository uses the open `SKILL.md` directory format and keeps each skill
self-contained under [`skills/`](skills/).

## Included skills

| Skill | Purpose |
| --- | --- |
| `semantic-pr-review` | Explain a pull request as a source-verified semantic hierarchy and interactive flowchart. |
| `wow-addon-dev` | Build, debug, package, and publish retail World of Warcraft addons under the taint and secret-value fences. |

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

## WoW addon development

`wow-addon-dev` covers retail World of Warcraft addons: Lua 5.1 in a sandbox,
the event and widget model, TOC manifests and SavedVariables, and the two
independent security fences — long-standing taint and combat lockdown, plus the
Midnight-era secret values that make combat state displayable but not readable.

The skill leads with verification rather than recall. It requires confirming the
live client build (`/dump select(4, GetBuildInfo())`) before writing a TOC and
checking the current patch's API changes on `warcraft.wiki.gg`, because this
domain rewrites itself every patch. Feasibility triage comes before design, so
an idea that modern retail no longer permits is rejected early instead of
half-built.

`assets/skeleton/` scaffolds a loadable addon, and the bundled checker validates
the manifest before the client ever launches:

```sh
python3 <skill-root>/scripts/check_toc.py path/to/AddOns/MyAddon
```

It catches folder/TOC name mismatches, malformed Interface versions, missing
listed files, and invalid SavedVariables names. It cannot tell you whether the
Interface number is current — only the in-game build check can.

## Install

Run the installer without options to open the dashboard:

```sh
./install.sh
```

Every skill appears as a row carrying its live state — not installed, up to
date, or differing from this checkout — beside a sidebar holding the view
filter, the destination, and copy/link mode. Keys: `↑`/`↓` to move, `Space` to
select, `Enter` for the `SKILL.md` preview, `V` to filter the list, `S` to
switch between a repo-level and a machine-wide install, `M` between copy and
link, `I` to install, `G` for the guided flow, `Q` to quit. A skill that already
exists and differs is never replaced silently: it asks first, then moves the old
copy into an adjacent `.skills-backups/` directory.

### Guided mode

Installing into a destination for the first time — one with no
`.dm1681-skills.json` receipt — opens a four-step flow instead: where to
install, which skills, copy or link, then a review that spells out every write
and backup and states plainly that nothing has been written yet. The sidebar
becomes a step rail; nothing else about the layout moves. Press `G` to switch
modes at any time, or force either with `skills install --guided` /
`--no-guided`.

### What the colours mean

Colour is information, not decoration, and one hue means one thing everywhere:

| Hue | Meaning |
| --- | --- |
| mauve | your selection, focus, and the active step — never data |
| blue | an additive install; nothing existing is lost |
| peach | a replacement; the old copy is backed up first |
| green | already identical to this checkout; nothing will happen |
| teal | a location — paths, roots, scope |
| yellow | allowed, but probably not what you want |
| red | failure, so a healthy run is provably red-free |

A skill's state is painted in the colour of the *consequence* of selecting it,
so the hue carries unchanged from the state pill to the action verb to the
review step. Counting the peach tells you how many overwrites are queued.

The dashboard needs a real terminal. A pty-based shell — Git Bash or mintty on
Windows — hides the terminal from Python, so run `install.ps1` from PowerShell
or Windows Terminal there. A bare run with no usable terminal installs nothing
and explains what to pass instead, rather than defaulting to every skill in
every root.

Skills that declare `global_default: false` in their `agents/openai.yaml` are
labelled `repo-level only` on their tile. `wow-addon-dev` is one: a narrow,
domain-specific skill should not reach every unrelated session.

On Windows PowerShell:

```powershell
.\install.ps1
```

Both launchers prefer `uv`, which automatically uses or provisions Python 3.12
and syncs the locked environment — including Textual, which the dashboard needs.
If `uv` is unavailable, they fall back to an installed Python 3.9 or newer;
without Textual there, naming skills on the command line still works and the
installer says so rather than failing with a traceback.

The default destination is a user-scoped copy into every skill root:
`~/.agents/skills`, the shared location supported by Codex, Cursor, and GitHub
Copilot, and `~/.claude/skills`, which Claude Code reads instead of the shared
directory.

Passing installer options keeps the command non-interactive, which makes it
safe for scripts and CI. Use `--interactive` to open the dashboard with preset
options, or `--non-interactive` to explicitly suppress it. `--graphify`,
`--matt-skills`, and `--target` are scripted-only; combining them with
`--interactive` is an error rather than a silent no-op.

### Run it from any directory

Install the launcher once and the collection follows you into every project:

```sh
./install.sh --skill NAME        # or open the dashboard first
skills setup-path                # writes ~/.local/bin/skills (+ skills.cmd)
skills setup-path --add-path     # if that directory is not on PATH yet
```

From then on, in any repository:

```sh
cd ~/code/some-project
skills                    # dashboard, targeting this directory
skills install NAME       # repo-level install, no paths to type
skills install NAME --user  # machine-wide instead
skills list               # what this collection ships
skills where              # path to the checkout the shims point at
```

`skills install` defaults to a repo-level install of the current working
directory, writing `./.agents/skills/NAME` and `./.claude/skills/NAME`. Naming
no skill opens the dashboard; naming one skips it entirely, so the command stays
usable in scripts and over SSH. Installing a `global_default: false` skill with
`--user` prints a note first, since those are meant to stay repo-level.

On Windows the shims are written as an extensionless `skills` for Git Bash and
`skills.cmd` for PowerShell and cmd.exe. `--add-path` edits the current user's
registry environment rather than calling `setx`, which silently truncates any
`PATH` longer than 1024 characters. Re-run `skills setup-path` after moving the
checkout: each shim hard-codes the path it was generated from.

Install for every supported agent family. This is the default, and writes one
shared copy to `.agents/skills` and one Claude-specific copy to
`.claude/skills`:

```sh
./install.sh
```

Narrow the install with `--agent` when you want only one root. Note that a
shared-only install is invisible to Claude Code, which reads `.claude/skills`
and never `.agents/skills`:

```sh
./install.sh --agent universal
```

Useful options:

```text
--agent universal|codex|cursor|copilot|claude|all
                             defaults to all: every skill root, so the
                             install is visible to whichever agent you use
--scope user|project         scripted installs only; the dashboard switches
                             scope with the `s` key instead
--project-dir PATH
--skill NAME                 repeatable; defaults to all skills
--mode copy|link             copy is the cross-platform default
--matt-skills                install all Matt Pocock skills for chosen agents
--no-matt-skills             skip Matt Pocock skills (the default)
--graphify                   install/upgrade Graphify and register its skill
--global-instructions [link|copy]
                             install global/AGENTS.md as user-level guidance
                             in ~/.agents/AGENTS.md and ~/.claude/CLAUDE.md
--interactive                force the dashboard open
--non-interactive            never open it; useful for scripts and CI
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
./install.sh --skill semantic-pr-review

# Install shared skills into a repository.
./install.sh --scope project --project-dir /path/to/repo

# Link a checkout so local edits are immediately visible to Codex/Cursor/Copilot.
./install.sh --mode link --force

# Preview an update without changing files.
./install.sh --agent all --force --dry-run

# Install this collection plus Graphify for shared agents and Claude Code.
./install.sh --agent all --graphify

# Also install the Matt Pocock engineering skills (third-party opt-in).
./install.sh --agent all --matt-skills

# Install both into one project's Codex skill directory.
./install.sh --agent codex --scope project --project-dir /path/to/repo --graphify
```

### Global (user-level) instructions

Skills are per-task; `global/AGENTS.md` holds guidance that applies to every
project. Installing it is opt-in and writes two small pointer files, so this
checkout stays the single source of truth:

    ~/.claude/CLAUDE.md  ->  ~/.agents/AGENTS.md  ->  <repo>/global/AGENTS.md

```sh
# Point both home files at this checkout; later edits apply without reinstalling.
./install.sh --global-instructions

# Write the text into ~/.agents/AGENTS.md instead, for agents that do not
# resolve @path imports or machines without this checkout.
./install.sh --global-instructions copy
```

Whatever is already at those paths is moved into `~/.skills-backups/` first,
and reruns that would not change anything report `unchanged`.

`uv` is recommended; Python 3.9 or newer can be used as a fallback. Existing
differing installations are never overwritten silently. With `--force`, the
old directory is moved into an adjacent `.skills-backups/` directory (outside
the scanned skills root) before the new version is installed.

### Optional Matt Pocock engineering skills

Matt Pocock's [`mattpocock/skills`](https://github.com/mattpocock/skills)
collection provides `implement`, `tdd`, and `code-review` workflows. No skill in
this collection requires them, so the dashboard does not offer to fetch them and
never prompts for a third-party download.

Opt in explicitly with `--matt-skills`. This requires Node.js 18 or newer and
runs the upstream cross-agent installer non-interactively:

```sh
npx --yes skills@latest add mattpocock/skills --skill '*' \
  --agent <selected-agent> --copy --yes
```

The upstream CLI runs inside a temporary project. This installer then copies
the discovered skills into the exact selected roots, including the preferred
user-scoped `~/.agents/skills` directory, while applying the same conflict
backup policy used for bundled skills. After installation, run
`/setup-matt-pocock-skills` once inside the target repository. See
[`docs/matt-pocock-skills.md`](docs/matt-pocock-skills.md) for the agent mapping
and operational boundary.

### Optional Graphify installation

Graphify is reachable two ways: as a row in the dashboard's **External tools**
group, or with `--graphify` for a scripted run. Both are opt-in and both end up
in the same place; the flag exists so CI never has to open a UI.

The dashboard lists it apart from this collection's own skills on purpose. A
bundled skill is a folder in this checkout, so the dashboard can diff it and
tell you whether it is up to date. An external tool is somebody else's package:
it follows your scope choice, ignores copy/link because its own installer
decides the shape, and reports only `NOT INSTALLED` or `PRESENT` — never `UP TO
DATE`, which would be a guess. Selecting one that is already present offers
`update`, since re-running its installer upgrades rather than doing nothing.
What it writes is not included in the review screen's write and backup counts,
and the review says so.

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
git checkout v8.1.0
./install.sh --agent all
```

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
