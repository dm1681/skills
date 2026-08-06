---
name: semantic-pr-review
description: Pull and explain a GitHub pull request as a source-referenced hierarchy and interactive semantic flowchart with complete execution branches, DTO-labeled handoffs, source-excerpt hover cards, and code-linked details. Use when a user wants to understand a PR, trace its architectural layers, compare execution strategies, inspect boundary or ownership shifts, or receive a standalone interactive walkthrough instead of a flat diff summary.
---

# Semantic PR Review

Turn a pull request into an evidence-backed architectural walkthrough and an interactive flowchart. Explain the change as a system of responsibilities and handoffs, not as a file-by-file changelog.

## Capability resolution

Use any available read-only GitHub integration, API client, CLI, or local Git refs for PR metadata and patch context. Prefer a purpose-built integration when it is available, but do not require a specifically named tool or companion skill.

Build the interactive explainer with the bundled template and scripts. A host-provided visualization surface may display or preview the result, but the workflow must still work when the agent has only filesystem access, Python 3, Git, and a browser. Produce a guided narrative directly when requested.

Resolve paths relative to this `SKILL.md` — command examples write its directory as `<skill-root>` — and never assume the skill was installed under a particular agent, user, or home-directory convention. If a preferred capability is unavailable, use the documented fallback and state the resulting limitation.

Read [references/semantic-layers.md](references/semantic-layers.md) before classifying the PR. Read [references/explorer-data-model.md](references/explorer-data-model.md), [references/interactive-flowchart.md](references/interactive-flowchart.md), and [references/build-and-verify.md](references/build-and-verify.md) before building the visual.

## Workflow

### 1. Resolve the exact PR snapshot

Identify the repository, PR number, base branch, head branch, and head SHA. Read the title, body, changed-file list, commits, reviews, and check state.

Fetch the PR without overwriting user work. Prefer a remote tracking ref, detached worktree, or another non-disruptive inspection method. Do not replace a dirty checkout or switch the user's branch without authorization.

Record the immutable head SHA. Anchor web source links to this SHA rather than a moving branch.

When local editor links are requested and the active workspace is not on that exact SHA, create a detached snapshot worktree. Never point Cursor at a mutable checkout whose `HEAD` or source bytes differ from the analyzed snapshot.

### 2. Establish the before-and-after boundary

Diff the PR head against the correct merge base. Inspect:

- public entrypoints and callers
- data models, contracts, and validation
- dispatch, routing, and configuration
- adapters and external dependencies
- execution engines or domain logic
- output normalization and downstream handoffs
- tests, import rules, documentation, and dependency changes

Read enough unchanged neighboring code to explain what invokes each changed component and what consumes its result. Distinguish behavior introduced by the PR from pre-existing behavior.

### 3. Use a code graph opportunistically

A code graph is optional. Never block PR analysis or artifact delivery on a graph tool's availability, freshness, or successful execution. Source code, tests, and interface documentation remain authoritative.

If Graphify is available and `graphify-out/graph.json` already represents the PR head snapshot, it may be used as a navigation fast path:

1. Run `graphify reflect --if-stale`.
2. Expand the question using tokens from the graph vocabulary.
3. Query or explain the highest-connectivity boundary nodes.
4. Verify inferred graph relationships in source before presenting them as fact.
5. Save useful query results only when Graphify was used and the generated write is authorized.

Compare the graph snapshot metadata with the PR head SHA before relying on it. If the graph is absent, stale, or built from another branch, skip it unless the user explicitly authorizes an update or rebuild. Use it only to find candidate seams and paths.

### 4. Build the semantic hierarchy

Derive layers from responsibilities, not directories. Use as many layers as the PR needs; do not force every PR into seven. For every layer, capture the full layer record — purpose, owner, receives, sends, connection, change, tradeoff, and evidence — as defined in [references/semantic-layers.md](references/semantic-layers.md).

Identify branches, convergence points, loops back into orchestration, and cross-cutting guardrails. State the single most important replacement or ownership seam.

Also create explicit edge records for runtime handoffs — source node, destination node, action verb, transferred DTOs or events, optionality, containers, transformation, and evidence — in the shape [references/explorer-data-model.md](references/explorer-data-model.md) defines.

### 5. Explain the architecture

Lead with the outcome and the old-to-new mental model. Then walk the hierarchy from caller to final consumer.

Use exact clickable references near each claim. Prefer:

- local absolute file links with line numbers in the written walkthrough
- immutable GitHub blob links anchored to the PR head SHA in a standalone page
- explicit labels such as `Open adapter · workflows.py lines 50–125`

Separate confirmed runtime behavior from inference. Call out incomplete neutrality, legacy branches, asymmetric execution paths, and unverified tests.

### 6. Build the interactive flowchart

Start with a prominent orientation block: central goal, old-to-new model, ownership chain, architectural payoff, and primary residual debt. Show the complete runtime path of every real execution alternative — caller and boundary contract, dispatch, adapters, translated requests, engines, mode-specific results, convergence, downstream handoff, and cross-cutting guardrails — without collapsing a multi-step branch into one summary node.

Render every runtime handoff as an arrow with a concise visible verb and exact transferred DTOs on hover or keyboard focus. Distinguish what the PR changed from unchanged context in every view, show the analyzed head SHA, and give every node a compact, source-backed code preview. The explorer is dark-only (Catppuccin Mocha) by design.

The full presentation contract — controls, tooltips, previews, change-status encoding, link strategy, accessibility, and responsive behavior — is in [references/interactive-flowchart.md](references/interactive-flowchart.md). Define code previews only as source records; the scaffold derives excerpts, labels, and immutable links from the Git blob per [references/explorer-data-model.md](references/explorer-data-model.md).

Author the model, then validate it with the scaffold's `--check` mode before rendering anything — it reports every violation at once. Build from [assets/pr-explorer-template.html](assets/pr-explorer-template.html) through `scripts/scaffold_pr_explorer.py` when the standard explorer shape fits, and create a standalone page with `scripts/render_standalone.py` when the user needs to open or share the page outside the agent's native artifact surface; `scripts/prepare_standalone.py` only adapts a sandboxed page produced by another renderer. Commands and flag semantics are in [references/build-and-verify.md](references/build-and-verify.md).

### 7. Verify

Verify in proportion to risk: run the repository tests the changed contracts deserve, run `scripts/verify_pr_explorer.py --strict` against the artifacts, and exercise the rendered page in a real browser following the procedure in [references/build-and-verify.md](references/build-and-verify.md).

Do not claim local tests passed when they did not run. Report current CI and review state separately from local verification.

### 8. Deliver

Return:

1. the interactive flowchart
2. a concise old-to-new mental model
3. the semantic layer walkthrough with references
4. important tradeoffs and residual risks
5. verification status and known limitations

When the user asks to keep the standalone page in the repository, save it under the closest architecture or developer-documentation directory using `pr-<number>-<scope>-explorer.html`, follow repository naming conventions when they differ, and add it to the nearest documentation index. Keep the editable fragment in the current session's artifact or output directory.

When the user asked for a complete understanding pass, cover every semantic layer in one response. When they prefer guided learning, pause at meaningful boundaries and ask them to summarize the flow in their own words.

## Quality bar

- Explain relationships, not just files.
- Preserve a clear hierarchy even when the diff is large.
- Make every arrow defensible from source or tests.
- Use immutable PR references where possible.
- Treat generated graphs as navigation aids, not sources of truth.
- Keep the visual interactive, keyboard accessible, responsive, and self-contained.
- Keep the final explanation shorter than the evidence-gathering process.
