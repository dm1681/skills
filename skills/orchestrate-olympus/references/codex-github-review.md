# Final Codex GitHub review

## Contents

1. Gate position
2. Request contract
3. Completion detection
4. Adjudication and action
5. Retry and failure behavior
6. Checkpoint state

## 1. Gate position

Run this gate after exact-head Olympus Reviewer CLEAN and the completed `PRESENTING` audit, but before `READY_FOR_HUMAN_MERGE`, `READY_TO_AUTOMERGE`, or any merge mutation.

Reviewer CLEAN is the authorization event for this final review trigger. Do not
post `@codex review` during `PLANNING`, `WORKING`, `REVIEWING`, `REPAIRING`, or
before the `PRESENTING` audit is complete. Passing checks, a Worker completion
claim, partial Reviewer feedback, or presentation alone does not authorize the
comment. Treat it as the last review request for an approved release candidate,
not as an incremental review-loop trigger.

Require an open, non-draft, mergeable PR whose current head equals the signed persistent-Reviewer clean signal and presented artifact head. Require `pause_mode=running`, no maintained blocker, and unchanged merge authority. Re-read the CLEAN comment, PR conversation, reviews, inline threads, status checks, workflow runs, and existing Olympus Codex-review markers before writing. If CLEAN is absent, stale, unsigned, or names another head, stop without posting.

## 2. Request contract

Use the configured GitHub integration to post exactly one top-level PR comment for the current full head SHA:

```markdown
@codex review

The persistent Olympus Reviewer approved all work at exact head `<FULL_SHA>`. Perform the final pre-merge review. Follow the repository `AGENTS.md` guidance and report actionable defects in the current PR diff.

---
_Olympus Orchestrator · Codex task `<ORCHESTRATOR_TASK_ID>`_
<!-- olympus-codex-review task=<ORCHESTRATOR_TASK_ID> pr=<PR> head=<FULL_SHA> scope=<SCOPE_VERSION> -->
```

The first line must contain the exact `@codex review` trigger. Use the hidden marker and full SHA for idempotency. If that marker already exists for the current head, resume monitoring it; never post a duplicate request. A prior automatic review, older-head request, or non-review `@codex` task does not satisfy this explicit gate.

Record the request comment ID, URL, timestamp, and head in the checkpoint, then enter `CODEX_REVIEWING`. Do not change product code, PR presentation, or merge state while waiting.

## 3. Completion detection

Treat 👀 as acknowledgement that review started, not completion. Complete the external review observation only when the head has remained unchanged and one of these appears after the request:

- a Codex-authored GitHub review submission, with all associated inline threads collected; or
- a Codex-authored 👍 no-finding reaction on the request with no later review threads from that request.

Tie the result to the request timestamp and current full head using available review metadata, reviewed-commit text, and an unchanged-head audit. Do not reuse a review of an older SHA. If the connector output cannot be tied to the requested head, keep the gate pending and report the exact evidence gap.

## 4. Adjudication and action

Send the completed request URL, exact head, review ID or no-finding reaction, and every new inline thread to the persistent Olympus Reviewer. The Orchestrator must not independently decide code correctness.

The Reviewer must:

1. Treat every Codex comment as an allegation, not an automatic finding.
2. Classify the changed surface by Olympus provenance before severity.
3. Identify duplicates of an existing disposition and record one signed no-change or duplicate disposition.
4. Promote each maintained defect into the shared ledger with a stable `PR<PR>-CODEX-<NNN>` ID, exact reviewed head, severity, scope, required actor, evidence, and required outcome.
5. Reply with a signed disposition where useful without resolving threads authored by the Codex integration.

If any blocking finding remains, clear the Olympus clean signal, mark the Codex review as `findings`, enter `REPAIRING`, and notify the existing high-effort Worker. Never post `@codex fix`, create a cloud repair task, or allow the external Reviewer to mutate the branch. After a Worker commit, repeat Olympus exact-head review and wait for a new persistent-Reviewer CLEAN, then complete presentation again before posting a new one-per-head final request.

If no blocking finding remains, the persistent Reviewer posts exactly one signed top-level acceptance naming the full head, request comment, review submission or no-finding reaction, and disposition summary. Mark the Codex review `accepted`; only then may the Orchestrator perform the final readiness and merge audit.

## 5. Retry and failure behavior

Never re-request review for an unchanged head. On each heartbeat, inspect the existing request, reactions, reviews, threads, and PR head.

If no 👀 or review appears for three consecutive checks, verify that Codex code review is enabled and the request is still visible. If the configured GitHub integration cannot expose or repair the required state, enter `ESCALATED` with the exact gap rather than silently skipping the gate. Once 👀 appears, continue monitoring unless the service reports an explicit failure.

If the PR head changes at any point, mark the old Codex review `stale`; it cannot satisfy readiness. Do not dismiss reviews, resolve another author's thread, bypass protection, or merge around an unavailable review.

## 6. Checkpoint state

Use optional `codex_review` state:

```json
{
  "head": "<FULL_SHA>",
  "request_comment_id": 123,
  "request_url": "https://github.com/...",
  "review_id": null,
  "status": "pending",
  "accepted_head": null
}
```

Valid statuses are `pending`, `in-progress`, `findings`, `accepted`, `stale`, and `blocked`. `accepted` requires a review ID or verified no-finding reaction recorded as the review ID, plus `accepted_head` equal to the current head.
