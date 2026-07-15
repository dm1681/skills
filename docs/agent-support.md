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

For the optional Graphify package and its separate platform mapping, see
[`graphify.md`](graphify.md).
