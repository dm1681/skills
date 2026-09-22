# Anthropic AGENTS.md support and this repository

Researched September 22, 2026. The compatibility policy below is documented in
the support guide and scaffold; installer behavior is unchanged.

## Announcement versus current behavior

Claude Code **v2.1.277**, released **September 18, 2026**, introduced direct
`AGENTS.md` loading, initially excluding Bedrock, Vertex, and Foundry.
[Release announcement](https://github.com/anthropics/claude-code/releases/tag/v2.1.277).
The details below describe current documentation and public plugin source;
they are not a runtime test of every feature in that release.

## Loading and configuration

Support is implemented by Anthropic's built-in `agents-md` plugin, which adds
project instruction files to the engine's context. Its four modes are:

| Mode | Behavior |
| --- | --- |
| `claude-md-or-agents-md` | Default: use AGENTS files when the project has no qualifying CLAUDE files. |
| `claude-md-and-agents-md` | Load both, deduplicating imports and links. |
| `claude-md` | Keep the existing CLAUDE loader alone. |
| `managed-only` | Keep managed instructions and memory at startup; omit project and personal instructions. |

[Plugin manifest](https://github.com/anthropics/claude-code/blob/main/mods/agents-md/.claude-plugin/plugin.json).

Fallback considers `CLAUDE.md`, `.claude/CLAUDE.md`, and `CLAUDE.local.md` in the
working directory or ancestors. User `~/.claude/CLAUDE.md`, managed instructions,
and `.claude/rules/` do not disable fallback. Startup reads `AGENTS.md` and
`.claude/AGENTS.md` along the ancestor path. `AGENTS.local.md`,
`AGENTS.override.md`, and `.agents/` instruction locations are unsupported.
Consequently, adding private `CLAUDE.local.md` can unexpectedly suppress shared
AGENTS instructions. Existing `@AGENTS.md` bridges remain supported without
duplication. `/init` still generates CLAUDE.md; its newer flow incorporates
AGENTS content. `/import` makes a one-time copy.
Direct AGENTS loading does not fire `InstructionsLoaded` hooks; imports through
CLAUDE do.
[Memory documentation](https://code.claude.com/docs/en/memory#agentsmd).

Use `/config` → **Project instructions**, or user, `--settings`, or managed
settings. Project/local settings cannot select this mode:

```json
{
  "pluginConfigs": {
    "agents-md@builtin": {
      "options": { "instructionFiles": "claude-md-and-agents-md" }
    }
  }
}
```

Imports expand and `claudeMdExcludes` applies. Nested AGENTS files attach on
text `Read`; they lack CLAUDE's prompt-mention, IDE-selection, and nontext-read
triggers. Nested changes are not reannounced; after compaction they return on
the next qualifying Read. Added directories (`--add-dir`) supply no AGENTS
files. External imports need previously granted approval without initiating
the approval dialog. Managed-only does not prevent subsequent nested CLAUDE
attachments. Disabling the built-in restores CLAUDE-only behavior.
[Plugin implementation notes](https://github.com/anthropics/claude-code/blob/main/mods/agents-md/README.md).

The code confirms that fallback suppresses AGENTS for the whole project,
including subsequent nested reads; it is not an independent filename choice
at every directory. It also deduplicates delivered files per agent loop.
[Registration source](https://github.com/anthropics/claude-code/blob/main/mods/agents-md/hooks/register.ts).

## Availability is more than a version check

The feature requires fetched feature flags. Fetching stops when
`DISABLE_GROWTHBOOK`, `DISABLE_TELEMETRY`, `DO_NOT_TRACK`, or
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` has a disabling value, and in third-party-provider or
Claude apps gateway sessions. A host-managed-provider exception exists.
The first session following installation or upgrade can lack newly enabled
features until the next session. There is no documented AGENTS-specific
environment switch guaranteeing availability in these cases.
[Environment-variable reference](https://code.claude.com/docs/en/env-vars#features-that-need-feature-flag-fetching).

## Decisions for this repository

These decisions follow from the findings above:

- **Keep AGENTS.md authoritative and retain the small CLAUDE.md import.**
  Its rationale is compatibility and predictable loading.
- **Keep compatibility scaffolding by default.** `scripts/init-repo.sh`
  currently generates the bridge. An explicit native-only option could suit
  controlled environments, but version detection alone is insufficient. Defer
  that option until a concrete need justifies it.
- **Keep global installation wiring.** `install.py:global_instruction_files`
  and `scripts/sync-agent-skills.sh` bridge through
  `~/.claude/CLAUDE.md`; direct project support does not discover
  `~/.agents/AGENTS.md` as Claude's personal instruction file.
- **Do not change skill-directory mappings or plugin synchronization.**
  Instruction-file support provides no evidence that Claude now discovers
  `.agents/skills`; those are separate capabilities.
  Its [skills documentation](https://code.claude.com/docs/en/skills#choose-where-skills-load)
  still specifies `.claude/skills` for personal and project filesystem skills.
- **Keep documentation together.** Explain conditional support in
  `docs/agent-support.md` and `docs/cloud-skills-sync.md`, preserving their
  global/import guidance.
- **Plan nested instructions deliberately.** With a root CLAUDE bridge and
  default fallback, nested AGENTS-only files will not load automatically.
  Use corresponding bridges, or explicitly configured both-files mode in
  environments where it is available.

Repository references: [CLAUDE.md](../CLAUDE.md),
[project scaffolder](../scripts/init-repo.sh), [installer](../install.py),
[cloud sync](../scripts/sync-agent-skills.sh),
[agent support](agent-support.md), [cloud guidance](cloud-skills-sync.md).
