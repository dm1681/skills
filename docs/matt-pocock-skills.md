# Matt Pocock skills prerequisite

The `orchestrate-olympus` skill delegates implementation, test-driven
development, and two-axis review to workflows from
[`mattpocock/skills`](https://github.com/mattpocock/skills). The interactive
installer recommends the complete collection so those workflows and their
transitive skill dependencies remain coherent.

## Install behavior

The wizard asks before downloading third-party content and defaults to **Yes**.
Scripted installs remain explicit:

```sh
./install.sh --agent all --matt-skills
```

The installer invokes the upstream `skills` CLI with all skills selected,
copies rather than links the result, and suppresses its nested prompts. It adds
`--global` for user scope and runs from `--project-dir` for project scope.

| This installer | Upstream `skills` CLI |
| --- | --- |
| `universal` / `agents` | `codex` (seeds the shared `.agents/skills` store) |
| `codex` | `codex` |
| `cursor` | `cursor` |
| `copilot` | `github-copilot` |
| `claude` | `claude-code` |
| `all` | `codex` and `claude-code` |

The effective command has this form:

```sh
npx --yes skills@latest add mattpocock/skills --skill '*' \
  --agent <mapped-agent> --copy --yes
```

Node.js 18 or newer is required because the upstream installer is distributed
through `npx`. `--dry-run` prints the exact command without requiring Node.js or
network access. A custom `--target` is rejected because the upstream CLI owns
its destination resolution; use user or project scope instead.

## One-time repository setup

Installing the files is the machine-level prerequisite. Then invoke
`/setup-matt-pocock-skills` once from inside the Olympus repository to configure
the issue tracker, triage labels, and documentation layout. This is a user or
agent action; the terminal installer cannot invoke a coding-agent slash command
on the user's behalf.

If the user declines the wizard prompt, the bundled Olympus skill can still be
copied, but mutating orchestration must pause until the required Matt skills are
available.
