# PR Explorer Data Model

Use this model to separate source-backed analysis from presentation. Populate it only after verifying every node and edge in source, tests, or interface documentation.

## Top-level record

| Field | Required content |
| --- | --- |
| `pr` | `number`, `repository`, `head_sha`, optional `evidence_sha`, optional `url` |
| `summary` | `goal`, `old_to_new`, `ownership_chain`, `payoff`, and `residual_debt` |
| `systems` | Stable owner or branch identities with `id`, `label`, and theme `color_token` |
| `nodes` | Semantic components keyed by unique `id` |
| `edges` | Evidence-backed runtime handoffs |
| `branches` | Real execution alternatives and their ordered node paths |
| `shared_before` | Ordered nodes before branch dispatch |
| `convergence_node` | Shared normalized output node |
| `shared_after` | Ordered nodes after convergence |

## Choosing the analyzed snapshot

Everything resolves against one commit. Normally that is `pr.head_sha`.

A deletion-only PR has no evidence at its head: the files worth explaining exist only in the pre-image. Set `pr.evidence_sha` to the commit the excerpts come from and leave `pr.head_sha` as the real head. The scaffold materializes from `evidence_sha`, records a notice naming both commits, and renders that notice on the page, so a pre-image anchor is always visible to the reader. Never overload `head_sha` to mean a commit that is not the head.

## Backtick handling per field

The template applies code formatting differently depending on the field. Getting this wrong produces literal backticks or mispaired `<code>` runs in the rendered page, and neither shows up in validation — only in a browser.

| Field | Rule |
| --- | --- |
| `summary.*` (including `ownership_chain` entries), `node.label` | **No backticks.** They are rendered literally. `code_label: true` already styles the label as code. |
| `node.purpose`, `receives`, `sends`, `role`, `connection`, `tradeoff`, `edge.transformation`, `edge.evidence`, `evidence_rail[].evidence` | **Backticks encouraged.** The rich-tooltip renderer converts them into real `<code>` elements. |
| `edge.transfer`, `edge.optional`, `edge.containers` | **No backticks.** The template already code-wraps each list item; adding your own leaves an unpaired delimiter at each end of the joined run. |

## What a node tooltip says, in order

A node's hover card reads as four things, and the model supplies them from
three fields:

1. **The summary** — the first line of `purpose`. What this node does,
   independent of the PR.
2. **The change** — `change_note` when present, otherwise a sentence derived
   from `change_status`.
3. **The detail** — every remaining line of `purpose`, so bullets land here.
4. **The handoff** — `Receives: … Sends: …`, built from those two fields.

```json
"change_status": "added",
"change_note": "Split the old inline branch into a registry lookup.",
"purpose": "Normalizes every inbound request before dispatch.\n- validates the `token`\n- refreshes metadata"
```

`change_note` is optional. Without it the line falls back to the status:

| `change_status` | Sentence |
| --- | --- |
| `added` | Added in this pull request. |
| `modified` | Modified in this pull request. |
| `removed` | Removed in this pull request. |
| `context` | Unchanged context. |

End the summary as a sentence, not with a colon. The change sentence now sits
between it and the bullets, so a trailing `:` points at the wrong line.

Write one when the status word is too blunt to be useful — "added" says
nothing about *what* was introduced, and this line is the one a reader uses to
decide whether the node is worth opening. It takes backticks like the other
prose fields, and it must be a non-empty string when present; the scaffold
rejects anything else rather than rendering a blank line.

## Markdown excerpts render as markdown

A `code_preview` with `"language": "markdown"` is drawn as the document it is —
headings, bold and italic, inline code, bullet and numbered lists,
blockquotes, rules, and fenced code blocks (highlighted in the fence's own
language) — instead of as raw markup. Point a node at a `.md` file and declare
the language; nothing else is needed.

```json
"code_preview": { "language": "markdown", "source_index": 0 }
```

What this does **not** change is the excerpt. `code_preview.code` still holds
the file's bytes, and `verify_pr_explorer.py` still compares them to the blob
at the pinned commit, so a markdown preview is exactly as source-backed as a
Python one. Only the drawing differs.

Two things worth knowing:

- **A link only becomes a link if its scheme is `http`, `https`, or
  `mailto`.** Anything else — a script scheme, or a relative path with no base
  to resolve against inside a tooltip — renders as its label text. Raw HTML in
  the excerpt is inserted as text and never parsed as markup.
- **An unterminated fence is kept, not dropped.** An excerpt is a slice of a
  file, so it can open a fence it never closes; the remaining lines render as
  the code block they are.

Choose another language when the excerpt's *markup* is the point — a PR that
changes markdown syntax itself is better read as source, since rendering is
what hides the characters under review.

## Line breaks and bullets

The same fields that take backticks also take line breaks. A field with no
newline renders as one inline run, exactly as before. Split it across lines and
each line becomes its own block, with a line that starts `- `, `* `, or a
literal bullet rendered as a real bullet whose wrapped text stays aligned.

```json
"purpose": "Normalizes every inbound request:\n- validates the `token`\n- refreshes session metadata"
```

Backticks still resolve inside a bullet, so the two features compose.

Two constraints worth knowing, because neither is obvious from the rendered
page:

- **The blocks are styled `<span>`s, not a `<ul>`.** These values land in a
  `<p>` and in several `<span>`s, where a `<ul>` or `<div>` is invalid and the
  HTML parser hoists it out of its container, breaking the layout. Phrasing
  content promoted to a block by CSS is the only structure valid in all of
  them.
