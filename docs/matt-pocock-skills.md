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
copies rather than links the result, and suppresses its nested prompts. The CLI
runs in a disposable staging project; this installer then copies every
discovered skill into the same resolved roots used for the bundled Olympus
skill. That preserves `~/.agents/skills` for shared user installs and applies
the installer's existing backup-before-replace policy.

| This installer | Upstream `skills` CLI |
| --- | --- |
| `universal` / `agents` | `codex` staging, then selected `.agents/skills` root |
| `codex` | `codex` staging, then selected `.agents/skills` root |
| `cursor` | `codex` staging, then selected `.agents/skills` root |
| `copilot` | `codex` staging, then selected `.agents/skills` root |
| `claude` | `claude-code` |
| `all` | `codex` and `claude-code` |

The effective command has this form:

```sh
npx --yes skills@latest add mattpocock/skills --skill '*' \
  --agent <mapped-agent> --copy --yes
```

Node.js 18 or newer is required because the upstream installer is distributed
through `npx`. `--dry-run` prints the exact staging command and final
destinations without requiring Node.js or network access. Custom `--target`
paths are supported because destination resolution remains under this
installer's control.

## One-time repository setup

Installing the files is the machine-level prerequisite. Then invoke
`/setup-matt-pocock-skills` once from inside the Olympus repository to configure
the issue tracker, triage labels, and documentation layout. This is a user or
agent action; the terminal installer cannot invoke a coding-agent slash command
on the user's behalf.

If the user declines the wizard prompt, the bundled Olympus skill can still be
copied, but mutating orchestration must pause until the required Matt skills are
available.
