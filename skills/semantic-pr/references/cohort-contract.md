# semantic-pr output contract (schemaVersion 1.0)

The stable, versioned artifact a consumer can depend on. Emitted with `--json`. Ticket
[#16](https://github.com/dm1681/skills/issues/16). The human-facing Markdown walkthrough is a
*rendering* of this same data and is not itself a contract.

## Stability guarantees

- **`schemaVersion`** is the contract version. Additive fields may appear without a bump;
  removals/renames/semantic changes bump the version. Consumers should tolerate unknown fields.
- **Symbol `id` is cross-commit stable.** It is `file::kind::name` (e.g.
  `apps/web/src/App.tsx::fn::promoteIdea`), disambiguated with `#2`, `#3`… only when the same
  `file+kind+name` occurs more than once. **Line numbers are deliberately not part of the id** —
  they shift every edit — so the same symbol keeps its id across commits. The current line is still
  provided as the `line` field for display.
- **Group `id` is content-derived and stable.** It is a 12-char SHA-1 prefix of the group's sorted
  member symbol ids. A feature group keeps its id across commits as long as its membership is
  unchanged; adding/removing a member yields a new id. This is what lets a consumer or a re-run
  recognize "the same group" ([#19](https://github.com/dm1681/skills/issues/19) incremental dedup,
  and [#1](https://github.com/dm1681/skills/issues/1)'s incremental remap).
- **Determinism:** for a fixed `(repo, base, head)` the artifact is byte-stable across runs
  (no timestamps, no randomness in ids). Latency fields under `meta` are the only run-varying values.

## Shape

```jsonc
{
  "schemaVersion": "1.0",
  "meta": {
    "repo": "olympus", "base": "<sha>", "head": "<sha>",
    "filesChanged": 18, "filesLoaded": 43,
    "symbolCount": 71, "edgeCount": 95, "crossFile": 12, "crossPkg": 2,
    "loadMs": 983, "analyzeMs": 2309            // run-varying; not part of stability
  },
  "symbols": [
    { "id": "apps/web/src/App.tsx::fn::promoteIdea", "name": "promoteIdea",
      "kind": "FunctionDeclaration", "file": "apps/web/src/App.tsx", "pkg": "apps/web",
      "line": 1093, "layer": 2, "degree": 3 }
  ],
  "edges": [
    { "source": "<stableId that depends on>", "target": "<stableId it depends on>",
      "crossPkg": false, "crossFile": true }
  ],
  "groups": [
    { "id": "a1b2c3d4e5f6", "cohort": 0, "pkgs": ["apps/web"], "crossPkg": false,
      "title": "Idea undo subsystem", "summary": "…",              // null when no LLM key
      "layerNotes": [ { "layer": 0, "note": "…" } ],
      "symbols": ["…stableId…"]                                    // member ids, layer order
    }
  ]
}
```

## Field reference

| Field | Meaning |
|---|---|
| `symbols[].layer` | 0 = foundational (nothing else in the changed set depends on it downward); higher = builds on lower. Longest-path over the depends-on DAG, cycle-guarded. |
| `symbols[].degree` | count of incident dependency edges within the changed set (a size/centrality hint). |
| `edges[]` | `source` **depends on** `target`. `crossPkg`/`crossFile` flag boundary-crossing edges. |
| `groups[]` | a feature group inside a dependency cohort. `cohort` is the connected-component index; groups within a large cohort are split by community detection. `symbols` are member ids in layer order. |

## Versioning policy

`SCHEMA_VERSION` lives in `src/contract.ts`. Bump the minor for additive changes consumers might
want to detect; bump the major for any breaking change to the fields above.
