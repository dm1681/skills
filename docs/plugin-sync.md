# Keeping plugins in sync across machines

This collection already keeps *skills* the same everywhere: they are files in
this checkout, so `skills install` copies them and `skills status` compares
them byte for byte. Claude Code **plugins** are the other half of the same
problem, and until `plugins.json` existed this repository could not see them —
so a machine could be three plugins short and still report "nothing to update".

## Why syncing `settings.json` does not solve it

The obvious move is to copy `~/.claude/settings.json` between machines, since
that is where `enabledPlugins` lives. It does not work, for two reasons.

**`enabledPlugins` does not install anything.** Since Claude Code v2.1.195, a
plugin that settings enable but that comes from an external source — a GitHub
repository, an npm package — does not load until someone installs it. Claude
Code reports it as not installed and prints the `claude plugin install` command
to run. A copied `settings.json` gets you a machine that believes it has
twenty-two plugins and has none.

**Half the file is machine-specific.** A real `settings.json` mixes portable
keys (`model`, `effortLevel`, `permissions`) with keys that name a path or a
platform: a `statusLine` command pointing at `pwsh` and a Windows path, an
`env` entry holding an output directory, `CLAUDE_CODE_USE_POWERSHELL_TOOL`.
Copying the file whole moves those too.

`extraKnownMarketplaces` *is* honoured — Claude Code registers those
marketplaces once you trust the folder — but registering a catalogue is not
installing from it.

So the handle is Claude Code's own CLI, which behaves identically on Linux,
macOS, and Windows. That is what `--plugins` drives.

## The manifest

`plugins.json` at the root of this checkout is the declared state:

```json
{
  "schema": 1,
  "marketplaces": {
    "claude-plugins-official": "anthropics/claude-plugins-official"
  },
  "plugins": [
    "github@claude-plugins-official",
    "pr-review-toolkit@claude-plugins-official"
  ]
}
```

A marketplace maps its **name** — the half after the `@` in every plugin id —
to the source string `claude plugin marketplace add` takes: an `owner/repo`
shorthand, a git URL, or a local path. A plugin naming a marketplace the same
file does not declare is refused when the manifest is read, because otherwise
it fails on a fresh machine as an error from the Claude CLI about a catalogue
nobody mentioned, a long way from the typo that caused it.

Nothing pins a version. Marketplaces update their plugins in the background,
so a pin would be overwritten on one machine and not another, and the manifest
would describe a state no machine actually holds.

## On each machine

```sh
git pull --ff-only
./install.sh            # or install.ps1 on Windows — the skills half
skills plugins          # the plugins half
```

`skills plugins` registers any marketplace the manifest names and this machine
lacks, installs every declared plugin that is missing, and re-enables any that
is installed but switched off. `--dry-run` prints the `claude` commands and
runs none of them.

Marketplaces are registered first — installing from a catalogue this machine
has not registered is the failure that ordering exists to prevent. Restart
Claude Code, or run `/reload-plugins`, to load what it installed.

## Checking for drift

```sh
skills status
```

Plugins now appear as their own section, in both the scoped and the `--all`
view: they are installed per machine and never per skills root, so narrowing
the question to one directory does not narrow them. The command exits `3` when
anything needs attention, which is what makes it usable from a hook or a CI
job.

The rows a plugin can be in:

| State       | Means                                             | Counts as work |
| ----------- | ------------------------------------------------- | -------------- |
| `current`   | registered, installed, enabled                    | no             |
| `missing`   | declared here, not installed on this machine       | yes            |
| `disabled`  | installed but switched off — `enable`, not reinstall | yes          |
| `untracked` | installed here, absent from `plugins.json`         | yes            |
| `unknown`   | the `claude` CLI could not be asked                | no             |

Healthy rows collapse to a single count. Two dozen `current` lines is what a
matching machine *produces*, and printing each one buries the handful that
need a decision.

`untracked` counts as work because that is the drift this file exists to
catch: something got installed on one machine and nowhere else. Closing it is
a choice, not an automatic removal — add the plugin to `plugins.json` and
commit, or `claude plugin uninstall` it. **`--plugins` never removes
anything.** The manifest is a floor for what every machine has, not a warrant
to delete what someone installed on one of them on purpose.

`unknown` deliberately does not count. A machine without Claude Code on `PATH`
cannot answer the question, and a check that treated "could not ask" as
"behind" would fail forever on a box that is perfectly current — the same
reason an unfetchable origin reports `unknown` rather than `behind`.

Only **user scope** is reconciled. A project- or local-scope plugin belongs to
the repository that asked for it; counting one as undeclared drift would
report every collaborator's repo-level choice as a problem on every machine
that opened that repo.

## Turning the section off

```sh
SKILLS_PLUGIN_STATUS=off skills status
```

For a hook or CI job whose command line somebody else wrote, and for machines
where asking is not wanted. It follows the same convention as
`AGENT_GLOBAL_INSTRUCTIONS`. This project's own tests set it: every other
section of the report reconciles files under a temp home, but this one asks
the real machine, so a suite that left it on would pass or fail on which
plugins happened to be installed wherever it ran.

## Adding a plugin to the baseline

Install it wherever you are, then let `status` tell you what to write:

```sh
claude plugin install linear@claude-plugins-official --scope user
skills status            # reports it as `untracked`
```

Add the id to the `plugins` list in `plugins.json`, commit, and the other
machines pick it up on their next `git pull && skills plugins`.

## What this does not cover

- **`settings.json` itself.** Model, effort level, permissions, and output
  style still drift. Merging a portable fragment into each machine's file —
  rather than copying the file, which would move the machine-specific keys
  with it — is the natural next step and is not built yet.
- **MCP servers** configured outside a plugin, which live in `~/.claude.json`
  alongside authentication state.
- **Plugin versions.** Deliberately; see above.
