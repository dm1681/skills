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

## Optional tools

For the optional Graphify package and its separate platform mapping, see
[`graphify.md`](graphify.md).

For the optional Matt Pocock workflows and their upstream CLI mapping, see
[`matt-pocock-skills.md`](matt-pocock-skills.md).

For the optional pstack plugin — which shares that fetch pipeline, and shares
two skill names with it — see [`pstack.md`](pstack.md). Neither optional
collection carries agent-specific content: every selected root receives the
same files, so nothing in the matrix above changes when one is installed.
