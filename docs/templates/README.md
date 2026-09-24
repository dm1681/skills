# Linear template reconciliation

These files are the exact replacement bodies for existing native Linear templates,
not a substitute for applying them in Linear:

- `symphony-project-setup.md`: embedded setup issue in workspace project template
  **Agent-Ready Software Project**, ID `d8000a8e-a285-4dbe-9a1b-c1caaa2fc96c`.
- `symphony-agent-task.md`: description in workspace issue template **Agent task**,
  ID `82789dda-2d26-4808-a957-a43e3dfba272`. Preserve its Backlog initial state.

Keep the project template's setup issue Backlog, with no agent delegate and no
automatic dispatch. Preserve unrelated template metadata and team defaults.
The actual team-default selection has not been verified.

Applied and verified on September 23, 2026 (02:50 UTC September 24): both existing
native templates were updated through Linear's authenticated public GraphQL API,
after inspecting the live schema. Exact native `templateData` readback matched;
existing assignment, Backlog state, native playbook mention and unrelated
metadata were retained. No issues were created or moved to test the templates.
The master playbook is now version 1.4. Both templates also require status
updates at pickup/checkpoints/completion and fresh issue readback after each
transition; incomplete setup must not remain in Backlog once work starts.

The connector still lacks template-edit operations and Computer Use still fails
WSL initialization, but neither blocks this completed API update. This was the
one-time implementation closeout; ordinary setup never edits templates.
Native project template updated at `2026-09-24T02:50:44.313Z`; Agent task template
updated at `2026-09-24T02:50:44.758Z`. Local before/after payloads are retained in
the ignored `.symphony/` directory without credentials.

Existing copied issues do not update with their templates. DIE-60 is the pilot's
setup issue and is reconciled directly. DIE-58 and DIE-59 remain separate project
setup work; preserve their no-dispatch boundaries and explicitly reconcile them
before treating the new template as applied there. In particular, DIE-59 does
not authorize installing/activating Symphony during its current harness task.
