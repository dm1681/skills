---
name: semantic-pr
description: Generate a layered, dependency-ordered walkthrough of a pull request or branch diff for any TypeScript repository — changed symbols extracted via AST, grouped into dependency cohorts, split into feature sub-groups, ordered foundational-first, and summarized in plain language. Use when reviewing or trying to understand a PR whose flat file-by-file diff is hard to follow, when you want a reviewer-friendly walkthrough of what changed and in what order, or when you need a structured (JSON) representation of a diff's change graph. Repository-agnostic and agent-agnostic; not tied to any particular orchestrator or CI system.
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

Scope today: **TypeScript / TSX** (uses the TS compiler via ts-morph). One repo at a time.

## How to run

The tool lives in this skill directory. First run installs dependencies.

```bash
cd "$(dirname SKILL.md)"        # this skill's directory
npm install                     # once
npx tsx src/cli.ts --repo /path/to/checkout --out walkthrough.md
```

Flags:
- `--repo <path>` — any local git checkout (default `.`).
- `--base <ref>` — default = merge-base with the default branch.
- `--head <ref>` — default `HEAD`.
- `--out <file>` — Markdown walkthrough (else stdout). `--json <file>` — structured analysis.
- `--prev <artifact.json>` — a prior `--json` artifact; groups whose stable id is unchanged reuse
  their summary (no LLM call), so re-reviewing a PR after new commits only summarizes what changed.

**LLM summaries are optional.** With `ANTHROPIC_API_KEY` set, each sub-group gets a plain-language
title + summary (`claude-opus-4-8` by default; `SEMANTIC_PR_MODEL=claude-sonnet-5` for lower cost).
Without a key, the full layered structure still renders with placeholder titles — the tool never
hard-requires the network.

## What it produces

A Markdown walkthrough shaped `cohort → sub-group → layer → symbol (name (kind) — file:line)`,
plus an optional JSON emit (`{ meta, symbols, edges, subGroups }`) for programmatic consumers —
e.g. posting as a PR comment, rendering in a UI, or feeding another review step. Consumers decide
where the output goes; the skill only produces it.

## How it works (pipeline)

1. **ingest** — `git diff base..head` → changed `.ts`/`.tsx` files + HEAD-side line ranges.
2. **analyze** — changed lines → enclosing symbols; `ts-morph` `findReferences` → dependency edges
   among the changed set. Auto-detects workspace packages so **cross-package** edges resolve in a monorepo.
3. **group** — connected-component cohorts → Louvain community sub-groups (for large cohorts) →
   longest-path layering (foundational first).
4. **summarize** — one structured LLM call per sub-group (optional; degrades gracefully).
5. **render** — Markdown walkthrough (+ optional JSON).

## Design notes / limitations

- TypeScript only for now; `analyze.ts`'s `enclosingNamed` is the seam to add tree-sitter (faster,
  tolerant of non-compiling diffs) or other languages.
- Includes test files by default (the diff matches all `*.ts`); filter by path if you want product-only.
- No move-detection, diagrams, or incremental-review dedup yet — deliberately deferred.
- Full background: `docs/layered-semantic-pr-spec.md` and the research/prototypes under `docs/`.
