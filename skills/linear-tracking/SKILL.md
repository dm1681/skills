---
name: linear-tracking
description: "Procedure for tracking work on a Linear issue in a repository whose AGENTS.md names a Linear project: resume, claim, state and label changes, handoff. Use when starting or resuming work on a tracked issue, changing an issue's state or labels, recording a handoff before stopping, or when Linear cannot be reached."
version: 1.0.0
---

# Linear tracking

The procedure for work tracked in Linear. Three sources share the subject:

- The global agent instructions hold what every reply needs: naming an issue by
  its slug, self-contained writing, and the three status rules.
- This skill holds the procedure those rules point at.
- The repository's `AGENTS.md` holds the mapping: project, team, state names and
  exceptions. Where it differs from this skill, the repository wins. A prompt
  that replaces the claim and handoff protocol, as a dispatched agent's does,
  wins too.

Nothing here grants authorization to execute, message or publish. Use only the
actions authorized for the current task.

## Status synchronization

This applies to every authorized session working a mapped issue, including
supervised setup work. Comments and checklists do not change the issue's status
field.

- Before substantive implementation, read the issue's current state and ownership.
  When authorized work begins from Backlog/Todo, set the mapped active state
  (In Progress here) and fetch the issue again to verify it.
- At meaningful checkpoints and before ending a substantive work turn, reconcile
  actual progress with the issue state. Keep In Progress while implementation or
  required validation remains. Move to the mapped review state only when its
  acceptance bar is met and the work is ready for human review. Follow explicit
  blocker exceptions instead of silently resetting started work to Backlog.
- After every state mutation, fetch the issue by its exact ID and verify the
  state field. A successful comment edit or mutation request alone is not proof.
  Respect a concurrent human change; do not blindly overwrite it.
- "Keep incomplete until reviewed" means do not mark Done; it does not mean keep
  Backlog.
- If access or authorization prevents a transition, report the failed transition
  and last verified state in the existing progress record and final response.
  Continue only independently authorized work; never claim the state was updated.
  Otherwise include the verified issue state when reporting substantive completion.

## The procedure

1. **Resume:** verify Linear access on this device/session. Read the mapped
   project's Current overview, the matching issue, its dependencies and latest
   handoff/comments. Reconcile them with the actual remote, branch, HEAD,
   worktree and uncommitted changes before choosing the next action. Reuse the
   existing issue; search before creating one within the authorized scope.
2. **Claim:** check the assignee, In Progress state and latest ownership record
   for another active session. Resolve an overlapping claim before editing.
   Record the agent/session or task, branch, worktree and starting HEAD on the
   issue, then set In Progress and remove `ready-for-agent`. Re-read ownership
   before starting; a comment alone is not an atomic lock. If an authorized
   claim cannot be recorded, report that limit and keep a local record.
3. **Track:** use the rules under "States and labels" and record dependency links and
   blockers as they change. Use the repository's documented equivalents when
   names differ; report missing configuration instead of creating a workflow.
4. **Handoff:** at meaningful checkpoints and before stopping, record completed
   work, acceptance evidence and tests (including failures, skips and untested
   environments), blockers, branch/commit/worktree, uncommitted files and the
   exact next action. Identify who owns the next step and whether this session
   has released its claim. After substantive work, refresh the project's
   Current overview with the current milestone, verified result, active work,
   blockers and next action, retaining unrelated project context.

## States and labels

| State or label | Use |
| --- | --- |
| Backlog | Future or blocked work; state the blocker and remove `ready-for-agent`. |
| Todo + `ready-for-agent` | Clear acceptance criteria, dependencies satisfied, available for an agent to claim. |
| In Progress | Claimed work; remove `ready-for-agent`. |
| In Review | Implementation ready for pending review; link the evidence and remaining review action. |
| Done | Acceptance criteria verified with evidence; distinguish local completion from merge/deployment when those are required. |
| `needs-decision` | A concrete user question with options and a recommendation; remove after recording the resolution. If it blocks work, use Backlog and remove readiness. |

## When Linear cannot be reached

If the mapping, connection or write authorization is missing, preserve a pending
handoff in the repository's chosen location (default
`docs/handoffs/<issue-or-task>.md`) with the same fields and the missing input.
Continue independent authorized work; do not guess a project or report a claim
or sync as successful. When access returns, reconcile current Linear state
before publishing an authorized pending handoff. These instructions neither
install nor authenticate the connector: verify access separately on each device
and keep credentials out of synced files.
