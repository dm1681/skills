# Onboarding model

The model is the only thing you write by hand. `scripts/build_onboarding.py`
validates it, reads each excerpt from the repository, and renders the page.
Keep the model next to the page (`docs/onboarding/<name>.json`) so anyone can
rebuild it after the code moves.

## Shape

```json
{
  "title": "Onboarding: acme-api",
  "summary": "Where things live, and what happens to a `POST /orders`.",
  "views": [ View, ... ]
}
```

`summary` fields accept inline `` `code` `` spans; everything else is plain text.

### View

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | `[A-Za-z0-9_-]+`, unique. Used in deep links (`#v=<id>&n=<node>`). |
| `title` | yes | Tab label. |
| `kind` | yes | `architecture` (a map of components) or `flow` (one path through the code). |
| `summary` | no | One or two sentences shown in the side panel. |
| `groups` | yes | Containers; see below. |
| `nodes` | yes | Shapes; see below. |
| `edges` | yes | Arrows; see below. |

A `flow` needs at least one `entry` node.

### Group

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique within the view. |
| `kind` | no | `file` (default) or `module`. |
| `path` | yes | Repo-relative. A `file` group's path must be a file; a `module` group's a directory. |
| `summary` | no | Shown when hovering the container header. |
| `lang` | no | Override the language chip; inferred from the extension otherwise. |

### Node

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique within the view. |
| `kind` | yes | One of the node kinds in [visual-language.md](visual-language.md). |
| `label` | yes | 2–5 words, verb first for steps. Wraps to two lines of ~24 characters. |
| `summary` | no | What it does and why a newcomer should care. Name the function here. |
| `group` | no | A group id. Omit for callers and services outside the repo. |
| `step` | no | Positive integer, unique per view: reading order and tour position. |
| `source` | in file groups | `{"path", "start", "end", "contains"}` — see below. |
| `drill` | no | Another view's id; the node gets an "open ⤵" link to that view. |

`source`:

- `path` — repo-relative; must equal the group's `path` for a `file` group, or
  sit under it for a `module` group.
- `start`, `end` — 1-based inclusive line numbers, at most 16 lines, no line
  longer than 120 characters. Pick the lines that show the idea (the
  signature and the decisive statements), not the whole function.
- `contains` — optional text that must appear in those lines. Use it on
  excerpts that matter; when the file changes and the lines drift, the build
  fails instead of showing the wrong code.

### Edge

| Field | Required | Meaning |
|---|---|---|
| `from`, `to` | yes | Node ids in this view. |
| `kind` | no | One of the edge kinds in [visual-language.md](visual-language.md); default `call`. |
| `label` | for `branch` | A few words: the condition, verb or payload (`yes`, `writes cache`, `OrderDTO`). |

## Minimal example

```json
{
  "title": "Onboarding: acme-api",
  "views": [{
    "id": "create-order",
    "title": "Create an order",
    "kind": "flow",
    "groups": [
      {"id": "routes", "path": "app/routes/orders.py"},
      {"id": "svc", "path": "app/services/orders.py"}
    ],
    "nodes": [
      {"id": "post", "kind": "entry", "step": 1, "label": "POST /orders", "group": "routes",
       "source": {"path": "app/routes/orders.py", "start": 12, "end": 18, "contains": "def create_order"}},
      {"id": "valid", "kind": "decision", "step": 2, "label": "Payload valid?", "group": "svc",
       "source": {"path": "app/services/orders.py", "start": 30, "end": 36}},
      {"id": "db", "kind": "store", "label": "orders table"},
      {"id": "ok", "kind": "exit", "step": 3, "label": "201 Created", "group": "routes",
       "source": {"path": "app/routes/orders.py", "start": 19, "end": 20}},
      {"id": "bad", "kind": "error", "step": 4, "label": "422 response", "group": "routes",
       "source": {"path": "app/routes/orders.py", "start": 21, "end": 22}}
    ],
    "edges": [
      {"from": "post", "to": "valid", "label": "OrderIn"},
      {"from": "valid", "to": "db", "kind": "data", "label": "inserts"},
      {"from": "valid", "to": "ok", "kind": "branch", "label": "yes"},
      {"from": "valid", "to": "bad", "kind": "branch", "label": "no"}
    ]
  }]
}
```
