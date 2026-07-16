# Olympus orchestration core contract

## Contents

1. Authority controls
2. Lane types and WIP
3. Durable state
4. State machine
5. Issue selection
6. Role boundaries
7. Readiness, final Codex review, and merge
8. Task and comment discipline
9. Post-merge reconciliation

## 1. Authority controls

Track three independent controls:

- `dispatch_mode`: `human-controlled` or `autonomous`.
- `merge_mode`: `owner-only` or `autonomous`.
- `pause_mode`: `running`, `owner-paused`, or `escalated`.

Start with `human-controlled`, `owner-only`, and `running`. Only an explicit owner command changes a control. Enabling autonomous dispatch does not enable autonomous merge. Enabling autonomous merge does not authorize force, bypass, review dismissal, or unrelated mutations.

Recognize these owner controls exactly:

- `Approve #N`: authorize one normal issue lane.
- `Enable autonomous dispatch` / `Disable autonomous dispatch`.
- `Enable autonomous merge` / `Disable autonomous merge`.
- `Pause all Olympus work`: set `owner-paused`, stop new mutations, preserve state, and pause heartbeats.
- `Resume Olympus work`: perform the resume audit before setting `running`.

`owner-paused` and `escalated` override dispatch and merge authority. An escalation stays suspended until the owner resolves it and explicitly resumes the affected authority.

## 2. Lane types and WIP

Use one `lane_kind`:

- `none`: no implementation lane.
- `issue`: new issue from Planner through PR.
- `repair`: existing PR repair from its live exact head.
- `maintenance`: explicitly owner-authorized repository management with no product behavior expansion.

Maintain exactly one running implementation lane and at most one open Worker PR. A safely checkpointed owner-paused lane may coexist with one explicitly authorized maintenance lane only when the paused lane has no open Worker PR; it performs no work or GitHub writes.

For a maintenance lane, create a concise canonical mini-brief containing exact base/head, authorized paths and behavior, ownership boundary, non-goals, verification, GitHub write authority, merge authority, and scope version. A separate Planner is optional only while the work remains repository management. Route any product behavior, public interface, schema, migration, security posture, architecture, or dependency decision through the normal Planner gate.

## 3. Durable state

GitHub is the durable audit ledger. Codex task IDs, worktree paths, pins, heartbeat state, and checkpoint files are host-local coordination state.

Keep the heartbeat prompt minimal: role identity, stable skill name, Reviewer/Orchestrator task IDs, and a validated compact checkpoint. Do not duplicate this contract in automation prompts.

When `graphify-out/` exists, use `$graphify` first for architecture, file-relationship, or project-content questions. Treat its tracked output as derived evidence: refresh it only through supported public tooling and apply the generated-artifact review boundary.

Before every mutation:

1. Read repository instructions and relevant domain, ADR, and acceptance material.
2. Inspect live issues, blocker edges, labels, assignments, linked/open PRs, comments, reviews, inline threads, exact heads, checks, and mergeability.
3. Inspect role tasks, worktrees, pins, archives, and automations.
4. Compare live state with the checkpoint; live evidence wins.
5. Validate the current scope version and authority modes.
6. Act only on a transition, explicit handoff, owner command, or unfinished in-scope work.

Required compact checkpoint fields are defined by `scripts/checkpoint.py`. Record dirty status and untracked-path inventory without copying sensitive contents into the checkpoint.

### Orchestrator-first startup order

Use this sequence for every cold start or role recovery:

1. Inspect live tasks and checkpoints before creating anything. Reuse an
   accessible persistent Orchestrator instead of duplicating it.
2. If none exists, create the persistent Orchestrator as the only role task.
   Do not include Reviewer, Planner, Worker, recovery, or maintenance creation
   in the same tool batch or parallel dispatch.
3. Wait for the Orchestrator creation call to return. Capture its actual task
   ID, title it `Olympus · Orchestrator · Persistent`, pin it, and record it in
   the checkpoint.
4. Send the Orchestrator identity handshake and confirm that task is live.
5. Have the live Orchestrator create or recover the persistent Reviewer next.
   Capture, pin, and record the Reviewer's actual task ID before either role
   authorizes GitHub writes.
6. Create a Planner, Worker, recovery, or maintenance task only after both
   persistent task IDs are known and recorded.

Never batch or parallel-create the Orchestrator with another role. If dependent
tasks survive but their Orchestrator is inaccessible, leave them stopped,
preserve their state, and establish the replacement Orchestrator first.

## 4. State machine

Normal lane:

```text
IDLE -> RECOMMENDED -> PLANNING -> WORKING -> REVIEWING
REVIEWING -> REPAIRING -> REVIEWING (zero or more loops)
REVIEWING --persistent Reviewer CLEAN--> PRESENTING
PRESENTING --audit complete, CLEAN still valid--> CODEX_REVIEWING
     -> REPAIRING|READY_FOR_HUMAN_MERGE
```

