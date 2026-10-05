# Diagram model

The model is the only thing you write by hand. `scripts/build_diagram.py`
validates it and renders the page. Keep the model next to the page
(`<name>.json` beside `<name>.html`) so anyone can rebuild it.

## Shape

```json
{
  "title": "Order fulfilment",
  "summary": "From a paid order to a parcel at the door.",
  "live": {"url": "state.json", "every": 2},
  "views": [ View, ... ]
}
```

`live` is optional: the page polls `url` every `every` seconds (default 2,
at least 0.5) and applies it as an update. See
[live-updates.md](live-updates.md).

`summary` fields accept inline `` `code` `` spans; everything else is plain text.

### View

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | `[A-Za-z0-9_-]+`, unique. Used in deep links (`#v=<id>&n=<node>`). |
| `title` | yes | Tab label. |
| `kind` | yes | `flow` (one path from start to finish) or `map` (a block diagram of parts and how they relate). |
| `summary` | no | One or two sentences shown in the side panel. |
| `groups` | yes | Containers; may be empty. |
| `nodes` | yes | Shapes. |
| `edges` | yes | Arrows. |

A `flow` needs at least one `entry` node.

### Group

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique within the view. |
| `label` | yes | Header text: the service, team, stage or zone name. |
| `kind` | no | `unit` (default, solid border) or `area` (dashed border). |
| `tag` | no | A short chip on the header's right: `AWS`, `python`, `Finance`. |
| `summary` | no | Shown when hovering the header. |

Nodes without a `group` land in the dotted "Outside the system" container.

### Node

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique within the view. |
| `kind` | yes | One of the node kinds in [visual-language.md](visual-language.md). |
| `label` | yes | 2–5 words, verb first for steps. Wraps to two lines of ~24 characters. |
| `summary` | no | What it does and why a reader should care. |
| `group` | no | A group id. |
| `step` | no | Positive integer, unique per view: reading order and tour position. |
| `drill` | no | Another view's id; the node gets an "open ⤵" link to that view. |
| `snippet` | no | `{"code", "lang", "title"}` — a short code or config block shown on hover. At most 16 lines of 120 characters. `lang` picks the highlighter (`python`, `typescript`, `json`, `yaml`, `sql`, `shell`, …); `title` is a caption such as a file name. |

### Edge

| Field | Required | Meaning |
|---|---|---|
| `from`, `to` | yes | Node ids in this view. |
| `kind` | no | One of the edge kinds in [visual-language.md](visual-language.md); default `call`. |
| `label` | for `branch` | A few words: the condition, verb or payload (`yes`, `writes cache`, `Invoice`). |

## Minimal example

```json
{
  "title": "Refund requests",
  "views": [{
    "id": "refund",
    "title": "Refund a charge",
    "kind": "flow",
    "groups": [
      {"id": "support", "label": "Support desk", "kind": "area"},
      {"id": "billing", "label": "Billing service", "tag": "python"}
    ],
    "nodes": [
      {"id": "ask", "kind": "entry", "step": 1, "label": "Customer asks", "group": "support"},
      {"id": "big", "kind": "decision", "step": 2, "label": "Over $500?", "group": "billing",
       "snippet": {"lang": "python", "title": "billing/refunds.py",
                   "code": "if amount > LIMIT:\n    return escalate(charge)"}},
      {"id": "ledger", "kind": "store", "label": "Ledger", "group": "billing"},
      {"id": "done", "kind": "exit", "step": 3, "label": "Refund issued", "group": "billing"},
      {"id": "mgr", "kind": "external", "step": 4, "label": "Finance approval"}
    ],
    "edges": [
      {"from": "ask", "to": "big"},
      {"from": "big", "to": "done", "kind": "branch", "label": "no"},
      {"from": "big", "to": "mgr", "kind": "branch", "label": "yes"},
      {"from": "done", "to": "ledger", "kind": "data", "label": "writes refund"}
    ]
  }]
}
```
