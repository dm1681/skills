# Build-ready spec — Layered Semantic PR Walkthrough (v1)

> Destination of wayfinder map [dm1681/skills#3](https://github.com/dm1681/skills/issues/3).
> Every decision below traces to a resolved decision ticket. This is the spec v1 was built from.
> Scope: **one repo at a time, TypeScript.** Repository- and agent-agnostic — packaged as the
> `semantic-pr` skill (`skills/semantic-pr/`). Wiring it into any specific consumer (an orchestrator,
> a CI job, a reviewer loop) is deliberately out of scope; the skill just produces the walkthrough.

---

## 1. What it does

Turn one repository's PR (or branch diff) into a **layered, semantically-grouped walkthrough**:
the flat file-by-file diff is reorganized into dependency **cohorts**, each cohort split into
feature **sub-groups**, each ordered into **layers** (foundational first), and each sub-group
gets a plain-language LLM summary. Validated on real Olympus PR #50 (see `docs/spike-pr50/`).

---

## 2. Pipeline

```
git diff (base..head)                     [#5]
        │
        ▼
tree-sitter: changed hunks → enclosing symbols   [#6 tier-1 A]
        │
        ▼
ts-morph: dependency edges among changed symbols │ one solution-style Program
(findReferencesAsNodes, keep edges within the    │ over the whole monorepo → [#6 tier-1 B]
 changed set; cross-package resolves for free)   │ cross-package edges
        │
        ▼
cohorts = connected components                   [#7]
   └─ large cohort → networkx greedy-modularity sub-groups
        │
        ▼
layers = longest-path over the depends-on DAG (cycle-guarded)   [#6]
        │
        ▼
per sub-group: one structured LLM call → title + summary        [#9]
        │
        ▼
render: Markdown walkthrough (PR comment / file)                [#8]
```

---

## 3. Decisions (the spec)

### Input & ingestion — [#5](https://github.com/dm1681/skills/issues/5)
- **Contract:** `(repoPath, baseRef, headRef)`. Default `baseRef` = merge-base with the default branch, `headRef` = `HEAD`.
- **Mechanism:** local `git diff <base>..<head>` for changed files + hunks; read file bodies from the head worktree. No webhook/API server in v1.
- **GitHub PR adapter** = a thin later wrapper (PR number → base/head SHAs → same path).

### Target language — [#4](https://github.com/dm1681/skills/issues/4)
- **TypeScript**, resolver backbone **ts-morph** (TS compiler API) — compiler-accurate resolution.
  Validated against a real TS pnpm monorepo (Olympus) as an example target, not as a dependency.

### Symbol extraction & edge detection — [#6](https://github.com/dm1681/skills/issues/6) (proven on real code)
- **(A) hunk → symbol:** tree-sitter — smallest AST node covering each changed line, walk to the
  nearest named `function`/`class`/`method`/`interface`/`type`. Fast, tolerant of broken syntax.
- **(B) edges:** ts-morph `findReferencesAsNodes()` per changed symbol; keep only references whose
  enclosing symbol is *also* in the changed set.
- **Monorepo:** a single solution-style `Project` spanning all packages resolves cross-package edges
  (tsconfig project references / path aliases handled natively).
- **Perf:** cost is ts-morph Program-build latency (~1s on PR #50), not diff size — build once, reuse
  the Program across the run.
- **Precision upgrade (later):** `scip-typescript --pnpm-workspaces` for a whole-repo index.

### Grouping & layering — [#7](https://github.com/dm1681/skills/issues/7) (proven on real code)
- **Cohorts** = connected components of the changed-symbol graph.
- **Sub-groups:** cohorts above ~12 symbols are split with **networkx greedy-modularity** community
  detection (Louvain alternative). On PR #50 the 39-symbol web cohort split into 5 feature-coherent
  sub-groups, modularity 0.503.
- **Layering:** longest-path over the depends-on DAG (cycle-guarded) — foundational (layer 0) first.
- The **LLM does not form groups** — structure is deterministic; the LLM only names/summarizes.

### Output format — [#8](https://github.com/dm1681/skills/issues/8)
- **Markdown walkthrough** (rendered to a file and/or posted as a PR comment).
- Structure: `PR summary → Cohort → [sub-group] → Layer → symbol (name (kind) — file:line)`.
- Each cohort/sub-group: LLM-named title, package badges + cross-package flag, ordered layers.
- HTML/graph view is a proven-feasible nice-to-have (`docs/olympus-pr50-semantic-layer.html`), not v1.

### LLM contract — [#9](https://github.com/dm1681/skills/issues/9)
- **Model:** default `claude-opus-4-8`; `claude-sonnet-5` as the cost/latency step-down; identical contract.
- **Call:** one per sub-group. Input = changed symbols (name/kind/file/layer) + code bodies + diff hunks,
  in dependency order. Output enforced by `output_config.format` json_schema:
  `{ title, summary, layer_notes[] }` — always parses.
- **Request:** `thinking:{type:"adaptive"}`, `output_config:{effort:"medium"}`, stream large cohorts.
- **Cost:** prompt-cache the fixed system/conventions prefix (`cache_control`); fan out cohort calls in
  parallel. ~10 cached calls for a PR the size of #50.

---

## 4. Out of scope for v1 — [#10](https://github.com/dm1681/skills/issues/10)
Deferred (each is additive, none needed to make the layering land):
- Mermaid diagrams (sequence/state/ERD)
- Move-aware diff rendering (build body-hash detection yourself when you get to it)
- Concept-based semantic search over summaries
- **Consumer/orchestrator integration** (wiring into a specific reviewer loop, CI, or UI) — the skill stays general; each consumer is its own effort
- Cross-repo / persistent cross-PR memory (LanceDB-style RAG)
- Multi-language breadth; review-quality *judging* (this tool explains, it doesn't judge)

---

## 5. Fog to revisit during build
Surfaced but deliberately not blocking the spec:
- Changed-symbol **granularity** & renames/moves/deletes handling.
- **Large-PR limits**: token budget, truncation, max files/hunks.
- **Program-build latency** management (cache/reuse across a session).
- **Per-language plugin architecture** (keeping a 2nd language clean).
- **Evaluation**: golden PRs to judge "does the walkthrough feel right".

---

## 6. Build order (solo, ~1–3 months to a useful v1)
1. `git diff` ingestion → tree-sitter hunk→symbol.  *(the skeleton)*
2. ts-morph Program + edge extraction → cohorts + layering.  *(the engine — already prototyped)*
3. networkx sub-group splitting.  *(already prototyped)*
4. LLM per-sub-group summaries (structured output + caching).  *(the felt payoff)*
5. Markdown render → PR comment.
6. *Later:* HTML graph view, diagrams, move detection, incremental-review dedup, Olympus wiring.

Steps 1–3 are proven on real Olympus code in `docs/spike-pr50/`.

---

*Provenance: wayfinder map #3, tickets #4–#12. Source research: `docs/coderabbit-semantic-layer-research.md`.
Working prototype + evidence: `docs/spike-pr50/`, `docs/olympus-pr50-semantic-layer.html`.*
