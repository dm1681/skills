# Olympus Graphify lifecycle

## Trigger and disposition

Apply this gate when `graphify-out/` is tracked and the active lane changes a
file inside Graphify's indexed corpus. Determine the corpus from Graphify's
tracked root and manifest metadata. When impact cannot be determined
confidently, treat the refresh as required.

Record exactly one structural disposition:

- `GRAPHIFY_NOT_REQUIRED` with the verified reason when `graphify-out/` is
  absent or no indexed file changed.
- `GRAPHIFY_STRUCTURAL_CURRENT` when the current exact head contains
  `graph.json` bytes matching a verified public refresh marker for its
  `SOURCE_TREE_HASH`.

Also record `GRAPHIFY_PRESENTATION_CURRENT` or
`GRAPHIFY_PRESENTATION_DEFERRED`. Presentation artifacts include community
labels, `GRAPH_REPORT.md`, `graph.html`, and other clustered views. Never claim
these artifacts are current after a structural-only refresh.

## Refresh selection

Use the structural fast path only when every indexed change is code and none of
these full-refresh triggers apply:

- a module, service, package, schema, public-interface, or cross-boundary
  dependency materially changed;
- community membership, labels, reports, HTML, or another Graphify view is PR
  evidence or part of acceptance;
- the baseline graph is missing, corrupt, unsafe, or too old to trust; or
- repository instructions require all tracked Graphify outputs to be current.

The fast path is the public command:

```sh
graphify update . --no-cluster
```

It refreshes structural `graph.json` without clustering. Mark presentation
artifacts deferred when their tracked bytes were not regenerated.

Use a full public refresh for any semantic document, paper, image, or video
change, or when a full-refresh trigger applies. For code-only changes run
`graphify update .`. For semantic inputs use `$graphify . --update`, or the
equivalent incremental flow documented by the active Graphify skill. Never
hand-edit generated graph output or call Graphify internals.

## Worktree cache and hook coordination

Before implementation, prefer portable tracked `graphify-out/manifest.json`
and `graphify-out/cache/`. If they are not tracked, the Orchestrator may seed
only those two paths from a trusted clean checkout of the same repository,
exact starting SHA, and Graphify version. Verify the seed contains no secrets,
private paths, or foreign corpus data. Never seed or share mutable
`graph.json`, labels, reports, HTML, or other presentation output across
branches. Skip seeding when provenance is uncertain.

Avoid duplicate rebuilds when a Graphify commit hook is installed. Make every
intermediate implementation commit, plus the final generated-artifact commit,
with `GRAPHIFY_SKIP_HOOK=1` scoped to that commit process. On POSIX shells use
`GRAPHIFY_SKIP_HOOK=1 git commit ...`; on PowerShell set the environment value
for the `git commit` call and remove it immediately afterward. Do not disable or
uninstall the repository hook.

Run exactly one synchronous refresh for each reviewed `SOURCE_TREE_HASH`, after
ordinary tests and source Standards/Spec CLEAN. Record the public command,
Graphify version, source-tree hash, and generated-output hash as the
`GRAPHIFY_REFRESH_MARKER`. Do not run a background hook refresh and then wait
on its lock with a second explicit refresh. A source repair that changes
indexed files invalidates the marker; an artifact-only commit does not when the
source and expected generated-output hashes still match.

Respect Graphify's platform-safe worker default. `GRAPHIFY_MAX_WORKERS` may be
set only for the final command after a repository-local timing check shows that
the chosen value is stable and faster; never encode an unverified global
override in the orchestration contract.

## Role contract

### Planner

State `GRAPHIFY_REQUIRED` or `GRAPHIFY_NOT_REQUIRED` in the canonical brief.
Identify indexed surfaces, classify code-only versus semantic changes, list
full-refresh triggers, supported public commands, tracked structural and
presentation outputs, health checks, repository aggregate tests, and privacy
or generated-artifact risk.

### Worker

When Graphify is required:

1. Finish implementation, documentation, ordinary focused tests, aggregate
   tests, and independent source Standards/Spec review while suppressing
   commit-hook rebuilds as described above.
2. Capture required acceptance evidence. Select the structural fast path or
   full path from the actual source diff and run exactly one synchronous public
   refresh for the reviewed source-tree hash.
3. Verify command completion, graph integrity, source coverage, expected node
   and edge changes, shrink behavior, and absence of credentials, private
   paths, or unrelated corpus content.
4. Run repository-owned Graphify, generated-artifact, evidence replay,
   privacy, diff, packaging, and fresh-clone checks.
5. Record the refresh marker plus both structural and presentation
   dispositions. Include every changed tracked artifact in the branch, commit
   it with the hook suppressed, perform targeted exact-head artifact
   verification, and push the exact head.

A required refresh failure, unsafe artifact diff, unexplained graph-health
warning, unsupported shrink, or false freshness claim blocks handoff. Preserve
evidence and escalate rather than bypassing the gate, editing output manually,
or silently deleting tracked artifacts.

### Reviewer

At the exact pushed head, verify the Planner classification, source-tree hash,
runtime fingerprint, source review certificates, final indexed diff, command
selection, hook-suppression evidence, refresh marker, structural freshness,
health, privacy, reproducibility, and applicable test evidence. Verify that
presentation artifacts are either current or explicitly deferred.

`GRAPHIFY_PRESENTATION_DEFERRED` is non-blocking only when the fast-path
criteria hold and no PR claim or acceptance check depends on those views. A
missing or stale structural graph, an undisclosed stale presentation artifact,
or an incorrectly deferred full-refresh trigger blocks CLEAN. Review Graphify
output under the generated-artifact boundary: Olympus-owned freshness,
integrity, packaging, privacy, and access-path defects may block; unmodified
upstream styling or interaction remains advisory unless promoted.

### Orchestrator

Do not send a final Worker head to the Reviewer until both Graphify
dispositions, refresh marker, and targeted artifact evidence are recorded.
Before readiness or merge,
recheck that the current base added no indexed-file changes outside the
reviewed head. If it did, return the lane through base recovery, one final
refresh, push, and exact-head review.

Track presentation deferrals across merged lanes. When autonomous dispatch
reaches an empty eligible issue frontier, start one Graphify presentation
maintenance lane before declaring the queue complete. Run
`graphify cluster-only .` from current `main` in that lane, review and merge its
PR under the existing merge authority, and clear the accumulated deferrals.
Any later full refresh that starts from all deferred structural heads and
records `GRAPHIFY_PRESENTATION_CURRENT` also clears those earlier deferrals, so
do not create a redundant maintenance lane.
Never regenerate or commit directly on `main`. Under human-controlled dispatch,
report the accumulated deferral durably and wait for explicit maintenance
authorization.

## Semantic incrementality boundary

Use `PROVENANCE_METADATA_ONLY` only under `change-aware-gates.md`. A changed
Markdown file that remains in the semantic corpus requires the supported
semantic update path. Public Graphify tooling may replace all semantic nodes
for that modified document; preserving unchanged section nodes is an upstream
engine concern. Never call internals or hand-edit output to emulate it.

## Post-merge verification

After merge, verify that `main` contains the reviewed structural artifacts and
the recorded presentation state, with no unreviewed indexed-source drift. An
unexpected structural drift requires a separately authorized repair or
maintenance lane. A known presentation deferral follows the batch-close rule
above and does not masquerade as a structural defect.
