---
name: flow-diagrams
description: Draw flowcharts and block diagrams as interactive, self-contained HTML pages in Catppuccin colour themes (Mocha by default, light and validated custom themes too), where shapes, colours, arrow styles and container borders carry defined meanings shown in a live legend - one hue means one thing, red only means failure. Covers process flows, request or data pipelines, decision trees, state hand-offs, system and architecture block diagrams, with optional code snippets on hover, numbered step tours, drill-down between views, and live updates that turn a drawn page into a state tracker. Use when the user asks for a flowchart, flow diagram, block diagram, process map, pipeline or system diagram, wants a diagram "in the same style" as an onboarding page, wants to watch a process's state change on a diagram, or another skill needs this visual language.
version: 1.0.0
---

# Flow diagrams

Turn a process or a system into a page a reader can explore. You write a
small JSON model; the bundled script validates it against the visual
language and renders one self-contained HTML file (no network, no
dependencies beyond Python 3.9+).

For a codebase walk-through with real source excerpts, use
`codebase-onboarding` instead: same look, plus file containers and excerpts
read from the repository.

## 1. Pick the view kind

| The user wants… | View `kind` |
|---|---|
| "how does X happen", a process, pipeline, decision tree, request path | `flow`: one path from an `entry` to every `exit` and `error` |
| "how do the parts fit", a system, architecture or block diagram | `map`: `component` blocks joined by `depends`, `call`, `data` and `async` edges |
| both | a `map` whose components `drill` into one `flow` each |

## 2. Gather the facts before drawing

Read the source, process document or conversation the diagram describes.
List the steps and the parts, then every branch, failure and hand-off.
Never draw an edge or a branch you cannot point to; ask one question when a
path is genuinely unknown rather than inventing it.

## 3. Write the model

Write `<name>.json` where the user wants the page (default: next to the
document or code it explains). The field reference and an example are in
[references/model.md](references/model.md); what each shape, colour, arrow
and border means is in
[references/visual-language.md](references/visual-language.md). The rules
that matter most:

- **Kinds carry meaning, not decoration.** Every flow starts at an `entry`
  and ends at an `exit` or `error`; every `decision` fans out through
  labelled `branch` edges; red is only for failure.
- **Containers are owners.** A solid `unit` is one service, team or file; a
  dashed `area` is a loose collection; anything ungrouped is outside the
  system.
- **Number the steps** of a flow (`step: 1, 2, …`) in reading order. The
  page's ◀ ▶ tour follows them.
- **6–20 nodes a view.** Split bigger diagrams and link them with `drill`.
- **Short labels, detail in `summary`.** A `snippet` is for the few lines
  of code or config that show the idea, not a whole file.

## 4. Build

```bash
python3 <skill-dir>/scripts/build_diagram.py <name>.json
```

It writes `<name>.html` beside the model (override with `--out`). It reports
every problem at once; fix the model and rebuild — never hand-edit the HTML.
`--check` validates without writing.

## 5. Look at it

Open the page in a browser (serve it with `python3 -m http.server` if your
browser tool blocks `file://`). Check, per view, that the numbered steps read
in order, hovering lights up the right neighbours, and no label is hidden by
a container header or another label. Screenshot it if you can, and fix what
looks wrong before handing it over.

## 6. Hand over

Tell the user the file path, how to open it, and the view to start with.
Offer to publish it if a publishing or artifact tool is available (the file
is self-contained). Suggest committing the `.json` next to the `.html`.

## Live state

A drawn page can change while open: the graph is fixed, the data on nodes
and edges is not. Add `"live": {"url": "state.json"}` to the model, serve the
folder over HTTP, and write the state with `scripts/update_state.py` (an
agent, one command per step) or any program; the page redraws what changed.
`examples/status-tracker/` draws pending / running / done / failed / skipped
and can be passed as-is with `--css` / `--js`. Everything — the update API,
feeds, atomic writes, drawing rules and limits — is in
[references/live-updates.md](references/live-updates.md).

## Themes

Pages offer the four Catppuccin flavours with a picker by default.
`--theme latte` opens in one, `--themes latte` locks to one, and
`--theme-file my.json` adds a custom palette, which the build checks keeps
kinds distinct and text readable. Format and rules:
[references/themes.md](references/themes.md).

## Page features (for your hand-over)

- Tabs per view; nodes marked "open ⤵" jump to their drill-down view.
- Hover: kind, summary and snippet; neighbours lit, everything else dimmed.
  Click pins it in the side panel with "Comes from" / "Leads to" links.
- The legend lists only the kinds the view uses; hovering an entry
  highlights every shape or arrow of that kind.
- ▴ (or `h`) minimises the header to the tab row and its controls; the
  choice is remembered per viewer, like the panels.
- Keys: ← → walk steps, `/` search, `f` fit, `[` `]` collapse panels,
  `h` header, `Esc` clear; drag to pan, wheel to zoom. The URL hash
  deep-links the view and selected node.

## Building another skill on this look

This skill is also the library other skills draw with. It owns the page,
kinds table, Python core and visual language, and never learns a domain:
a consumer carries byte-identical copies, builds through
`diagram_core.build` with its own hooks, and injects its own extension
script and stylesheet for anything domain-specific. The API, the page hooks
and the sync step are in [references/extending.md](references/extending.md);
`codebase-onboarding` (Python hooks only) and `semantic-pr-review` (hooks
plus an extension) are the worked examples. `scripts/build_diagram.py` is
the plain consumer: it ships no extension of its own, and `--css` / `--js`
inject yours.
