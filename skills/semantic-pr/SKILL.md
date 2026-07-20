---
name: semantic-pr
description: Generate a layered, dependency-ordered walkthrough of a pull request or branch diff for any TypeScript or Python repository — changed symbols extracted via AST, grouped into dependency cohorts, split into feature sub-groups, ordered foundational-first, ready for you to summarize. Use when reviewing or trying to understand a PR whose flat file-by-file diff is hard to follow, when you want a reviewer-friendly walkthrough of what changed and in what order, or when you need a structured (JSON) representation of a diff's change graph. Fully deterministic: it calls no model and needs no API key — the invoking agent writes the summaries. Repository-agnostic and agent-agnostic; not tied to any particular orchestrator or CI system.
---

# semantic-pr

Turn one repository's PR (or branch diff) into a **layered, semantically-grouped walkthrough**.
The flat diff is reorganized into dependency **cohorts**, each split into feature **sub-groups**,
ordered into **layers** (foundational first), and each sub-group summarized. Works against any
local checkout — no service, orchestrator, or CI integration required.

## When to use

- A PR's diff is large or spread across many files and the flat view is hard to reason about.
- You want a walkthrough that reads foundational-changes-first instead of alphabetical-by-file.
- You need the change **graph** (symbols + dependency edges, incl. cross-package) as structured JSON.
- Any coding agent reviewing a PR wants a "what changed and how it fits together" summary before findings.

Scope today: **TypeScript / TSX** (via the TS compiler, ts-morph) and **Python** (via stdlib `ast`
for extraction + pyright's language server for precise references). Mixed-language diffs work in one
run — each file is routed to its language provider and the results are merged. One repo at a time.

## Before first run (preconditions)

Required: **Node.js ≥ 18** and **git**. Optional (enables Python): **python3** and the bundled
**pyright** (installed by `npm install`). The tool reads the working tree, so check out `head` first.

One-time setup, then a readiness check:

```bash
cd "$(dirname SKILL.md)"        # this skill's directory
npm install                     # once — installs ts-morph, graphology, pyright, tsx
npx tsx src/cli.ts --doctor     # ✓/✗ readiness report with the exact fix for anything missing
```

`--doctor` prints one of three verdicts: **ready** (TS + Python), **typescript-only** (TS works;
install python3/deps for Python), or **not-ready** (required deps missing — it names them and how to
fix). If dependencies aren't installed, a normal run refuses with `→ run: npm install` rather than a
stack trace. If python3/pyright are missing while Python files are in the diff, the run still succeeds
but **stamps the partial result** — a banner in the walkthrough and a `degraded` list in the JSON meta.

## How to run

```bash
npx tsx src/cli.ts --repo /path/to/checkout --out walkthrough.md
```

Flags:
- `--doctor` — print the readiness report and exit (non-zero only if not-ready); run no analysis.
- `--repo <path>` — any local git checkout (default `.`).
- `--base <ref>` — default = merge-base with the default branch.
- `--head <ref>` — default `HEAD`.
- `--out <file>` — Markdown walkthrough (else stdout). `--json <file>` — structured analysis.
- `--prev <artifact.json>` — a prior `--json` artifact; groups whose stable id is unchanged reuse
  their summary (no LLM call), so re-reviewing a PR after new commits only summarizes what changed.
- `--include <globs>` / `--exclude <globs>` — comma-separated path globs (e.g. `apps/web/**`,
  `tests/**`, `**/*.test.ts`). Tests are **included by default and rendered last** as a
  "Verification / tests" section; pass `--exclude 'tests/**'` for a product-only view.

**The skill calls no model and needs no API key.** It produces the deterministic layered structure;
each group gets a deterministic fallback title and an **empty summary**. **You (the invoking agent)
write the summaries** — run with `--json`, then for each group read its members' `snippet` fields
(and `file:line` if you want more) and write a 1–2 sentence summary. Everything you need is in the
JSON; there is no second API call and nothing to configure.

**Incremental re-review:** pass a prior `--json` artifact as `--prev`. Groups whose stable id is
unchanged carry their previous summary forward, so on a re-run you only summarize what changed.

## What it produces

A Markdown walkthrough shaped `cohort → sub-group → layer → symbol (name (kind) — file:line)`,
plus a stable, versioned JSON artifact (`--json`) — see `references/cohort-contract.md`. Group
`summary` fields are empty until you fill them; group `title` fields carry a deterministic fallback
you may replace. Consumers decide where the output goes; the skill only produces it.

## How it works (pipeline)

1. **ingest** — `git diff base..head` → changed `.ts`/`.tsx`/`.py` files + HEAD-side line ranges.
2. **analyze** — routes each changed file to its **language provider**, then merges: TypeScript via
   `ts-morph` (`findReferences` for edges, auto-detects workspace packages so **cross-package** edges
   resolve in a monorepo); Python via stdlib `ast` (`src/providers/py_extract.py`) for changed symbols
   + pyright's LSP `textDocument/references` for precise edges. Both keep only edges **among the changed
   set**, so a reference site always lives in a changed (and therefore opened) file.
3. **group** — connected-component cohorts → Louvain community sub-groups (for large cohorts) →
   longest-path layering (foundational first).
4. **label** — deterministic fallback title per group; summaries left empty for the caller (no model).
5. **render** — Markdown walkthrough (+ stable JSON via `--json`).

## Design notes / limitations

- Languages live behind `LanguageProvider` (`src/providers/`); add one by implementing extract +
  edges for its file types and registering it in `analyze.ts`. Ids embed the file path, so providers
  never collide and mixed-language diffs merge deterministically (provider registration order).
- **Python edges are precise, not heuristic.** pyright only links a reference it can resolve, so edges
  through untyped indirection (e.g. a value flowing through an unannotated `dict`) are missed rather
  than guessed — no false edges. Type-annotated code resolves cleanly across files. If `pyright` or
  `python3` is unavailable, the Python provider degrades to symbols-without-edges (logged, not fatal).
- The tool reads the **working tree** while line ranges come from `head`; run it with `head` checked out.
- Includes test files by default (the diff matches all source files); filter by path if you want product-only.
- No move-detection or diagrams yet — deliberately deferred.
- Full background: `docs/layered-semantic-pr-spec.md` and the research/prototypes under `docs/`.
