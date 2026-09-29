# Visual language

The page ships one palette, Catppuccin Mocha, and one rule: **a hue means one
thing everywhere**. A teal node and a teal arrow both mean "asynchronous"; a
yellow node and a yellow arrow both mean "branching". Pick a kind for what the
code *does*, never for how it should look. The legend on the page is generated
from the same table the build script validates against, so it can only list
kinds that exist.

## Node kinds (shape + colour)

| Kind | Shape | Colour | Use for |
|---|---|---|---|
| `entry` | stadium | green | Where control enters: a route handler, CLI command, `main`, event subscriber, exported API. Every flow starts at one. |
| `step` | rounded rectangle | blue | A function or block doing ordinary work: validate, transform, compute. The default. |
| `decision` | diamond | yellow | A branch that changes the path: `if`, `match`, dispatch table, feature flag. Its outgoing edges are `branch` edges with labels. |
| `store` | cylinder | peach | State that outlives the call: database, file, cache, session, queue storage. |
| `external` | hexagon | mauve | Something outside the repo: HTTP API, SaaS SDK, OS process, another service. |
| `async` | parallelogram | teal | Work that continues later or elsewhere: enqueue, emit event, spawn task, callback, cron. |
| `config` | folded note | lavender | Settings that shape behaviour: env vars, config files, constants, feature flags read at startup. |
| `exit` | stadium, double outline | pink | Where the flow ends successfully: response sent, value returned to the caller, process exit 0. |
| `error` | octagon | red | Where the flow ends in failure: raised exception, error response, non-zero exit. Red is reserved for this. |
| `component` | rectangle with a heavy left bar | sapphire | Architecture views only: a module, package, service or file treated as one unit. |

## Edge kinds (line + head + colour)

| Kind | Line | Head | Colour | Use for |
|---|---|---|---|---|
| `call` | solid | filled triangle | subtext (neutral) | A synchronous call or hand-off: A invokes B and waits. The default. |
| `return` | thin solid | open chevron | overlay (dim) | A value flowing back to a caller when showing it adds meaning. Omit trivial returns. |
| `branch` | solid | filled triangle | yellow | One outcome of a `decision`. Always labelled (`yes`, `no`, `POST`, `cache hit`). |
| `async` | dashed | filled triangle | teal | Fire-and-forget: publish, enqueue, schedule, spawn. The caller does not wait. |
| `data` | dotted | round dot | peach | Reads or writes to a `store`. Label with the verb (`reads user`, `writes cache`). |
| `error` | dashed | filled triangle | red | Failure propagation: raise, throw, reject, error response. |
| `depends` | long dash | open chevron | overlay (dim) | Architecture views only: A imports or depends on B at build time. |

## Containers

- **File group** (`"kind": "file"`): a solid-bordered box headed with the file
  path (directory dimmed, file name bright) and a language chip. It encloses
  every node whose excerpt comes from that file, and nothing else — the build
  script rejects a node whose `source.path` differs from its group's `path`.
- **Module group** (`"kind": "module"`): a dashed-bordered box for a directory
  or package in architecture views. Its nodes may cite any file under it.
- **Ungrouped nodes** (no `group`): drawn in a dotted "Outside the repo" box.
  Use for `external` nodes, users, and other callers without source.

## Numbered steps

Give flow nodes a `step` (1, 2, 3…) in the order a reader should follow them.
Numbers render as badges, drive the Previous/Next tour, and let the reader
follow a flow that crosses files. Architecture views usually omit steps.

## Choosing well

- One node per meaningful responsibility, not per line. Aim for 6–20 nodes a
  view; split a larger flow into two views and link them with `drill`.
- A file appears as one container per view. If a flow leaves a file and comes
  back, both nodes still sit in that one container; the arrows show the trip.
- Label nodes with the verb phrase a newcomer needs ("Resolve tenant"), and put
  the function name in `summary` or let the excerpt show it.
