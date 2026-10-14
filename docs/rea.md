# Optional REA installation

[REA (Reverse Engineer Anything)](https://github.com/morluto/rea) is an MCP
server and CLI that lets an agent inspect shipped artifacts: native binaries,
Electron/JavaScript apps, APKs, .NET assemblies, firmware, WASM, HAR/pcap
captures and more. Its `reverse-engineer-anything` skill tells the agent how
to route a target and how to cite evidence.

Pass `--rea` to register both for the agents selected with `--agent`:

```sh
npx -y rea-agents@<REA_VERSION> setup <clients> --yes
```

| `--agent` value | REA setup arguments |
| --- | --- |
| default / `all` | `--all-detected` (every supported agent REA finds installed) |
| `claude` | `--client claude_code` |
| `codex` | `--client codex` |
| `cursor` | `--client cursor` |
| `copilot` | `--client copilot_cli` |
| `universal` / `agents` | refused: they name a skill directory, not an agent |

REA's setup writes each client's MCP registration (backing up the original
config file) and installs its skill into that client's personal skill
directory, such as `~/.claude/skills/reverse-engineer-anything`. Restart the
agents it names afterwards so the tools appear.

## Why it is not vendored

The skill ships about every other day and has to describe the tools of the
server version it was released with. A copy here would drift within a week
and fight REA's own setup over the same directory, so REA keeps ownership of
both and this collection only tracks the marker directory. The dashboard
therefore reports it as `PRESENT` or `NOT INSTALLED`, never `UP TO DATE`.

## Boundaries

- **Pinned.** `install.REA_VERSION` fixes the package version so an install is
  reproducible. Bump it deliberately after reading the upstream changelog.
- **Personal.** REA is marked `personal` in `install.EXTERNAL_TOOLS`. On a
  work-profile machine it is not a dashboard row, and `--rea` is refused before
  anything is installed. Whether an employer allows reverse-engineering
  tooling is a policy question this installer cannot answer.
- **Machine-wide only.** REA's setup has no project scope, so `--rea` refuses
  `--scope project` and `--target`.
- **No extra software.** Hopper is never installed (`--install-hopper` is
  never passed). Analysis engines (Ghidra, IDA, JADX, Binwalk, Unblob, tshark,
  sigrok, WABT) are brought by you, only when a task needs them. Static
  JavaScript/Electron analysis needs none of them.
- **Runtime.** REA needs `npx` from Node.js 22.19+, 24.11+ or 26+. The setup
  runs from your home directory so that a project-local REA cannot replace the
  pinned one.
- `--dry-run` prints the setup command without running npx.

To remove it, use REA's own `npx -y rea-agents@<REA_VERSION> uninstall`, which
removes only REA-owned registrations and skill files.

## Vetting record (2026-10-13, 6.4.0)

MIT licence, personal-account publisher (`morluto`), very widely used, actively
maintained (daily releases, ~550 open issues). 38 direct npm dependencies plus
optional `frida`. Known CVEs were not checked. Read upstream's `DISCLAIMER.md`:
the project rules out DRM, anti-cheat, and authentication bypass.

Primary references:

- [REA source repository](https://github.com/morluto/rea)
- [`rea-agents` on npm](https://www.npmjs.com/package/rea-agents)
- [REA installation guide](https://github.com/morluto/rea/blob/main/docs/installation.md)
