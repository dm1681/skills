# Agent support

The installer uses the shared Agent Skills convention where the agent supports
it, and falls back to the agent's native directory only when necessary.

| Installer value | User scope | Project scope | Notes |
| --- | --- | --- | --- |
| `universal` / `codex` | `~/.agents/skills` | `<repo>/.agents/skills` | Codex's documented user and repository locations. |
| `cursor` | `~/.agents/skills` | `<repo>/.agents/skills` | Cursor supports the shared directory and its own `.cursor/skills`; the shared path is preferred. |
| `copilot` | `~/.agents/skills` | `<repo>/.agents/skills` | GitHub Copilot supports the shared directory plus Copilot/GitHub-specific alternatives. |
| `claude` | `~/.claude/skills` | `<repo>/.claude/skills` | Claude Code's documented native location. |
| `all` | Both unique targets above | Both unique targets above | Installs once per distinct discovery root. |

Primary references:

- [OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Anthropic: Extend Claude with skills](https://code.claude.com/docs/en/skills)
- [GitHub: About agent skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)
- [Cursor: Agent Skills](https://cursor.com/docs/skills)

Agent discovery behavior changes over time. Keep this matrix and the installer
mapping together, and update both in the same pull request.

## Instruction files and skill directories

Claude Code v2.1.277 added conditional native `AGENTS.md` loading. That governs
project instructions; it does not change the skill-directory matrix above.
Continue installing Claude skills into `.claude/skills` at the selected scope.

This collection retains `CLAUDE.md` importing `@AGENTS.md` as its compatibility
default. It also retains the global instruction chain through
`~/.claude/CLAUDE.md`: native project loading does not discover
`~/.agents/AGENTS.md` as Claude's personal instruction file.

Before adding nested instruction files or removing an import, read the
[shared guidance policy](cloud-skills-sync.md#shared-agent-guidance-agentsmd--claudemd).
For the loading modes, availability constraints, and primary sources, see the
[Anthropic support research](anthropic-agents-md-support.md).

## Global instruction loading

The skill-directory matrix above is separate from instruction discovery.
`install.global_instruction_files()` writes only `~/.agents/AGENTS.md` and
`~/.claude/CLAUDE.md`, regardless of `--agent`. Link mode imports the checkout;
copy mode embeds the source in the shared file while Claude still imports it.
The POSIX sync script uses the same default destinations, with
`AGENT_GLOBAL_AGENTS_FILE` and `AGENT_GLOBAL_CLAUDE_FILE` overrides. Neither path
configures all agents' native instruction loaders.

| Agent | Native instruction entry point | Coverage of the current installer |
| --- | --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` with `@path` imports | The generated chain targets this entry point. Verify loading in a fresh session. |
| Codex | `$CODEX_HOME/AGENTS.md` (default `~/.codex/AGENTS.md`); a nonempty `AGENTS.override.md` takes precedence | Neither file is written. Configure an explicit read of the canonical source in a discovered instruction file and verify it; `~/.agents/skills` discovery does not establish global instruction loading. |
| Cursor | User Rules in settings; project `AGENTS.md` or `.cursor/rules` | These entry points are not configured. Add an explicit source reference through the applicable rule mechanism and verify loading. |
| Copilot | CLI: `$COPILOT_HOME/copilot-instructions.md` (default `~/.copilot/copilot-instructions.md`); repository instructions also supported | The CLI user file is not written. Configure the relevant instruction entry point separately; IDE/cloud surfaces need their own verification. |
| `universal` / `all` | Installer aliases, not additional instruction loaders | Installing to both skill roots gives no extra instruction-loading guarantee. |

Copy mode fixes dependence on `@path` resolution only after the shared file is
actually discovered or explicitly read. Preserve existing native instructions
when configuring a bridge; edit the canonical source rather than maintaining
another handwritten copy. This change documents the gaps and does not install
new bridges or roll out settings across devices.

Sources checked 2026-09-22: [Claude memory](https://code.claude.com/docs/en/memory),
[Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[Cursor rules](https://cursor.com/docs/rules), and
[Copilot CLI instructions](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions).
For the Linear mapping example and delivery checks, see
[`linear-workflow.md`](linear-workflow.md).

## Optional tools

For the optional Graphify package and its separate platform mapping, see
[`graphify.md`](graphify.md).

For the repository-owned Matt-derived subset and session selection, see
[`matt-pocock-skills.md`](matt-pocock-skills.md).

For the optional pstack plugin — which shares that fetch pipeline, and shares
two skill names with it — see [`pstack.md`](pstack.md). Neither optional
collection carries agent-specific content: every selected root receives the
same files, so nothing in the matrix above changes when one is installed.

Symphony workers use explicit launch context and verified Codex skill discovery;
see [project setup](symphony.md#worker-skill-selection). Interactive skills remain
available in ordinary sessions.
