# Spike: edge-detection engine on a real Olympus PR (wayfinder #6)

Throwaway proof-of-concept resolving [dm1681/skills#6](https://github.com/dm1681/skills/issues/6).
Runs the two-tier engine against Olympus PR #50 (read-only; nothing committed to Olympus).

- `spike.mjs` — extracts changed symbols (ts-morph AST), resolves dependency edges among
  them (`findReferencesAsNodes`), groups into cohorts (connected components), computes a
  foundational-first layering (longest-path on the depends-on DAG). Emits `graph.json`.
- `graph.json` — the real output: 68 symbols, 95 edges (2 cross-package), 8 cohorts.
- `build-viz.mjs` — renders `graph.json` into `../olympus-pr50-semantic-layer.html`.

Run: `npm i ts-morph && node spike.mjs` with Olympus cloned at `/workspace/olympus`.

Result: cross-package resolution works, `@olympus/contracts` types land at layer 0,
end-to-end ~2.2s. See the visualization for the full readout.
