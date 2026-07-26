# PR Explorer Data Model

Use this model to separate source-backed analysis from presentation. Populate it only after verifying every node and edge in source, tests, or interface documentation.

## Top-level record

| Field | Required content |
| --- | --- |
| `pr` | `number`, `repository`, `head_sha`, and optional `url` |
| `summary` | `goal`, `old_to_new`, `ownership_chain`, `payoff`, and `residual_debt` |
| `systems` | Stable owner or branch identities with `id`, `label`, and theme `color_token` |
| `nodes` | Semantic components keyed by unique `id` |
| `edges` | Evidence-backed runtime handoffs |
| `branches` | Real execution alternatives and their ordered node paths |
| `shared_before` | Ordered nodes before branch dispatch |
| `convergence_node` | Shared normalized output node |
| `shared_after` | Ordered nodes after convergence |

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
- `source_sha`: the resolved immutable PR head
- `code`: exact contiguous bytes from the selected source range

Keep previews to 4–10 useful lines where possible and no more than 12. Prefer the smallest contiguous excerpt that shows the boundary, dispatch, translation, engine invocation, normalization, or assertion being explained. Do not fabricate omitted code; use a literal ellipsis only when the excerpt is explicitly presented as abridged.

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
