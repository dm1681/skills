## Outcome
What should be true when this task is finished?

## Context
Repository/project, relevant files, accepted decisions, glossary/ADRs, related
issues and evidence links. Resolve preparation questions interactively before
queueing this task for Symphony.

## Scope
Included work, constraints and explicit boundaries.

## Acceptance and validation
- [ ] Observable result and the command or evidence that verifies it.
- [ ] Required tests, project checks, runtime evidence and human review.

## Dependencies
Use native blocks/blocked-by relations for real implementation prerequisites,
related links for nonblocking follow-ups, project membership for routing, and an
attached PR for review. The project startup gate checks its exact Done setup
issue; every task does not need a blocker link to that issue.

## Required status verification
Read this exact issue's current state and ownership before implementation.
For authorized Todo work, update the status field to In Progress and fetch the
issue again before starting. Workers must not self-dispatch Backlog work or
restart Human Review/Merging/terminal work outside the established routing.

Reconcile status at meaningful checkpoints and before ending a substantive turn.
Verify every transition with a fresh issue read, including Human Review and Done.
A workpad edit alone does not update status. If a transition fails, record the
failure and last verified state instead of claiming success. Respect concurrent
human changes and retain the workflow's completion and blocked-access rules.

## Execution workflow
Prepared work enters Todo. Symphony transitions it to In Progress and keeps one
persistent `## Codex Workpad` comment containing plan, acceptance, validation,
progress and blockers. Resume that workpad and actual repository state. Do not
use the old readiness-label claim/removal protocol, project Current overview
updates or separate handoff documents for worker execution.

After passing project checks and PR feedback sweeps, return to Human Review.
A human runs code-review and posts actionable findings on the PR. Move incremental
feedback on the attached PR to Todo; PR comments alone do not dispatch a worker.
Rework is a deliberate full reset of the PR, branch and workpad. Following human
approval, move to Merging, follow the upstream land workflow and mark Done after
merge. Creating this issue does not start Symphony or grant extra execution rights.
