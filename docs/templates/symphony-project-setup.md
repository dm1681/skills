## Outcome
Prepare the project's actual repository harness, then configure project-level
Symphony without dispatch. A fresh agent in an isolated checkout can discover
the project, set up its environment, implement bounded work and run meaningful
validation using repository instructions.

## Repository and project context
- Repository URL and selected Linux/WSL checkout: <fill in>
- Linear project UUID and slug ID: <fill in>
- This setup issue's UUID/identifier: <record exactly in Symphony configuration>
- Existing instructions, constraints and safe development access: <verify>

## Source instructions
Read the complete Harness Engineering — Repository Setup Playbook, version 1.4
or later, and record the version actually used:
https://linear.app/diego-mcdonald/document/harness-engineering-repository-setup-playbook-b2e35753abae

Preserve existing work. Implement and validate the smallest useful foundation;
do not stop at an assessment. Use the skills repository's docs/symphony.md for
the delivered project setup commands and runtime validation limits.

## Sequence
1. Run this harness preparation supervised. Reuse the repository's existing
   setup, instructions, diagnostics, validation and CI.
2. Configure project-level Symphony with the exact project and setup issue.
   Install/verify the selected project-local runtime and selected worker skills.
   Setup and check do not dispatch workers or edit Linear templates.
3. Record isolated-checkout, worker discovery, sandbox and runtime evidence.
4. Have a human review the evidence; mark this issue Done only when acceptance
   is satisfied and material limitations are resolved or explicitly accepted.
5. Start Symphony only through a separate explicit start action after the gate
   passes. This issue does not authorize live dispatch.

## Status updates — required
Before implementation, read this exact issue and check for another active owner.
Once repository access is confirmed and authorized setup work starts, change its
status field from Backlog/Todo to In Progress, then fetch it again to verify.
A progress comment alone is not a status update.

At checkpoints and before ending a substantive turn, reconcile actual progress
with status: In Progress while implementation/validation remains; Human Review
when the setup deliverable meets its acceptance bar and awaits human acceptance;
Done only after that acceptance. "Keep incomplete" forbids premature Done; it
does not require Backlog. Do not overwrite a concurrent human decision.

Verify every transition by rereading the issue. If a write fails, record the
failed transition and last verified state; do not claim success. Report the
verified state in the substantive completion response. These updates do not
start Symphony or authorize deployment.

## Acceptance checks
- [ ] Baseline checks and pre-existing failures are recorded.
- [ ] Concise AGENTS.md guidance identifies the project, commands and boundaries.
- [ ] Development setup is repeatable and has safe configuration examples.
- [ ] Fast/full checks and a representative smoke test pass; negative checks fail correctly.
- [ ] Relevant existing architectural invariants and CI/local commands agree.
- [ ] A disposable checkout containing the changes passes the onboarding rehearsal.
- [ ] Worker workspaces and cleanup preserve interactive and sibling work.
- [ ] The launcher explicitly identifies workers and actual Codex discovery enables
      only the selected skills; interactive-only and viz-driven-dev are excluded.
- [ ] The chosen runtime, localhost dashboard and normal sandbox are verified.
- [ ] The exact setup issue belongs to the intended project; incomplete, canceled,
      mismatched or inaccessible issues refuse start.
- [ ] Team states support Backlog, Todo, In Progress, Human Review, Merging, Done,
      and Rework for deliberate full resets.
- [ ] Evidence, failures/skips, authentication prerequisites and remaining risks
      are recorded; no remote CI or rollout success is claimed without observation.
- [ ] A human has reviewed acceptance evidence before marking this issue Done.

## Execution boundaries
No live worker dispatch, unrelated migrations, sandbox bypasses, secrets in
files, production access or implicit deployment. Ordinary setup must not edit
workspace templates. Keep this issue Backlog until repository identity and safe
access are confirmed. Then move to In Progress when supervised implementation
begins, as required above. No ready-for-agent label is required.

Future Symphony tasks use one persistent issue workpad. Human Review is manual;
Todo resumes incremental feedback on the existing PR, Rework resets the approach,
and a human-approved Merging transition authorizes the upstream land workflow.
