# Cloud skills sync (agent-agnostic)

Cloud/web coding sessions run in a fresh, ephemeral container. The repository is
cloned in, but your local user-scope skills are not — so skills you installed
with `./install.sh` on your own machine are absent. Only the agent's bundled
skills and skills committed inside the cloned repo are present.

This directory ships two pieces that close that gap:

- **[`scripts/sync-agent-skills.sh`](../scripts/sync-agent-skills.sh)** — an
  **agent-neutral** installer. When invoked, it installs these skills into every
  agent's user-scope skill directory. It has no dependencies beyond git +
  coreutils, is idempotent, and applies no guard of its own — each agent's
  startup wrapper decides when to run it.
- **[`.claude/hooks/session-start.sh`](../.claude/hooks/session-start.sh)** — a
  thin Claude Code `SessionStart` hook that runs the installer in web sessions.
  Registered for this repo in [`.claude/settings.json`](../.claude/settings.json).

## Lightest setup: no per-repo files

The hook is the per-repo route. Two options need **nothing committed to each
repo** and are usually what you want for "spin up a new repo and forget it":

### Enable skills on claude.ai (zero files, always current)

Claude Code on the web loads skills you enable on claude.ai into every cloud
session automatically. Package each skill and upload it once:

```sh
scripts/package-skills.sh          # writes dist/<skill>.zip (SKILL.md at the archive root)
```

Then in claude.ai: **Settings → Capabilities → Skills → "Upload skill"** and drag
in each `dist/<skill>.zip`. Enabled skills appear in every cloud session with no
repo files and no setup script, and update when you re-upload. This is the
lightest path when the skills are yours to enable on your account.

### Cloud environment setup script (zero per-repo files)

A setup script is attached to the **cloud environment** (configured in the
claude.ai web UI, not in any repo) and runs before Claude launches for every
session in that environment. Copy the contents of
[`scripts/cloud-setup-script.sh`](../scripts/cloud-setup-script.sh) into the
environment's **Setup script** field:

- In claude.ai/code, click the cloud icon showing the environment's name, hover
  the environment, and click its gear icon (a new environment's **Add
  environment** dialog has the same field). Paste, then save.

The whole script is three lines, and **installs no skills**:

```bash
rm -rf /opt/agent-skills
git clone --depth 1 https://github.com/dm1681/skills /opt/agent-skills || true
/opt/agent-skills/install.sh --cloud-bootstrap || true
```

