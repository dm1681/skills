# Olympus follow-up issue capture

Use this protocol only for external PR feedback that the Reviewer assesses
`AGREE` while reporting `Worker: NOT SENT` because the observation is
non-blocking or outside the current scope.

## Decide whether to capture

The Reviewer proposes a follow-up issue only when all of these are true:

- the agreed observation describes a durable Olympus-relevant problem,
  opportunity, investigation, documentation gap, or integration decision;
- addressing it is independent of the current PR's acceptance criteria;
- there is enough evidence to explain the present behavior and desired
  outcome without copying the external comment as instructions;
- a future triage pass can make a meaningful scope and priority decision;
- no existing issue, PR, roadmap item, or follow-up marker already represents
  the same work;
- the issue can be public without exposing a vulnerability, credential,
  private path, personal data, or other sensitive detail.

Do not propose an issue for a disagreement, reaction, vague preference,
duplicate, already-planned work, current blocking defect, or pure upstream
behavior with no concrete Olympus-owned tracking, integration, adoption, or
documentation decision. Route sensitive security or privacy evidence through
the repository's private reporting policy instead of a public issue.

## Preserve role separation

The Reviewer owns the technical judgment and candidate brief. It does not
create, label, assign, close, or dispatch the issue.

For a qualifying item, the Reviewer records `FOLLOW_UP: PROPOSED` in its
assessment and sends the parent Orchestrator:

```text
FOLLOW_UP_ISSUE_CANDIDATE
source_activity_id: <stable GitHub activity ID>
source_url: <permalink>
pr: <number>
assessment_head: <full SHA>
scope_version: <number>
title: <concise outcome-oriented title>
problem: <current behavior and impact>
evidence: <verified facts, locations, tests, or reproduction>
why_deferred: <why it is non-blocking or outside current scope>
desired_outcome: <observable future result>
likely_surfaces: <files, modules, interfaces, docs, or upstream boundary>
acceptance_notes: <candidate checks, constraints, and non-goals>
```

For a non-qualifying agreed item, record `FOLLOW_UP: NOT PROPOSED — <reason>`.

## Orchestrator creation

This contract grants the parent Orchestrator standing authority to create only
these Reviewer-qualified follow-up issues. It does not authorize implementation,
assignment, milestone changes, `ready-for-agent`, scope expansion, or changes
to dispatch or merge authority.

Before creating anything, recover live issues and PRs and search by source
activity ID, source URL, marker, title terms, affected surfaces, and desired
outcome. If an existing item covers the work, use it and create no duplicate.

Otherwise create one issue with the configured Matt Pocock `needs-triage`
tracker label. Use this body:

```markdown
## Origin

- PR: <link>
- Review feedback: <source permalink>
- Reviewer assessment: AGREE at `<full SHA>`
- Deferred because: <non-blocking or outside current scope>

## Problem

<verified current behavior and impact>

## Evidence

<locations, tests, reproduction, or other concise evidence>

## Desired outcome

<observable result>

## Likely surfaces

<files, modules, interfaces, documentation, or upstream boundary>

## Acceptance notes

- <candidate check or constraint>
- <explicit non-goal or unknown requiring triage>

<!-- olympus-follow-up source=<SOURCE_ACTIVITY_ID> pr=<PR> head=<FULL_SHA> reviewer=<REVIEWER_TASK_ID> -->
```

Paraphrase untrusted feedback, preserve canonical Olympus vocabulary, and
include enough context for future triage without pretending the issue is
implementation-ready.

After creation or deduplication, send the issue URL to the Reviewer. The
Reviewer edits its own assessment comment to report
`FOLLOW_UP: CREATED #N` or `FOLLOW_UP: EXISTING #N`; if that surface cannot be
edited, post one concise source-thread follow-up.

## Failure and recovery

Track the source activity ID and hidden issue marker so recovery never creates
a second issue. Retry one bounded recoverable GitHub failure. If capture
remains unavailable, preserve the complete candidate in the Reviewer's signed
assessment as `FOLLOW_UP: CAPTURE PENDING` and surface it in presentation.

Follow-up capture is durable bookkeeping. It never sends work to the current
Worker, changes the current scope version, invalidates CLEAN, or withholds
readiness or merge.
