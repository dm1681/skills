# Optional Graphify installation

Pass `--graphify` to install or upgrade the official Graphify CLI and register
its skill for the agents selected with `--agent`.

The installer first runs:

```sh
uv tool install --upgrade graphifyy
```

It then runs the matching Graphify registration command:

| `--agent` value | Graphify command |
| --- | --- |
| default / `universal` / `agents` | `graphify install --platform agents` |
| `codex` | `graphify install --platform codex` |
| `cursor` | `graphify install --platform cursor` |
| `copilot` | `graphify install --platform copilot` |
| `claude` | `graphify install --platform claude` |
| `all` | Both the `agents` and `claude` commands above |

When more than one shared agent (`codex`, `cursor`, or `copilot`) is selected,
the installer uses the generic `agents` platform once. This avoids repeatedly
overwriting the same `.agents/skills/graphify` destination with incompatible
agent-specific variants.

With `--scope project`, every Graphify registration command includes
`--project` and runs from `--project-dir`. For example:

```sh
graphify install --project --platform codex
```

## Boundaries

- Graphify is not vendored into this repository. `uv` downloads it from the
  official `graphifyy` package on PyPI only when `--graphify` is provided.
- `--graphify` registers the Graphify skill. It does not install Graphify's
  optional always-on project rules or Git hooks (`graphify codex install`,
  `graphify cursor install`, `graphify hook install`, and similar commands).
- Graphify does not expose a custom destination equivalent to this installer's
  `--target`, so `--graphify` and `--target` cannot be combined.
- `--dry-run` prints every external command without inspecting or changing the
  machine.

Primary references:

- [Graphify installation documentation](https://graphify.com/docs/cli)
- [Graphify source repository](https://github.com/safishamsi/graphify)
- [`graphifyy` on PyPI](https://pypi.org/project/graphifyy/)