`--cloud-bootstrap` registers a user-scope `SessionStart` hook and stops there.
The hook asks *you*, once the session is running, which skills you want; see
[Choosing in the session](#choosing-in-the-session) below.

That indirection is the point. A setup script runs before anyone is present to
consult, so any skill set it hard-codes is a set chosen on your behalf — and
changing it means editing a field in a web UI that has already drifted from the
repository. Registering a hook instead means this field never needs editing
again, and what you are offered is whatever the checkout says today.

It applies to every repo used in that environment and needs nothing committed per
repo. The result is cached (the script re-runs only when you change the
environment or after the cache expires). Requires network access that allows
cloning GitHub.

### Choosing in the session

On each fresh cloud session the hook checks whether any of the collection's
skills are installed. If some are, it says nothing. If none are, it puts the
catalog and the exact install commands into the session's context and tells the
agent to ask you before installing anything.

What it offers:

| Option | Command |
| --- | --- |
| the skills marked machine-wide | `install.sh --skill NAME --skill NAME` (generated, named explicitly) |
| one skill, this repo only | `install.sh --skill NAME --scope project` |
| user-level instructions | `install.sh --global-instructions` |
| graphify (needs `uv`) | `install.sh --graphify` |
| mattpocock/skills (needs `git`) | `install.sh --matt-skills` |

Two things the offer is careful about:

- It never suggests `--non-interactive`, which installs *every* bundled skill.
  A skill marked `global_default: false` is narrow on purpose, and installing it
  machine-wide costs every unrelated session its description. The suggested
  command is generated from that same flag, so it cannot drift from it.
- Matt's `code-review` shares a name with Claude's built-in `/code-review` and
  replaces it for the session. The offer says so, so the choice is informed.

To silence it permanently, `touch ~/.claude/.skills-cloud-declined` — declining
has to outlive the session that declined. To switch it off for a whole
environment, set `AGENT_SKILLS_CLOUD_OFFER=off`.

If you would rather have a fixed set installed with no questions — a CI-style
environment, say — skip `--cloud-bootstrap` and call the sync script directly,
which installs everything under `skills/` unconditionally:

```bash
AGENT_SKILLS_PROJECT_DIR=/opt/agent-skills \
  /opt/agent-skills/scripts/sync-agent-skills.sh || true
# a second source, same installer, pointed elsewhere
AGENT_SKILLS_REPO=mattpocock/skills AGENT_SKILLS_SUBDIR=skills/engineering \
AGENT_SKILLS_PROJECT_DIR=/opt/agent-skills \
  /opt/agent-skills/scripts/sync-agent-skills.sh || true
```

That path installs every bundled skill, narrow ones included, and takes no
account of `global_default`. It is the right tool when nobody will be present to
answer; it is the wrong one when somebody will.

## What "agent-agnostic" means here

The **installer** is fully agent-neutral: it writes to every user-scope skill
root, so whichever agent runs the session finds the skills. By default it covers
both distinct roots from [`agent-support.md`](agent-support.md):

| Destination | Agents |
| --- | --- |
| `~/.claude/skills` | Claude Code |
| `~/.agents/skills` | shared Agent Skills dir (Codex, Cursor, Copilot) |

The **trigger** cannot be fully agent-neutral: each agent has its own startup
mechanism. Claude Code fires `SessionStart` hooks from `.claude/settings.json`;
other agents use their own hook configuration. So the reusable pattern is one
neutral installer, wired into each agent's own startup mechanism.

## How the installer picks a source

1. **Local** — if the current repo already contains the skills (a `skills/`
   directory with `<skill>/SKILL.md` entries), it copies them straight from the
   working tree. No network, no auth. This runs inside this repo and for any
   repo that vendors the skills.
2. **Clone** — otherwise it clones the source repo and installs from it. This
   repo is public, so the clone needs no auth and works from any session (see
   the source note below).

Installing = copying each `<skill>/SKILL.md` directory into every destination
root, replacing any existing copy of the same skill name. Safe to re-run.

## Set up another repo in one command

From a checkout of this repo, scaffold a target repo with the machinery, the
vendored skills, and the `AGENTS.md`/`CLAUDE.md` pair:

```sh
scripts/init-repo.sh /path/to/target-repo
```

It is non-destructive and idempotent: it copies the installer + Claude hook,
registers the hook in `.claude/settings.json` (merging if that file already
exists), vendors every skill from `skills/` (so the installer uses local mode —
no auth), and creates `AGENTS.md` plus a one-line `@AGENTS.md` `CLAUDE.md`.
Options: `--subdir DIR` (vendor elsewhere and point the hook at it),
`--no-vendor` (use submodule/clone mode instead), `--no-agents-md`, `--force`.
Then commit the listed paths to the target's **default branch**.

## Shared agent guidance: AGENTS.md + CLAUDE.md

Keep one source of truth. `AGENTS.md` holds the guidance (Codex, Cursor, and
Copilot read it natively); `CLAUDE.md` is a one-line `@AGENTS.md` import so
Claude Code pulls in the exact same content. Edit `AGENTS.md` only — never
duplicate the text into `CLAUDE.md`. `init-repo.sh` scaffolds both this way.

## Reuse in another repo (manual)

If you prefer not to use `init-repo.sh`, copy both files into the target repo,
then wire the installer into each agent's startup mechanism:

1. Copy `scripts/sync-agent-skills.sh` (keep it executable).
2. **Claude Code** — copy `.claude/hooks/session-start.sh` and add the
   `SessionStart` entry from `.claude/settings.json` to that repo's
   `.claude/settings.json` (merge if it exists).
3. **Other agents (Codex / Cursor / Copilot / …)** — from that agent's own
   startup-hook configuration, run `scripts/sync-agent-skills.sh`. Add your own
   remote/opt-in guard there if you only want it in cloud sessions.
4. Commit to the repo's **default branch** — hooks only take effect once they
   are on the branch the cloud session checks out.

Point the installer at a different source or in-repo location with env vars (all
optional):

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_SKILLS_REPO` | `dm1681/skills` | `owner/name` of the skills source repo (clone mode) |
| `AGENT_SKILLS_REF` | `main` | branch or tag to install from (clone mode) |
| `AGENT_SKILLS_SUBDIR` | `skills` | directory holding `<skill>/SKILL.md` entries |
| `AGENT_SKILLS_DEST` | `~/.claude/skills:~/.agents/skills` | colon-separated destination roots |
| `AGENT_SKILLS_PROJECT_DIR` | `$PWD` | repo to check for local skills |
| `AGENT_GLOBAL_INSTRUCTIONS` | `off` | `link` or `copy` to also install `global/AGENTS.md` as user-level guidance |
| `AGENT_GLOBAL_AGENTS_FILE` | `~/.agents/AGENTS.md` | shared destination for those instructions |
| `AGENT_GLOBAL_CLAUDE_FILE` | `~/.claude/CLAUDE.md` | Claude Code destination, which points at the shared file |

The Claude hook maps `CLAUDE_PROJECT_DIR` onto `AGENT_SKILLS_PROJECT_DIR`
automatically; set the rest only if you need to override a default.

`AGENT_GLOBAL_INSTRUCTIONS` is off by default because it replaces files in the
home directory (each is backed up into `~/.skills-backups/` first). `link`
writes pointers back to the local checkout; `copy` writes the text itself. A
cloned source is always installed as `copy`, since the clone is a temporary
directory that a pointer would outlive.

## Choosing a source: vendor vs. clone

`dm1681/skills` is public, so **clone mode works from any session with no auth**
and without adding the repo to the session's scope. That makes both sources
viable — pick by what you want:

- **Vendor** (the `init-repo.sh` default) — copy the skills into the target repo
  (or add a git submodule) so the installer uses local mode. Self-contained,
  works offline, and pins the exact skill versions committed to that repo; the
  cost is refreshing the copies when skills change. Set `AGENT_SKILLS_SUBDIR` if
  you vendor them somewhere other than `skills/`.
- **Clone** (`init-repo.sh --no-vendor`) — vendor nothing and let the installer
  clone the source at session start. Single source of truth with no duplicated
  content; the cost is a startup dependency on the source repo being reachable.
  Pin with `AGENT_SKILLS_REF` if you don't want `main`.

If a clone ever fails (network, a private fork, a bad ref), the installer logs a
warning and lets the session start normally rather than blocking it.

## Notes

- Web container state is cached after the hook completes, so the skills are part
  of the session's environment from startup.
- Skills install by name; a skill here that shares a name with an agent's
  bundled skill will replace the bundled copy for that session.
- The installer writes only to skill directories under `$HOME`; it never
  modifies the target repo's files.
