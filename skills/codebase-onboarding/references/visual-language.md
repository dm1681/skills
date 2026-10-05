# Visual language

Colours are named roles from the Catppuccin palette — `green`, `blue`,
`peach`, `text`, `base`, … — and the page follows one rule: **a hue means one
thing everywhere**. A teal node and a teal arrow both mean "asynchronous"; a
yellow node and a yellow arrow both mean "branching". Pick a kind for what the
thing *does*, never for how it should look. The legend on the page is drawn
from the same kinds table the build script validates against, so it can only
list kinds that exist, and it shows only the kinds the current view uses.

Every kind points at a role, never at a value, so a theme (Catppuccin Mocha by
default, its other flavours, or a validated custom palette) changes how the
page looks without changing what anything means. Some skills lock their pages
to one theme.

This file is shared verbatim by every skill that renders this look. The owner
is `skills/flow-diagrams`; edit it there and run
`scripts/sync_shared_diagram.py`.

Rosewater, flamingo, maroon and sky belong to no kind. A skill built on this
look may claim one of them for a single meaning of its own, pair it with a
shape or symbol, and explain it in its legend.

## Node kinds (shape + colour)

Shape and colour carry the same meaning, so a reader who cannot tell two hues
apart still reads the kind from the outline.

| Kind | Shape | Colour | Use for |
|---|---|---|---|
| `entry` | stadium | green | Where the flow starts: a route handler, CLI command, `main`, an incoming order, a user action, a cron trigger. Every flow starts at one. |
| `step` | rounded rectangle | blue | Ordinary work: a function, a task, a process step (validate, transform, review, ship). The default. |
| `decision` | diamond | yellow | A branch that changes the path: `if`, a dispatch table, a feature flag, an approval gate. Its outgoing edges are `branch` edges with labels. |
| `store` | cylinder | peach | State that outlives the step: database, file, cache, session, queue storage, ledger, archive. |
| `external` | hexagon | mauve | Something outside the system drawn: third-party API, SaaS, OS process, a vendor, another team's service. |
| `async` | parallelogram | teal | Work that continues later or elsewhere: enqueue, emit event, spawn task, callback, a hand-off to a batch job. |
| `config` | folded note | lavender | Settings that shape behaviour: env vars, config files, constants, feature flags, policies, SLAs. |
| `exit` | stadium, double outline | pink | Where the flow ends successfully: response sent, value returned, order shipped, process exit 0. |
| `error` | octagon | red | Where the flow ends in failure: raised exception, error response, rejection, non-zero exit. Red is reserved for this. |
| `component` | rectangle with a heavy left bar | sapphire | Maps and block diagrams: a module, package, service, subsystem or device treated as one block. |

## Edge kinds (line + head + colour)

Line style says *when* (solid waits, dashed does not); the head says *what*
moves (a triangle is control, a chevron a dim back-reference, a dot data).
Every arrow is routed at right angles, with rounded corners, around every node
and container header it does not connect, so a line never hides behind a
shape; its shape carries no meaning of its own. Arrow labels are drawn above
everything and placed clear of nodes, headers and each other.

| Kind | Line | Head | Colour | Use for |
|---|---|---|---|---|
| `call` | solid | filled triangle | subtext (neutral) | A synchronous hand-off: A passes control or work to B and waits. The default. |
| `return` | thin solid | open chevron | overlay (dim) | A result flowing back to the caller when showing it adds meaning. Omit trivial returns. |
| `branch` | solid | filled triangle | yellow | One outcome of a `decision`. Always labelled (`yes`, `no`, `POST`, `cache hit`, `> $10k`). |
| `async` | dashed | filled triangle | teal | Fire-and-forget: publish, enqueue, schedule, spawn. The sender does not wait. |
| `data` | dotted | round dot | peach | Reads or writes to a `store`. Label with the verb (`reads user`, `writes cache`). |
| `error` | dashed | filled triangle | red | Failure propagation: raise, throw, reject, error response, escalation. |
| `depends` | long dash | open chevron | overlay (dim) | Maps and block diagrams: A relies on B — imports it, requires it, cannot run without it. |

## Containers (border = what the box holds)

Containers are columns headed with their name. The border style is the
meaning; a skill built on this look may rename the kinds (a `file`, a
`system`) but keeps the border.

- **Solid border** — one thing that owns everything inside: a file, a service,
  a machine, a team. `flow-diagrams` calls it `unit`.
- **Dashed border** — a loose collection: a directory or package, a
  department, a network zone, a phase. `flow-diagrams` calls it `area`.
- **Dotted border, no fill** — outside the system drawn. Every node without a
  group lands here automatically; use it for users, callers and `external`
  services.

A header can carry a small tag chip on the right (a language, a cloud, an
owner) for one fact a reader scans for.

## Numbered steps

Give flow nodes a `step` (1, 2, 3…) in the order a reader should follow them.
Numbers render as badges, drive the ◀ ▶ tour, and let the reader follow a
flow that crosses containers. Maps usually omit steps.

## Choosing well

- One node per meaningful responsibility, not per line or per person. Aim for
  6–20 nodes a view; split a larger flow into two views and link them with
  `drill`.
- A container appears once per view. If a flow leaves it and comes back, both
  nodes still sit in that one container; the arrows show the trip.
- Label nodes with the verb phrase a reader needs ("Resolve tenant", "Approve
  refund"); put names and detail in `summary`.
- Never draw an edge or a branch you cannot point to in the source, the
  process document or the person who owns it.