- **Blank lines are dropped, and each line is trimmed.** Indent the JSON
  string however you like; spacing between blocks comes from the stylesheet,
  not from the authored whitespace.

In a node tooltip, a multi-line `purpose` also pushes the trailing
`Receives: … Sends: …` sentence onto its own line, so it never rides on the
last bullet. A single-line `purpose` keeps the original one-paragraph wording.

## Validate before you render

Run the scaffold in check mode while authoring. It reports every violation in one pass — missing fields, unknown systems, unresolved path nodes, missing edges, preview length, and line width — without writing an artifact:

```bash
python3 <skill-root>/scripts/scaffold_pr_explorer.py \
  --data /absolute/path/to/pr-model.json \
  --repo-root /absolute/path/to/repository \
  --check
```

`--output` is not required with `--check`. Authoring twenty nodes and discovering the preview caps one render at a time is the single most expensive way to use this skill.

## Node record

Every node must contain:

- `id`
- `label`
- `code_label`: whether the primary label is a code object
- `system`
- `change_status`: `added`, `modified`, `removed`, or `context`
- `purpose`
- `receives`
- `sends`
- `role`
- `connection`
- `tradeoff`
- `sources`
- `code_preview`

Each raw source record contains:

- `label`: descriptive semantic evidence label
- `path`: repository-relative source path
- `start_line`: inclusive one-based start
- `end_line`: inclusive one-based end

Do not hand-author `github_url`, `cursor_url`, `snapshot_sha`, or `local_path`. The scaffold script derives immutable GitHub links and `snapshot_sha` from `pr.head_sha`. It adds a Cursor URL only when an explicitly supplied snapshot worktree has the same `HEAD` and identical source bytes.

Each raw `code_preview` contains only:

- `language`: syntax family such as `python`, `typescript`, `toml`, or `markdown`
- `source_index`: zero-based index into the node's `sources` list

The scaffold derives:

- `source_label`: compact `file · start–end` text shown above the excerpt
- `source_sha`: the resolved analyzed snapshot (`pr.evidence_sha` when set, otherwise `pr.head_sha`)
- `code`: exact contiguous bytes from the selected source range

Keep previews to 4–10 useful lines where possible. The scaffold rejects more than 12 lines, and rejects any line over 110 characters — deeply indented YAML and long shell strings hit the width cap first. Prefer the smallest contiguous excerpt that shows the boundary, dispatch, translation, engine invocation, normalization, or assertion being explained. Do not fabricate omitted code; use a literal ellipsis only when the excerpt is explicitly presented as abridged.

The referenced source must point to the same snapshot and first line as the excerpt. Generate the explorer and validate it against the same Git repository and ref. Never use a mutable local workspace as the Cursor target unless it exactly matches the analyzed SHA.

## Edge record

Every runtime edge must contain:

- `from`
- `to`
- `change_status`: `added`, `modified`, `removed`, or `context`
- `verb`
- `transfer`: exact DTO, event, state, or configuration names
- `optional`: optional transfer members, or an empty list
- `containers`: wrapping envelopes or configuration containers, or an empty list
- `transformation`: translation, normalization, or routing behavior
- `evidence`: source or test reference

Use an empty `transfer` list only when the edge explicitly represents control flow with no runtime payload. Cross-cutting tests and documentation belong on a separate evidence rail rather than payload-free runtime edges.

Classify the handoff itself, not merely its endpoint nodes. An edge is `context` when the PR leaves the transfer and transformation unchanged, even if an adjacent node changed. Use the edge status to style the visible path segment in both full-path and delta views.

## Branch record

Each branch contains:

- `id`
- `label`
- `system`
- `path`: ordered node IDs

A real implementation branch should normally include adapter, translated request or configuration, engine, and mode-specific result nodes before reaching `convergence_node`.

## Example shape

```json
{
  "pr": {
    "number": 54,
    "repository": "owner/repository",
    "head_sha": "immutable-sha"
  },
  "summary": {
    "goal": "One stable boundary for every strategy",
    "old_to_new": "Caller-selected implementation to subsystem-owned dispatch",
    "ownership_chain": ["Caller owns when", "Subsystem owns how", "Consumer owns review"],
    "payoff": "Implementations can be replaced behind one contract.",
    "residual_debt": "One legacy branch remains isolated."
  },
  "systems": [
    {"id": "shared", "label": "Shared contract", "color_token": "var(--viz-series-1)"}
  ],
  "shared_before": ["caller", "dispatch"],
  "branches": [
    {"id": "mode-a", "label": "Mode A", "system": "shared", "path": ["adapter", "engine", "result"]}
  ],
  "convergence_node": "normalized-output",
  "shared_after": ["consumer"],
  "nodes": [
    {
      "id": "dispatch",
      "label": "resolve_strategy()",
      "code_label": true,
      "system": "shared",
      "change_status": "added",
      "purpose": "Choose one implementation behind the stable boundary.",
      "receives": "`PlanningRequest`",
      "sends": "`PlanningBackend`",
      "role": "Strategy dispatch",
      "connection": "Maps the caller's requested mode to one backend.",
      "tradeoff": "Explicit routing is easy to audit but requires a registered mapping.",
      "sources": [
        {
          "label": "Dispatch mapping · selection.py lines 31–40",
          "path": "src/selection.py",
          "start_line": 31,
          "end_line": 38
        }
      ],
      "code_preview": {
        "language": "python",
        "source_index": 0
      }
    }
  ],
  "edges": []
}
```

The example shows structure only. Do not reuse its claims or labels without PR-specific evidence.
