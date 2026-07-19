# semantic-pr

Turn one repository's PR (or branch diff) into a **layered, semantically-grouped walkthrough** —
the flat diff reorganized into dependency cohorts, split into feature sub-groups, ordered
foundational-first, ready for the invoking agent to summarize. Implements
[`docs/layered-semantic-pr-spec.md`](../../docs/layered-semantic-pr-spec.md)
(wayfinder map [#3](https://github.com/dm1681/skills/issues/3)). TypeScript targets only.

## Install & run

```bash
cd skills/semantic-pr && npm install
npx tsx src/cli.ts --repo /path/to/repo --base <ref> --head <ref> --out walkthrough.md --json out.json
```

Flags: `--repo` (default `.`), `--base` (default = merge-base with the default branch),
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
| `ingest.ts` | `git diff base..head` → changed TS files + HEAD line ranges | [#5](https://github.com/dm1681/skills/issues/5) |
| `analyze.ts` | changed lines → enclosing symbols; ts-morph `findReferences` → edges; auto-detects workspace packages so cross-package edges resolve | [#6](https://github.com/dm1681/skills/issues/6) |
| `group.ts` | connected-component cohorts → Louvain sub-groups (cohorts >12) → longest-path layering | [#7](https://github.com/dm1681/skills/issues/7) |
| `label.ts` | deterministic fallback titles; summaries left empty for the invoking agent; `--prev` reuse | [#20](https://github.com/dm1681/skills/issues/20) · [#19](https://github.com/dm1681/skills/issues/19) |
| `render.ts` | Markdown walkthrough: cohort → sub-group → layer → symbol | [#8](https://github.com/dm1681/skills/issues/8) |

## Verified

Run against real Olympus PR #50 (`apps/server` + `apps/web` + `packages/contracts`):
**71 symbols, 95 edges (2 cross-package), 19 sub-groups, ~2.3 s.** Cross-package edges
(`apps/server` → `packages/contracts`) resolve; contracts types land at layer 0.

## Known v1 limitations (from the spec's fog list)

- **(A) uses ts-morph, not tree-sitter.** `enclosingNamed` in `analyze.ts` is the seam to swap in
  tree-sitter (faster, tolerant of non-compiling diffs) per the spec.
- Includes test files (`tests/`) since the diff matches all `*.ts`; a path filter is a small add.
- No move detection or diagrams yet (deferred). Summarization is intentionally the caller's job.
- Program-build latency dominates; reuse the Program across a session for repeated runs.