With autonomous merge authority, the final states are:

```text
CODEX_REVIEWING -> REPAIRING|READY_TO_AUTOMERGE
READY_TO_AUTOMERGE -> MERGING -> MERGED_ARCHIVE -> IDLE
```

Maintenance lane:

```text
IDLE|PAUSED -> MAINTENANCE_WORKING -> REVIEWING|REPAIRING
REVIEWING --persistent Reviewer CLEAN--> PRESENTING
PRESENTING --audit complete, CLEAN still valid--> CODEX_REVIEWING
            -> REPAIRING|READY_FOR_HUMAN_MERGE|READY_TO_AUTOMERGE
```

Any active phase may enter `PAUSED` from an owner command or `ESCALATED` from a blocking decision. Resume only through the audit in `pause-and-recovery.md`.

## 5. Issue selection

Exclude parent specs, closed issues, issues without `ready-for-agent`, issues with open declared blockers, claimed issues, issues represented by an open PR, and issues represented by an active Planner or Worker.

Rank the eligible frontier by:

1. downstream critical-path unlocking;
2. risk reduction;
3. smallest coherent vertical slice;
4. lowest issue number.

In human-controlled mode, recommend exactly one issue and wait for approval. In autonomous mode, dispatch the top issue only while `pause_mode=running`, no lane is active, and no escalation exists.

## 6. Role boundaries

- Orchestrator: choose and report the path, maintain authority and checkpoint state, create/steer tasks, reconcile scope, present artifacts, issue the single exact-head final `@codex review` request, and perform an authorized final merge audit. Do not implement or independently review product code.
- Planner: plan one issue or material repair from an exact SHA; remain read-only for product code.
- Worker: implement or repair one lane, use TDD at established seams, verify documented public commands, update tracked generated artifacts only through supported tools, and never approve or merge.
- Reviewer: independently review exact-head Olympus-owned work, classify provenance before severity, verify fixes, resolve only Reviewer-authored threads, and never implement, approve, or merge.

Use the role-specific prompt references. Obtain actual task IDs before authorizing GitHub writes.

## 7. Readiness, final Codex review, and merge

Readiness requires:

- one signed persistent-Reviewer CLEAN signal approving all work at the exact full head SHA;
- one completed explicit `@codex review` request made only after that CLEAN signal and completed presentation for the same head, plus a signed persistent-Reviewer acceptance of its result;
- explicit shared disposition for every blocking finding;
- required checks successful, including new repository-owned suites in any documented aggregate;
- documented setup/runbook commands verified at their real public seam when materially affected;
- no unresolved blocking conversation or review state;
- a mergeable current head;
- no escalation or pause;
- a completed presentation gate with current artifact links and truthful limitations.

Any new commit invalidates readiness, the Olympus clean signal, and the final Codex review. PR-body-only presentation changes require a final head/check/thread re-audit but not a new code review when the head is unchanged.

With `merge_mode=owner-only`, never approve or merge. With `merge_mode=autonomous`, re-audit every gate immediately before using the repository's allowed non-forced merge method. Never bypass protection, force, dismiss review, or resolve another author's blocker to satisfy policy.

## 8. Task and comment discipline

Use actual task IDs in one visible signature and one hidden marker. Only `notify=<role>` is a cross-role trigger. Update canonical artifacts instead of posting duplicates. Do not post no-change heartbeat comments.

Never post `@codex review` before the persistent Reviewer approves all work with exact-head CLEAN. After CLEAN and completed presentation, post exactly one final request per exact head. Use the full-SHA `olympus-codex-review` marker to resume monitoring instead of duplicating the trigger. Never use `@codex fix` to create a second implementation actor.

Standard task titles:

- `Olympus · Orchestrator · Persistent`
- `Olympus · Reviewer · Persistent`
- `Olympus · Planner · Issue #N`
- `Olympus · Worker · Issue #N / PR #P`
- `Olympus · Setup · Topic · PR #P`

Pin persistent roles and active one-shot tasks. Archive and unpin a one-shot task only after merge or explicit lane completion and after its worktree is clean or safely preserved.

## 9. Post-merge reconciliation

After merge, verify the PR merged, the issue closed when applicable, and `main` advanced to the expected commit. Inspect tracked Graphify artifacts or other derived evidence for final-main drift; refresh through supported public tooling in a separately authorized change if needed rather than silently writing to `main`.

Archive completed one-shot tasks and heartbeats, update the checkpoint, recompute the frontier according to dispatch mode, and keep owner-paused lanes paused. A PR-only maintenance lane completes without inventing an issue.
