# Explorer Data Model

Use this model to separate source-backed analysis from presentation. Populate it only after verifying every node and edge in source, tests, or interface documentation.

## Top-level record

| Field | Required content |
| --- | --- |
| `pr` | Snapshot identity for any changeset: `number`, `repository`, `head_sha`, optional `evidence_sha`, optional `url` |
| `summary` | `goal`, `old_to_new`, `ownership_chain`, `payoff`, and `residual_debt` |
| `systems` | Stable owner or branch identities with `id`, `label`, and theme `color_token` |
| `nodes` | Semantic components keyed by unique `id` |
| `edges` | Evidence-backed runtime handoffs |
| `branches` | Real execution alternatives and their ordered node paths |
| `shared_before` | Ordered nodes before branch dispatch |
| `convergence_node` | Shared normalized output node |
| `shared_after` | Ordered nodes after convergence |

## Naming the changeset

The snapshot block is keyed `pr` because a pull request was the first supported input, but it identifies any changeset:

- **Pull request** — `number` is the PR number, `repository` is `owner/name`, `head_sha` is the head commit.
- **Ref comparison, commit range, or committed working-tree snapshot** — `number` carries a short changeset label instead (`main...feature`, `HEAD~3..HEAD`, `snapshot 9f2c1ab`), `repository` names the origin the commits are reachable in, and `head_sha` is the analyzed commit. The page prints a bare label as-is and only prefixes `PR ` when the label is a number.

Two constraints outlive the rename. Excerpts are materialized from Git blobs, so the analyzed snapshot must be a commit — review uncommitted work against a snapshot commit or worktree, or deliver the narrative walkthrough without the explorer. Source links are built from `repository` as GitHub blob URLs, so a changeset with no GitHub-reachable origin should be delivered with local editor links and a stated limitation rather than fabricated web links.

## Choosing the analyzed snapshot

Everything resolves against one commit. Normally that is `pr.head_sha`.

A deletion-only changeset has no evidence at its head: the files worth explaining exist only in the pre-image. Set `pr.evidence_sha` to the commit the excerpts come from and leave `pr.head_sha` as the real head. The scaffold materializes from `evidence_sha`, records a notice naming both commits, and renders that notice on the page, so a pre-image anchor is always visible to the reader. Never overload `head_sha` to mean a commit that is not the head.

## Backtick handling per field

The template applies code formatting differently depending on the field. Getting this wrong produces literal backticks or mispaired `<code>` runs in the rendered page, and neither shows up in validation — only in a browser.

| Field | Rule |
| --- | --- |
| `summary.*` (including `ownership_chain` entries), `node.label` | **No backticks.** They are rendered literally. `code_label: true` already styles the label as code. |
| `node.purpose`, `receives`, `sends`, `role`, `connection`, `tradeoff`, `edge.transformation`, `edge.evidence`, `evidence_rail[].evidence` | **Backticks encouraged.** The rich-tooltip renderer converts them into real `<code>` elements. |
| `edge.transfer`, `edge.optional`, `edge.containers` | **No backticks.** The template already code-wraps each list item; adding your own leaves an unpaired delimiter at each end of the joined run. |

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

Classify the handoff itself, not merely its endpoint nodes. An edge is `context` when the changeset leaves the transfer and transformation unchanged, even if an adjacent node changed. Use the edge status to style the visible path segment in both full-path and delta views.

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

The example shows structure only. Do not reuse its claims or labels without changeset-specific evidence.
