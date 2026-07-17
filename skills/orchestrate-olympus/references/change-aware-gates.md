# Olympus change-aware validation gates

Use this contract to preserve review quality while avoiding work that a later
artifact-only commit cannot invalidate.

## Classify the proposed head

Classify every changed path before reusing evidence:

- `SOURCE`: product code, tests, configuration, dependency or lock files,
  scripts, durable documentation, and comments that can change behavior,
  contracts, acceptance meaning, or agent understanding.
- `DETERMINISTIC_ARTIFACT`: generated Graphify output, screenshots,
  recordings, reports, indexes, or packages reproduced from an already
  reviewed source tree by a recorded command.
- `PROVENANCE_METADATA_ONLY`: a mechanical evidence SHA, path, size, or
  timestamp correction that changes neither source behavior nor the meaning of
  an acceptance claim.
- `MIXED_OR_UNKNOWN`: any head containing an unknown or ineligible path.
  Treat it as `SOURCE`.

A changed test, fixture, selector, semantic document, code comment, or runtime
configuration is `SOURCE`. A file is not an artifact merely because it lives
under `docs/` or was produced mechanically.

Record a deterministic `SOURCE_TREE_HASH` over the tracked source-classified
tree entries, including path, mode, and object identity. Record the path rules
used to compute it. Never infer artifact-only status from a commit message.
Aggregate path classes in this order: any `SOURCE` makes the head `SOURCE`; any
unknown or ineligible path makes it `MIXED_OR_UNKNOWN`; otherwise any
`DETERMINISTIC_ARTIFACT` makes the head `DETERMINISTIC_ARTIFACT`, even with
eligible provenance-only companions; otherwise the head is
`PROVENANCE_METADATA_ONLY`.

## Bootstrap a stable runtime

Before implementation, bootstrap the repository-supported runtime once in the
Worker worktree. Record a `RUNTIME_FINGERPRINT` containing platform, required
Node and pnpm versions, lockfile identity, Playwright package and browser
versions when applicable, and any other toolchain input required by the
repository.

Give concurrent test actors separate repository-supported output, report,
trace, screenshot, and browser-profile directories keyed by lane and actor.
Do not invent environment variables the repository does not support. If a
suite has a shared output lock and no supported isolation seam, serialize that
suite. Runtime or lockfile drift invalidates reusable test evidence.

## Source phase

The Worker completes source implementation, focused tests, and the repository's
required product aggregate before expensive evidence generation. Record every
reusable result as:

```text
TEST_EVIDENCE command=<exact command> scope=<focused|aggregate> required=<true|false>
source_tree_hash=<hash> runtime_fingerprint=<hash> result=PASS
```

Next, the parent Orchestrator dispatches independent one-shot read-only
Standards and Spec axes against the proposed source head. Parallel execution is
preferred when slots are available; sequential execution preserves
correctness. Record separate CLEAN certificates with the source head,
source-tree hash, scope version, and runtime fingerprint.

Any source-axis finding returns the lane to `WORKING`. Do not capture required
screenshots or run the final Graphify refresh until both source axes are CLEAN.

## Evidence and artifact phase

After source CLEAN:

1. Capture required evidence and replay its acceptance path.
2. Run exactly one supported public Graphify refresh for the reviewed source
   tree when required.
3. Commit deterministic artifacts with duplicate hooks suppressed.
4. Run targeted exact-head artifact verification: provenance, reproducibility,
   privacy, integrity, diff, packaging, links, presentation claims, Graphify
   health, and evidence replay.
5. Push the exact artifact-verified head and open or update the PR.

Record a `GRAPHIFY_REFRESH_MARKER` containing source-tree hash, Graphify
version, public command, and generated-output hash. The marker is valid only
when those values still match. Hooks, explicit refreshes, and later phases must
consult it; never run a second public refresh for the same source tree and
expected output merely to recreate already verified bytes.
Also record an explicit Graphify disposition: `not-required`, `current`,
`stale`, or `failed`. `current` requires a matching marker; `not-required`
requires recorded impact evidence and no marker.

Evidence that reveals a source defect returns the lane to `WORKING` and
invalidates source certificates. An artifact defect returns to the evidence or
artifact phase unless repairing it changes a source-classified file.

## Change-aware invalidation

Any commit invalidates the exact-head Reviewer CLEAN and final readiness. It
does not necessarily invalidate source evidence:

| New head class | Reusable evidence | Required reruns |
|---|---|---|
| `SOURCE` or `MIXED_OR_UNKNOWN` | Nothing affected by the changed source | Impacted tests, required aggregate, Standards, Spec, evidence, Graphify when indexed corpus content changed, artifact verification |
| `DETERMINISTIC_ARTIFACT` | Product tests and source-axis certificates when source hash and runtime fingerprint match | Evidence replay, marker/output freshness, privacy, diff, packaging, artifact verification; refresh only if marker inputs or output mismatch |
| `PROVENANCE_METADATA_ONLY` | Same as deterministic artifact, only after the eligibility rule below | Provenance, claims, links, privacy, diff, packaging, targeted artifact verification |

The final reusable Reviewer must still issue one exact-head CLEAN before
readiness. It validates the source certificates, artifact certificate, test
ledger, external feedback, checks, and current diff. It requires newly
dispatched full Standards and Spec certificates when source changed, a
certificate is missing or stale, scope changed materially, or classification
is uncertain; it does not silently manufacture or reuse them.

## Provenance metadata and semantic documents

Use `PROVENANCE_METADATA_ONLY` only when the path is excluded from Graphify's
semantic corpus by reviewed repository configuration, or live Graphify
metadata proves it is not semantically indexed. Otherwise a Markdown change
remains semantic input and requires the public semantic update path.
The metadata must not change the evidence subject, reviewed source-tree hash,
scope version, acceptance meaning, or PASS/FAIL result. A recorded source SHA
identifies the source commit being evidenced, never the containing artifact
commit; otherwise the record would be self-referential. Treat any violation as
`SOURCE` or `MIXED_OR_UNKNOWN`.

Prefer excluding mechanical evidence indexes from the semantic corpus in a
separate reviewed configuration change. Do not hand-edit Graphify output or
call internal APIs to simulate incrementality.

Current public Graphify updates may replace the semantic nodes of an entire
modified Markdown document. Preserving unchanged section nodes inside that
document is an upstream Graphify engine improvement, not behavior this skill
can safely implement. Record the limitation and use supported public commands.

## GitHub Actions degradation

After a documented bounded retry budget with backoff produces repeated
authenticated GitHub Actions endpoint `5xx` or `503` responses, the
Orchestrator may mark `unknown-degraded` and continue only through one initial
branch push and its corresponding WIP PR creation or update when all
corroborating evidence agrees:

- authenticated viewer identity;
- issue assignment and no competing active lane;
- open PR inventory and exact remote branch/head;
- commit status or check-suite surfaces that remain readable; and
- local source, artifact, and privacy gates are clean.

This fallback never means green. Record the failed endpoint, timestamps,
attempts, and corroborating evidence. A successful Actions read and all
required checks are mandatory before final Reviewer CLEAN, readiness, or
merge. After the initial WIP publication, use one bounded Actions wait. If the
endpoint remains unavailable at exhaustion, enter `ESCALATED` with the retry
evidence instead of looping forever. Never use degradation to bypass a known
failure or merge gate.
