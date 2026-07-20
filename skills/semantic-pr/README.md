# semantic-pr

Turn one repository's PR (or branch diff) into a **layered, semantically-grouped walkthrough** —
the flat diff reorganized into dependency cohorts, split into feature sub-groups, ordered
foundational-first, ready for the invoking agent to summarize. Implements
[`docs/layered-semantic-pr-spec.md`](../../docs/layered-semantic-pr-spec.md)
(wayfinder map [#3](https://github.com/dm1681/skills/issues/3)). Targets **TypeScript/TSX** and
**Python**; mixed-language diffs work in one run.

## Install & run

```bash
cd skills/semantic-pr && npm install
npx tsx src/cli.ts --doctor      # readiness check (node, git, deps, python3, pyright) — run this first
npx tsx src/cli.ts --repo /path/to/repo --base <ref> --head <ref> --out walkthrough.md --json out.json
```

Requires **Node ≥ 18** + **git**; **python3** + bundled **pyright** are optional and enable Python.
Missing deps → the run refuses with `→ run: npm install` (not a stack trace); missing python3/pyright
→ the run succeeds but stamps a `degraded` list into the JSON meta and a banner in the walkthrough.

Flags: `--doctor` (readiness report, then exit), `--repo` (default `.`), `--base` (default = merge-base with the default branch),
`--head` (default `HEAD`), `--out` (Markdown file; else stdout), `--json` (stable artifact),
`--prev <artifact.json>` (reuse unchanged groups' summaries), `--include`/`--exclude` (comma-separated
path globs; tests are included by default and rendered last as a "Verification / tests" section).

**No API key, no model.** Fully deterministic — it emits the layered structure and a stable JSON
artifact (`references/cohort-contract.md`); group summaries are left empty for the **invoking agent**
to fill from each symbol's `snippet`/`file:line` in the JSON. `--prev` carries prior summaries
forward for unchanged groups.

## Pipeline (module → ticket)

| Module | Does | Ticket |
|---|---|---|
| `ingest.ts` | `git diff base..head` → changed `.ts`/`.tsx`/`.py` files + HEAD line ranges | [#5](https://github.com/dm1681/skills/issues/5) |
| `analyze.ts` | routes each file to its `LanguageProvider`, merges, then finalizes (crossPkg/crossFile, degree, stable ids) | [#6](https://github.com/dm1681/skills/issues/6) |
| `providers/typescript.ts` | ts-morph AST → enclosing symbols; `findReferences` → edges; auto-detects workspace packages so cross-package edges resolve | [#6](https://github.com/dm1681/skills/issues/6) |
| `providers/python.ts` + `py_extract.py` | stdlib `ast` → changed symbols; pyright LSP `textDocument/references` → precise edges | [#6](https://github.com/dm1681/skills/issues/6) |
| `group.ts` | connected-component cohorts → Louvain sub-groups (cohorts >12) → longest-path layering | [#7](https://github.com/dm1681/skills/issues/7) |
| `label.ts` | deterministic fallback titles; summaries left empty for the invoking agent; `--prev` reuse | [#20](https://github.com/dm1681/skills/issues/20) · [#19](https://github.com/dm1681/skills/issues/19) |
| `render.ts` | Markdown walkthrough: cohort → sub-group → layer → symbol | [#8](https://github.com/dm1681/skills/issues/8) |

## Verified

- **TypeScript** — real Olympus PR #50 (`apps/server` + `apps/web` + `packages/contracts`):
  **71 symbols, 95 edges (2 cross-package), 19 sub-groups, ~2.3 s.** Cross-package edges
  (`apps/server` → `packages/contracts`) resolve; contracts types land at layer 0.
- **Python** — a 3-file layered app (`models` → `store` → `service`) end-to-end: cross-file method
  edges (`Service.welcome` → `User.greeting`, `Store.add` → `make_user`) resolve via pyright,
  land foundational-first, byte-stable across runs. On untyped indirection pyright reports **no**
  edge rather than a guessed one (precise-not-heuristic).

## Tests

`npm test` runs two layers:

- **Behavioral** (`tests/pipeline.test.ts`) — build tiny synthetic git repos and assert specific
  properties: TS multi-layer layering + cross-file edge with evidence, cycle detection, small-PR
  degradation, cross-run stable ids, path globs / test detection, `--prev` reuse, Python cross-file
  edges via pyright, Python class-qualified method names, a mixed TS+Python diff, `--doctor`
  readiness, and the degraded-analysis banner.
- **Golden** (`tests/golden.test.ts` + `eval/`) — snapshot the *entire* artifact (JSON + Markdown)
  for six realistic fixtures, so any unintended change anywhere in the output fails the gate.

### Golden eval (`eval/`)

Each fixture is `eval/fixtures/<name>/{base,head}/**` (plain source; a throwaway git repo is
materialized at run time). Deterministic output makes full-output snapshotting reliable.

```bash
npm run eval                      # assert every fixture matches its checked-in golden
UPDATE_GOLDENS=1 npm run eval     # regenerate goldens after an intended change; review the diff
```

| Fixture | Exercises |
|---|---|
| `ts-layered` | monorepo `apps/`→`packages/`: multi-layer foundation→consumer, **cross-package** edges, a test ordered last |
| `ts-cycle` | cycle surfaced, no false topological order |
| `ts-independent` | unrelated changes stay separate cohorts |
| `ts-small` | single-symbol PR → short walkthrough |
| `py-layered` | Python cross-file edges via pyright (typed `models`→`store`→`service`) |
| `mixed` | TS + Python in one diff |

Output-affecting deps (`ts-morph`, `typescript`, `graphology*`, `pyright`) are **pinned** so goldens
stay reproducible; a deliberate dep bump is a golden regeneration you review.

## Known v1 limitations (from the spec's fog list)

- **TypeScript uses ts-morph, not tree-sitter.** `enclosingNamed` in `providers/typescript.ts` is the
  seam to swap in tree-sitter (faster, tolerant of non-compiling diffs) per the spec.
- **Python edges require resolvable types.** pyright links only references it can resolve; edges through
  untyped indirection are missed, not guessed. Needs `python3` + the bundled `pyright` (else degrades to
  symbols-without-edges).
- Includes test files since the diff matches all source files; a path filter is a small add.
- No move detection or diagrams yet (deferred). Summarization is intentionally the caller's job.
- Provider-build latency (TS Program / pyright startup) dominates; reuse across a session for repeated runs.
