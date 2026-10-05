# Live updates: turning a diagram into a state tracker

A drawn page can change while it is open. The graph — which nodes exist,
where they sit, how they connect — is fixed when the page is built; the
**data on** nodes and edges can change afterwards. That is enough for a
state tracker: draw the whole process once, then move each step from
pending to running to done.

The library only moves data onto the page. What the states are and how they
look belongs to an extension; [`examples/status-tracker/`](../examples/status-tracker/)
is a complete one to copy or use as it is.

## 1. The update API

Every page exposes `window.diagram.update(patch)` (and `api.update` inside
extension hooks):

```js
diagram.update({
  nodes: { fetch: { status: "running", detail: "3 of 10 sources" } },
  edges: { "fetch>parse": { label: "retrying" } },
});
```

- A patch names existing nodes by id and edges as `FROM>TO`, and sets fields
  on them. Fields merge; unchanged values cost nothing.
- Any field may change except the ones that place an element: `id`, `group`,
  `step` and `drill` on nodes, `from` and `to` on edges. Those throw, because
  the layout is fixed. `kind` may change (a step can become an `error`), but
  must be a known kind.
- Changed elements are redrawn in place, in every view that shows them; the
  legend, the details panel, an open hover card, search and highlighting
  follow. An unknown id is reported in the console and skipped.
- Built-in fields (`label`, `summary`, `kind`, `source`) are drawn by the
  page. Any other field (`status`, `detail`, a percentage) is yours: the page
  stores it and hands it to your extension hooks, which draw it.

`update` returns how many elements changed.

## 2. Getting updates to the page

Pick one feed. All of them end in `update(patch)`.

| Feed | When | How |
|---|---|---|
| **State file** (built in) | An agent or a program writes the state; anyone opens the page | Add `"live": {"url": "state.json", "every": 2}` to the model and serve the folder over HTTP. The page polls the file every `every` seconds (at least 0.5) and applies it whenever it changes. |
| **Your own channel** | You already have a server pushing events | In your extension, open a WebSocket or `EventSource` and call `api.update` on each message. |
| **A host page** | The diagram is embedded in an app via `<iframe>` | In your extension, listen for `message` events from the host's origin and call `api.update`. Check `event.origin`. |

The state file is a patch: `{"nodes": {...}, "edges": {...}}`. The page
applies the whole file each time it changes, so it always describes the
current state, not a history.

Browsers refuse to fetch from a `file://` page, so serve it:

```bash
cd <folder with page.html and state.json>
python3 -m http.server 8765 --bind 127.0.0.1
# open http://127.0.0.1:8765/page.html
```

Beside the search box, the page shows `● live · <time of last poll>`, or why
the feed is down; it stays visible when the header is minimised.

## 3. Writing the state

### From an agent or a shell

Use `scripts/update_state.py`. It merges into the existing file, refuses
layout fields, checks ids against the model when given `--model`, and
replaces the file in one atomic step, so the page never reads half a write:

```bash
S=<skill-dir>/scripts
python3 $S/update_state.py state.json --reset --model pipeline.json \
  --node start status=done --node fetch status=running "detail=3 of 10 sources"
python3 $S/update_state.py state.json --node fetch status=done --node valid status=running
python3 $S/update_state.py state.json --edge "valid>bad" label=retrying
```

Values parse as JSON when they can (`3`, `true`, `null`, `["a"]`) and stay
strings otherwise. An agent working through a plan can run one command per
step it starts and finishes; whoever has the page open watches it advance.

### From a program

Write the same JSON yourself — but atomically: write a temporary file in the
same folder, then rename it over `state.json` (`os.replace` in Python,
`fs.renameSync` in Node). A plain overwrite can be read half-written.

## 4. Drawing the state

The visual language still applies: never recolour a kind, keep red for
failure, and pair any hue you claim with a shape or symbol. The example
extension draws a `status` field like this:

| Status | Drawn as |
|---|---|
| `pending` | faded |
| `running` | pulsing sky glow and a `…` corner badge (sky belongs to no kind) |
| `done` | `✓` corner badge |
| `failed` | red `✕` corner badge — failure is the one thing red means |
| `skipped` | faded with a dashed outline |

It also adds the status (and an optional `detail`) to hover cards and the
details panel, a "Status" legend section that highlights every node in that
state, and makes statuses searchable. Use it as it is:

```bash
python3 <skill-dir>/scripts/build_diagram.py pipeline.json --out page.html \
  --css <skill-dir>/examples/status-tracker/status.css \
  --js <skill-dir>/examples/status-tracker/status.js
```

or copy it and change the vocabulary. A skill with its own builder passes the
same files to `diagram_core.render` as its extension.

## Limits

- **Structure is fixed.** No adding or removing nodes or edges while live; a
  layout recomputed on every change would make everything jump. Containers a
  viewer has moved stay where they put them while updates arrive. Draw every
  step up front and mark the ones that will not run as `skipped`.
- **Polling, not push.** The built-in feed checks the file every few seconds.
  For sub-second updates, use your own channel.
- **Text only.** Every value is rendered as text, never as HTML, so a state
  file cannot inject markup — but treat it as trusted input all the same.
