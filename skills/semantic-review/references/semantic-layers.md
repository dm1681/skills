# Semantic Layer Classification

## Choose layers by responsibility

Start with this taxonomy, then merge, split, or omit categories to match the changeset:

1. **Caller or orchestration** — decides when work runs and assembles current context.
2. **Boundary contract** — typed request, response, event, schema, or validation boundary.
3. **Selection or dispatch** — chooses an implementation, route, mode, or strategy.
4. **Adapter or integration** — translates between stable domain vocabulary and implementation-specific APIs.
5. **Execution or domain engine** — performs the substantive algorithm or workflow.
6. **Normalization and handoff** — converges branches and returns state to the owning subsystem.
7. **Guardrails and evidence** — tests, import rules, documentation, migration checks, and dependency gates.

These are analytical roles, not mandatory directories. A single file may participate in multiple layers, and one layer may span several packages.

## Layer record

For each layer, produce a record with:

| Field | Question |
| --- | --- |
| Purpose | Why does this responsibility exist? |
| Owner | Which subsystem owns the decision or state? |
| Receives | What exact input enters? |
| Sends | What exact output leaves? |
| Connection | Who calls it, and who consumes it? |
| Change | What does this changeset alter? |
| Tradeoff | What coupling, debt, or risk remains? |
| Evidence | Which source lines, tests, and docs prove it? |

## Connection patterns

Explicitly recognize:

- **Linear flow:** `caller → contract → implementation → result`
- **Branch:** one mode or decision selects multiple implementations
- **Convergence:** multiple branches normalize into one output
- **Re-entry:** output returns to an orchestrator that owns the next decision
- **Cross-cutting rail:** tests or rules constrain several runtime layers
- **Replacement seam:** a stable interface lets one implementation be replaced
- **Legacy containment:** an adapter preserves old behavior behind a new boundary

## Evidence rules

- Use the analyzed snapshot SHA for GitHub links.
- Cite implementation lines for runtime behavior.
- Cite tests for protected outcomes and failure behavior.
- Cite interface documents for declared ownership.
- Mark Graphify-inferred relationships as leads until verified in source.
- Do not infer “mode selects implementation” merely from similarly named files; locate the actual mapping or router.
- When the changeset is a pull request, do not treat a passing CI check as proof that an open or blocked PR is ready to merge.

## Final mental model

Write one compact sentence in this shape:

`Owner of policy → stable boundary → replaceable implementation seam → engine-specific work → normalized result → owner of next decision`

Then explain where the changeset moved responsibilities relative to the old design.
