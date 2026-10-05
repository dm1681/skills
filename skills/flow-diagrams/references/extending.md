# Building a skill on flow-diagrams

`flow-diagrams` is a library: it owns the visual language, the layout and the
page's interactions, and knows nothing about any domain. A skill that draws
in this look adds its own meaning in two places — Python hooks while
building the model, and an extension script and stylesheet on the page.
`codebase-onboarding` uses only the Python side; `semantic-pr-review` uses
both.

## 1. Carry the shared files

Skills install one at a time and cannot import each other, so a consumer
carries byte-identical copies of:

- `assets/diagram-template.html`
- `assets/diagram-kinds.json`
- `scripts/diagram_core.py`
- `references/visual-language.md`

Add the skill to `CONSUMERS` in the repository's
`scripts/sync_shared_diagram.py` and run it. A test fails while any copy
differs; edit the owner's copy here, never a consumer's.

## 2. Build with `diagram_core.build`

```python
import diagram_core as core

built = core.build(
    model,                        # {"title", "summary"?, "views": [...]}
    kinds,                        # core.load_kinds(path), optionally with "groups" replaced
    view_kinds={"flow", "map"},   # the view kinds this skill allows; "flow" needs an entry
    default_group="unit",         # the group kind used when a group names none
    check_group=check_group,      # (where, raw, out, problems)
    check_node=check_node,        # (where, raw, out, group_out_or_None, problems)
    check_edge=check_edge,        # (where, raw, out, problems)
    meta={"label": "owner/repo @ abc1234"},  # the byline beside the page title
)
```

`build` validates everything the visual language requires and raises
`core.ModelError` with every problem at once. Each hook receives the raw
entry and the render-ready copy:

- **Fill in what the page draws.** Groups need a `label` or a `path` for
  their header (a `path` dims the directory and brightens the file name) and
  may set a `tag` chip. Nodes may set `source`:
  `{"code", "lang", "start"?, "path"?, "end"?, "href"?, "title"?}`.
- **Attach your own fields.** Any extra key on the copy rides through to the
  page untouched, for your extension to read. For larger payloads, add a key
  to the returned dict instead (`built["my_model"] = ...`) and look entries
  up by id.
- **Report domain rules** by appending to `problems`.

A view may carry `tag`, the chip shown on its tab (default `flow` or `map`).
Rename containers by replacing `kinds["groups"]`: keep `outside`, give every
kind a `border` of `solid`, `dashed` or `dotted`, and an optional `heading`
for `outside`. The border keeps its meaning whatever the name.

## 3. Render with an extension

```python
html = core.render(built, kinds, template_path, {"css": css_text, "js": js_text})
```

The CSS is appended to the page's stylesheet and may use its Catppuccin
variables (`--base`, `--text`, `--rosewater`, …). The JS runs before the
page and sets `window.diagramExtension` to an object of optional hooks.
Every hook receives `api` as its last argument.

| Hook | Called | Return |
|---|---|---|
| `header(container, api)` | once, at load | nothing; append to `container` (hidden when left empty) |
| `nodeCard(node, place, api)` | building a node's hover card (`place` = `"tip"`) or details panel (`"details"`) | elements to insert after the summary |
| `edgeCard(edge, api)` | building an edge's hover card | elements to append |
| `sourceBlock(source, api)` | drawing a node's excerpt | an element to use instead of the highlighted code block, or `null` |
| `decorateNode(node, g, {w, h}, api)` | after drawing each node | nothing; add SVG or classes to `g` |
| `decorateEdge(edge, g, api)` | after drawing each edge | nothing |
| `legend(view, api)` | building the legend for a view | elements to insert before "Keys" |
| `searchText(node, api)` | filtering on search | extra text to match |

`api` holds the page's own parts, so an extension draws with them rather than
copying them: `el`, `sv` (DOM and SVG builders that never use innerHTML),
`prose` (inline `` `code` `` spans), `highlight`, `codeBlock`, `sourceLink`,
`kindChip`, `cssVar`, `lightUp(nodeIds, edgeFilter)`, `restoreFocus`,
`select`, `centerOn`, `openView`, `update`, `KINDS`, `MODEL` and `state`.

`api.update(patch)` (also `window.diagram.update`) changes data on existing
nodes and edges and redraws them, re-running `decorateNode` / `decorateEdge`
on fresh elements, so a decoration hook only ever draws from the current
data and never has to undo an earlier one. Extra fields set by an update
reach every hook. A model's `live` feed, the update rules and a worked
status-tracker extension are in [live-updates.md](live-updates.md).

## 4. Themes

A page built without themes keeps the template's Mocha palette and shows no
picker. Offer themes with `core.apply_themes(built, themes, default=..., offer=[...])`,
or add the shared flags with `core.add_theme_arguments(parser)` and
`core.themes_from_args(...)`. Offer one theme to lock the page. Extension CSS
should use the palette variables, never literal colours, so it follows the
theme. Details: [themes.md](themes.md).

## Keep the language intact

- Never recolour a kind or reuse a kind's hue for something else. Rosewater,
  flamingo, maroon and sky belong to no kind (code highlighting aside): an
  extension may claim one for a single meaning of its own and say so in its
  legend.
- Pair any colour you add with a shape or symbol, as the kinds do.
- Put domain words in the extension, never in the library.
