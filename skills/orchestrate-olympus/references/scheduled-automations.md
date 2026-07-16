# Olympus Codex scheduled automations

## Required persistent automations

Create two local Codex heartbeat automations during cold start:

| Stable name | Exact target | Default cadence | Prompt source |
| --- | --- | --- | --- |
| `olympus-work-orchestrator` | Persistent Orchestrator task ID | Every 10 minutes | `checkpoint.py render-heartbeat` |
| `olympus-pr-review-watcher` | Persistent Reviewer task ID | Every 10 minutes | Reviewer heartbeat in `reviewer-prompt.md` |

Use the native Codex automation tool. These are Codex thread heartbeats, not
standalone cron jobs. Never expose or hand-author raw recurrence rules, edit
automation storage directly, or substitute an operating-system scheduler.

## Creation order

For each persistent role:

1. Inspect existing Codex automations by stable name and target task.
2. Create or recover the role task first and capture its actual task ID.
3. Build the compact role prompt with the actual persistent task IDs and
   validated checkpoint state.
4. Update a matching automation or create it when none exists. Target the exact
   role task, use a local heartbeat every 10 minutes, and set it running only
   when `pause_mode=running`.
5. View the saved automation and verify name, automation ID, target task,
   cadence, destination, prompt, and status.
6. Record the automation ID in the checkpoint before sending the role's
   identity handshake or creating any dependent role.

Never create an automation with a pending, guessed, title-derived, or stale
task ID. Never create a second automation merely because a matching one is
paused. If a stable-name match targets an inaccessible replaced task, retarget
and update it only after preserving the old task state.

## Lifecycle

- On every wake, verify the persistent automations still target the recorded
  task IDs; live automation state supersedes the checkpoint.
- On owner pause or escalation, pause both persistent automations without
  deleting them.
- On explicit resume, complete the recovery audit before setting both running.
- Preserve stable names, cadence, destination, model settings, and IDs unless
  the owner explicitly changes them or a replaced target requires an update.
- If creation or verification fails, enter `ESCALATED`, preserve the live task
  and checkpoint, and do not dispatch implementation work.
