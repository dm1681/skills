# Olympus pause and recovery

## Contents

1. Owner pause
2. Safe checkpoint
3. Stalled-task audit
4. Recovery Worker
5. Resume and base drift
6. Archive safety

## 1. Owner pause

On `Pause all Olympus work` or an equivalent explicit command:

1. Set `pause_mode=owner-paused` and phase `PAUSED`.
2. Stop new dispatch, implementation, review, presentation, merge, and GitHub writes.
3. Let a currently running atomic command finish when interruption risks corruption; otherwise interrupt safely.
4. Stop sending new child work. Safely interrupt or let the current atomic
   child turn finish according to corruption risk, then keep reusable children
   idle without deleting them.
5. Inspect and record each active task, worktree, branch, exact head, dirty status, and untracked-path inventory.
6. Do not archive a task or delete a worktree merely because work is paused.

An owner-authorized maintenance lane may run while the normal lane stays frozen only when its scope explicitly says so and the checkpoint distinguishes both.

## 2. Safe checkpoint

Record metadata, not sensitive content:

- task IDs, titles, pin/archive status, and last meaningful activity;
- worktree path, branch, local head, remote head, and base;
- staged, modified, deleted, and untracked path names;
- known running command and whether it can finish safely;
- current TDD slice and test state;
- canonical brief URL and scope version;
- PR, findings, checks, clean signal, and next action.

If uncommitted work matters, preserve it before destructive recovery. Use a protected local recovery location and capture tracked binary diff plus required untracked files only after inspecting for secrets. Verify the recovery copy can be read. Do not commit partial work merely to make cleanup convenient unless the Worker contract and owner authorize it.

## 3. Stalled-task audit

Do not infer a stall from elapsed time alone while a known command is running.

- After one missed expected progress interval, inspect task status and terminal/output.
- After two intervals with no meaningful activity and no known running command, send one concise nudge.
- After three intervals with no response, classify the task as stalled and perform the safe checkpoint.

Interrupt only after inspecting state. Never archive or remove the worktree until it is clean or its recovery copy is verified.

## 4. Recovery Worker

When the original Worker is inaccessible:

1. Verify the live PR branch/head and original worktree state.
2. Preserve any recoverable local changes.
3. Create one fresh isolated Worker from the pushed exact head, using `· Recovery` in the title.
4. Give it the current canonical scope version, brief, full finding ledger, and recovery inventory.
5. Apply preserved work only after inspecting it against the live head; otherwise reproduce the failing test and repair anew.
6. Retire the old task only after the recovery Worker is synchronized and no unique local state remains.

Do not create a duplicate PR, branch, claim, or finding ledger.

## 5. Resume and base drift

On explicit resume:

1. Re-read repository instructions and recover live GitHub/task state.
2. Fetch and compare current `main`, lane base, local head, remote head, and dirty worktree.
3. If `main` advanced while the lane was paused, inspect overlapping files, contracts, migrations, and acceptance changes.
4. Preserve dirty work before rebasing, merging, switching, or recreating anything.
5. Resume directly only when the original base remains valid and the scope/test seam is unchanged.
6. Replan or request owner direction for material base drift, conflicts, public-seam change, or incompatible generated artifacts.
7. Restore only the authority modes the owner explicitly resumes.
8. Reuse accessible Reviewer and Worker children only after verifying their
   exact IDs, role state, worktrees, and live lane ownership.

## 6. Archive safety

Archive and unpin a Planner after its canonical handoff is durable. Archive and unpin a Worker after verified merge or explicit lane completion only when:

- the remote branch contains intended commits;
- the worktree is clean, or a verified recovery copy intentionally remains;
- no unique untracked file is being discarded;
- no child turn remains active against that worktree;
- GitHub and checkpoint state identify the successor or terminal state.

Never use destructive Git or filesystem cleanup as an orchestration shortcut.
