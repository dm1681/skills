# Olympus subagent lifecycle

## Parent-resident control loop

The current parent task is the Olympus Orchestrator. Do not spawn a separate
Orchestrator subagent. Recover live GitHub, checkpoint, worktree, and accessible
subagent state before creating a child.

Use subagent messages and waits as the event loop. Send a follow-up turn when a
role has new work, then wait for its result or for another meaningful event.
Do not poll on a fixed schedule and do not create a scheduled automation merely
to keep the lane alive.

The parent must not send its final response while any of these remain:

- an active Planner, Worker, Reviewer, recovery, or maintenance turn;
- unfinished implementation, review, repair, presentation, or authorized merge;
- CI or another external condition that can be watched with a bounded wait;
- an eligible autonomous queue remains after a merge or lane completion.

During long work, send concise user-visible status updates and continue waiting
internally. A commentary update is not a terminal handoff.

## Role lifecycles

- **Reviewer: reusable.** Spawn or recover the Reviewer before any Planner or
  Worker. Keep the same Reviewer for all exact heads and repair rounds in the
  active parent session. Send follow-up turns for new heads, findings, or scope
  corrections.
- **Planner: one-shot.** Spawn one Planner for one issue or material replan.
  Send its actual `PLANNER_TASK_ID` immediately after creation returns. Retire
  it only after the canonical brief is durable and its worktree is safe.
- **Worker: reusable for the active lane.** Use one Worker for implementation
  and all repairs on that lane. Capture its actual child ID and send
  `WORKER_TASK_ID` immediately after creation returns. Send a follow-up turn
  containing the new exact head, finding ledger, and scope version. Create a
  replacement only after recovery proves the original is inaccessible and
  unique local state is safe.
- **Standards and Spec axes: one-shot and read-only.** After product tests pass,
  the parent Orchestrator dispatches one independent Standards axis and one
  independent Spec axis against the same proposed source head, source-tree
  hash, runtime fingerprint, scope version, and canonical brief. They may read
  the Worker worktree but never edit it or write to GitHub. Each returns one
  signed CLEAN certificate or stable findings to the parent. They do not
  replace the reusable Reviewer or issue final approval.
  Create each from `source-review-axis-prompt.md` and retire it after its
  certificate or findings are captured.
- **Watcher: optional, bounded, and read-only.** A Watcher may observe one
  external condition such as CI completion, mergeability refresh, or a required
  GitHub response. Give it a condition, evidence source, and finite timeout. It
  reports success, failure, or timeout to the parent and then ends. It never
  edits code, mutates GitHub, or becomes a persistent role.

Reserve constrained child capacity in this order: reusable Reviewer, active
Worker, required Standards and Spec source axes, optional Watcher. Retire or
interrupt a Watcher before it prevents a mandatory axis from starting. If only
one review slot is free, run Standards and Spec sequentially; parallelism is an
optimization, not an acceptance requirement.

## Startup order

1. The current parent explicitly assumes the Orchestrator role.
2. Recover existing accessible role subagents and checkpoint IDs.
3. Spawn or recover the Reviewer before any other child role.
4. Record the Reviewer's actual subagent ID and deliver its identity handshake.
5. Verify the Matt Pocock triage-label gate.
6. Spawn a one-shot Planner when planning is required.
7. Spawn or resume the active-lane Worker only after the canonical brief is
   authorized, then immediately deliver its actual `WORKER_TASK_ID`.

Do not parallelize startup in a way that can create duplicate role ownership.
Independent read-only discovery may run in parallel after the Reviewer exists.

## Terminal conditions

The parent may return a final response only when one of these is true:

- `merge_mode=owner-only` and the current lane is truthfully
  `READY_FOR_HUMAN_MERGE`; this is terminal even if autonomous dispatch would
  otherwise have later eligible issues, because the current lane cannot be
  reconciled as merged;
- autonomous merge and post-merge reconciliation are complete and autonomous
  dispatch has no eligible issue remaining;
- the owner explicitly paused or stopped Olympus work;
- the lane entered a genuine `ESCALATED` state that requires owner authority,
  external coordination, or an unavailable capability.

An unavailable scheduled-task feature is not an escalation because scheduled
tasks are not part of this model.

## Session loss and recovery

Subagents keep the lane autonomous only while the parent task remains active.
They do not make the parent self-wake after the task ends, the app exits, or the
machine restarts. GitHub and the checkpoint remain the recovery ledger.

On a new parent task, render the compact recovery prompt with
`checkpoint.py render-resume`, recover live state, and reuse accessible child
tasks by recorded ID. If a child is inaccessible, preserve its worktree and
GitHub state before creating a replacement. Never assume transcript continuity
is more authoritative than the repository, PR head, checks, or finding ledger.
