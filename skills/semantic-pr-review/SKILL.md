---
name: semantic-pr-review
description: Pull and explain a GitHub pull request as a source-referenced hierarchy and interactive semantic flowchart with complete execution branches, DTO-labeled handoffs, source-excerpt hover cards, and code-linked details. Use when a user wants to understand a PR, trace its architectural layers, compare execution strategies, inspect boundary or ownership shifts, or receive a standalone interactive walkthrough instead of a flat diff summary.
---

# Semantic PR Review

Turn a pull request into an evidence-backed architectural walkthrough and an interactive flowchart. Explain the change as a system of responsibilities and handoffs, not as a file-by-file changelog.

## Capability resolution

Use any available read-only GitHub integration, API client, CLI, or local Git refs for PR metadata and patch context. Prefer a purpose-built integration when it is available, but do not require a specifically named tool or companion skill.

Build the interactive explainer with the bundled template and scripts. A host-provided visualization surface may display or preview the result, but the workflow must still work when the agent has only filesystem access, Python 3, Git, and a browser. Produce a guided narrative directly when requested.

Resolve paths relative to this `SKILL.md`; never assume the skill was installed under a particular agent, user, or home-directory convention. If a preferred capability is unavailable, use the documented fallback and state the resulting limitation.

Read [references/semantic-layers.md](references/semantic-layers.md) before classifying the PR. Read [references/explorer-data-model.md](references/explorer-data-model.md) and [references/interactive-flowchart.md](references/interactive-flowchart.md) before building the visual.

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

Derive layers from responsibilities, not directories. Use as many layers as the PR needs; do not force every PR into seven.

For every layer, capture:

- **Purpose:** why the layer exists
- **Owner:** subsystem or module responsible for it
- **Receives:** incoming state, request, event, or configuration
- **Sends:** outgoing state, result, event, or side effect
- **Connection:** upstream and downstream handoffs
- **Change:** what the PR changes at this layer
- **Tradeoff:** deliberate coupling, migration debt, or risk
- **Evidence:** exact source, test, and documentation references

Identify branches, convergence points, loops back into orchestration, and cross-cutting guardrails. State the single most important replacement or ownership seam.

Also create explicit edge records for runtime handoffs. Capture the source node, destination node, action verb, transferred DTOs or events, optionality, wrapping container, transformation, and evidence.

### 5. Explain the architecture

Lead with the outcome and the old-to-new mental model. Then walk the hierarchy from caller to final consumer.

Use exact clickable references near each claim. Prefer:

- local absolute file links with line numbers in the written walkthrough
- immutable GitHub blob links anchored to the PR head SHA in a standalone page
- explicit labels such as `Open adapter · workflows.py lines 50–125`

Separate confirmed runtime behavior from inference. Call out incomplete neutrality, legacy branches, asymmetric execution paths, and unverified tests.

### 6. Build the interactive flowchart

Start with a prominent orientation block containing the central goal, old-to-new model, ownership chain, architectural payoff, and primary residual debt.

Create a top-down directional flowchart that shows:

- caller and boundary contract
- dispatch or decision point
- parallel implementation branches
- branch convergence
- downstream handoff
- cross-cutting guardrails

For every real execution alternative, show the complete path from dispatch through adapter, request or configuration translation, execution engine, mode-specific result, and shared convergence. Do not collapse a multi-step branch into one summary node.

Render every runtime handoff as an arrow with a concise visible verb. On hover or keyboard focus, name the exact transferred DTOs, events, configuration objects, optionality, and containers using code notation.

Visually distinguish code and transfers changed by the PR from unchanged context needed to understand the path. Give nodes and runtime edges explicit change status, show the analyzed head SHA, and provide separate `PR delta` and `Full request path` controls with a visible status legend.

When all execution branches are already visible, emphasize a complete branch on hover or keyboard focus and omit redundant `Trace ...` buttons. Add persistent branch controls only when they materially change, reveal, or filter the rendered information. Make every component a native button. Add a concise hover or focus preview and a persistent click-selected detail area.

Give every node a compact, source-backed code preview. On hover or keyboard focus, show the status, purpose, receives, sends, linked file-and-line location, and a syntax-highlighted `<pre><code>` excerpt. Keep the tooltip open while the pointer moves into it so the viewer can select the excerpt or activate its source link.

Use Catppuccin Latte syntax colors in light mode and Mocha in dark mode. Highlight common token categories locally without a network dependency. Prefer 4–10 exact lines and cap previews at 12.

Define each preview only as a source record with repository-relative `path`, inclusive `start_line`, inclusive `end_line`, `language`, and `source_index`. Never hand-copy preview text or author its displayed label independently. Let `scripts/scaffold_pr_explorer.py` read the Git blob at `pr.head_sha`, derive the excerpt and label, and build immutable GitHub links. Supply `--cursor-root` only for a worktree on the same SHA; generation must fail if its `HEAD` or source bytes differ.

The selected detail area must show purpose, receives, sends, architectural role, connection, tradeoff, and source links. Update all fields and links when the selected node changes.

Build from [assets/pr-explorer-template.html](assets/pr-explorer-template.html) through `scripts/scaffold_pr_explorer.py` when the standard explorer shape fits. In the commands below, replace `<skill-root>` with the directory containing this `SKILL.md`:

```bash
python3 <skill-root>/scripts/scaffold_pr_explorer.py \
  --data /absolute/path/to/pr-model.json \
  --output /absolute/path/to/pr-fragment.html \
  --repo-root /absolute/path/to/repository \
  --source-ref <exact-head-sha> \
  --cursor-root /absolute/path/to/matching-snapshot-worktree
```

Omit `--cursor-root` to fail closed to immutable GitHub links. Render a standalone page when the user asks for HTML or needs to open or share the page outside the agent's native artifact surface. Follow the sandbox, typography, editor-link, and repository-handoff rules in [references/interactive-flowchart.md](references/interactive-flowchart.md).

Create the standalone page directly with the bundled renderer. This path does not depend on a host visualization tool:

```bash
python3 <skill-root>/scripts/render_standalone.py \
  --fragment /absolute/path/to/pr-fragment.html \
  --output /absolute/path/to/page.html \
  --title "PR <number> <scope> Explorer"
```

Use `scripts/prepare_standalone.py` only when adapting a standalone iframe page produced by another renderer.

### 7. Verify

Verify in proportion to risk:

1. Run repository tests relevant to the changed contracts, adapters, and handoffs when the environment supports them.
2. Distinguish assertion failures from dependency or environment failures.
3. Run the artifact validator:

```bash
python3 <skill-root>/scripts/verify_pr_explorer.py /absolute/path/to/fragment.html \
  --standalone /absolute/path/to/page.html \
  --source-repo /absolute/path/to/repository \
  --source-ref <exact-head-sha> \
  --strict
```

Strict validation must compare every rendered preview byte-for-byte with its Git blob, verify labels and immutable URLs from the same range, and verify every Cursor target's worktree `HEAD` and full source bytes.

4. Exercise branch switching, Previous/Next navigation, node selection, dynamic source links, editor deep links, pointer entry into node tooltips, code selection, and delayed tooltip dismissal.
5. Render or screenshot the page at 736 px and 320 px. Check that `scrollWidth <= clientWidth` and inspect for clipped, overlapping, or arbitrarily broken identifiers.
6. Check both light and dark modes: code previews must use Catppuccin Latte and Mocha, retain readable contrast, and distinguish syntax categories.

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
