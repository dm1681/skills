# Olympus Graphify lifecycle

## Trigger

Apply this gate when `graphify-out/` is tracked and the active lane changes a
file inside Graphify's indexed corpus. Determine the corpus from Graphify's
tracked root and manifest metadata. When impact cannot be determined
confidently, treat the refresh as required.

If `graphify-out/` is absent or no indexed file changed, record
`GRAPHIFY_NOT_REQUIRED` with the reason. Do not run Graphify merely to create
new repository scope.

## Role contract

### Planner

State `GRAPHIFY_REQUIRED` or `GRAPHIFY_NOT_REQUIRED` in the canonical brief.
Identify the indexed surfaces expected to change, the supported incremental
command, tracked outputs, health checks, repository aggregate tests, and any
privacy or generated-artifact risk.

### Worker

When Graphify is required, use this order:

1. Complete the implementation, documentation, and ordinary focused and
   aggregate tests.
2. Run `$graphify . --update`, or the equivalent installed public incremental
   command documented by the active Graphify skill. Never hand-edit generated
   graph output or call Graphify internals.
3. Verify the command completed, graph health has no unexplained corruption,
   tracked outputs are fresh, and the diff contains no credentials, private
   paths, or unrelated corpus content.
4. Run any repository-owned Graphify, generated-artifact, or fresh-clone
   aggregate tests.
5. Include the refreshed tracked artifacts in the same branch, then perform
   the final pre-push Standards and Spec check, push the exact head, and notify
   the Reviewer.

Repeat the gate during a repair round whenever the repair changes indexed
files after the last successful refresh. A required refresh failure, unsafe
artifact diff, unexplained graph-health warning, or unsupported shrink blocks
handoff. Preserve evidence and escalate rather than bypassing the gate,
editing output manually, or silently deleting tracked artifacts.

### Reviewer

At the exact pushed head, verify the Planner disposition, changed indexed
surfaces, successful public refresh evidence, tracked artifact freshness,
health results, privacy, reproducibility, and repository aggregate tests.
Review Graphify output under the generated-artifact boundary: Olympus-owned
freshness, integrity, packaging, privacy, and access-path defects may block;
unmodified upstream styling or interaction remains advisory unless promoted.

Do not issue CLEAN when a required refresh is missing, stale, unsafe, corrupt,
or absent from the reviewed head.

### Orchestrator

Do not send a final Worker head to the Reviewer until the Worker records
`GRAPHIFY_REQUIRED` with refresh evidence or `GRAPHIFY_NOT_REQUIRED` with a
verified reason. Before readiness or merge, recheck that the current base has
not added indexed-file changes outside the reviewed head. If it has, return the
lane through base recovery, Graphify refresh, push, and exact-head review.

## Post-merge verification

After merge, verify that `main` contains the reviewed Graphify artifacts and
that the merge introduced no unreviewed indexed-source drift. Do not regenerate
or commit directly on `main`.

If unexpected final-main drift remains, preserve the merged lane evidence and
open or dispatch a separately authorized maintenance lane. That lane repeats
the public refresh, generated-artifact review, and normal readiness gates.
