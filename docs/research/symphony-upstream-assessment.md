# Symphony compatibility assessment

Assessment date: 2026-09-23. Upstream revision: `be10a1b79df723d6d7612b5651c8522704dafb2e` (`main` resolved with `git ls-remote`; the temporary clone's `git rev-parse HEAD` matched). Source inspection only; no Symphony service, tracker mutations, or end-to-end integration tests were run. This note separates the portable specification, Elixir reference implementation, and the example workflow prompt.

## What was compared locally

Local baseline: `d8641f5c793a510addb44a06cb42c7db6bc0af69` plus the existing working-tree edits, inspected on 2026-09-23. These are documented policies, not proof that every current agent session loads or enforces them.

| Local source | Current contract | Consequence for adoption |
| --- | --- | --- |
| [Global Linear workflow](../../global/AGENTS.md#linear-work-tracking-and-handoffs) | Resume from Current overview and handoffs; check session ownership; claim and remove readiness; record evidence, claim release and next owner. | Preserve this protocol in the worker prompt and admission process. Symphony's internal claim is insufficient for coordination with desktop agents. |
| [Implement fork](../../skills/implement/SKILL.md) | Choose all-at-once or section-by-section before coding; TDD where appropriate; two-axis code review; commit. | Dispatch only work whose pacing is already decided. Keep interactive slices outside unattended execution. |
| [Repository agent guide](../../AGENTS.md#review-agents) and [visualization skill](../../skills/viz-driven-dev/SKILL.md) | Announce each review round against its revision; satisfy required checks; visualize the hypothesis before implementation and regenerate against real output. | Explicitly carry these gates into the custom workflow and provision the tools they require. |
| [Loading matrix](../agent-support.md#global-instruction-loading) and [Linear delivery guidance](../linear-workflow.md#deliver-and-verify-the-guidance) | Installing skills, loading instructions and connecting Linear are separate checks. | Verify all three inside an actual worker environment. |

Live filesystem inspection found `C:/Users/hbar6/.codex/AGENTS.md` empty, no `AGENTS.override.md` at that default location, and the shared/Claude pointer chain leading to this checkout's `global/AGENTS.md`. This does not prove a future worker lacks all guidance: project instructions or other explicit configuration could load it. It does establish that the existing default Codex global file supplies none. [Official Codex instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md) documents that entry point separately from skill discovery.

The Linear guidance and implement fork are still local, uncommitted changes. A remote clone cannot acquire those changes from this checkout's working tree. The [DIE-32 handoff](../handoffs/DIE-32.md) also records incomplete device rollout and no verified Linear project mapping for this skills repository; this assessment did not query the live tracker to refresh that historical mapping status.

The local [GitHub identity rules](../../global/AGENTS.md#github-identities-and-ssh-remotes) require account-specific SSH aliases and a verified identity before writes to the pseudonymous account. Worker provisioning must preserve that account separation. Copying a generic clone hook and relying on the host's current default `gh` account would not establish compliance.

Graphify's launcher failed with `Failed to canonicalize script path`. Existing graph nodes and edges identified the instruction installer; current files supplied the workflow evidence. No code was modified or tests rerun for this source assessment.

## Upstream findings

### 1. A readiness label removed on claim cannot also be a required Symphony label

The current version **does support label gating**. However, `tracker.required_labels` applies to admission, running-task reconciliation, per-turn continuation, and retry eligibility. It is not an admission-only filter. In `Orchestrator.reconcile_issue_state`, losing routing eligibility terminates the active worker without removing its workspace. `issue_routable?` delegates to `Issue.routable?`, which requires every configured label. `AgentRunner.continue_with_issue?` and `retry_candidate_issue?` enforce the same rule. Consequently, configuring `required_labels: [ready-for-agent]` while the agent's Claim procedure removes `ready-for-agent` stops that worker on the next reconciliation. The example polling interval is five seconds.

Sources: [configuration notes](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/README.md), [orchestrator](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/orchestrator.ex), [issue routing](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/tracker/issue.ex), [continuation](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/agent_runner.ex).

Integration implication: preserve the existing readiness semantics by adding an initial-admission predicate distinct from continued ownership, or explicitly revise the workflow's label contract. A durable Symphony routing label alone does not enforce the separate initial `ready-for-agent` gate. Admission, restart recovery, reconciliation, and retry must be designed together.

### 2. Process-local claims do not implement cross-session ownership

The orchestrator's `claimed`, `running`, and `blocked` maps prevent duplicate dispatch within that orchestrator. They do not themselves reserve work against a separately running desktop session or another orchestrator. The specification explicitly describes in-memory scheduler state and tracker/filesystem-based restart recovery. Linear assignee routing is available, including `me`, but it checks an assignee identifier rather than the user's session ownership comments. With no configured assignee, the Linear adapter accepts any assignee. Its polling query includes issue fields and blockers but does not read project Current overview or session handoff comments. Agents can fetch these through the injected Linear tool, so the missing protocol can be supplied in the custom prompt or a claim integration.

Sources: [specification, sections 4, 7, 17](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/SPEC.md), [orchestrator claim checks](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/orchestrator.ex), [Linear query and assigned_to_worker?](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/linear/client.ex).

### 3. The example's state machine and audit trail differ from the local cycle

The sample treats `Todo`, `In Progress`, `Merging`, and `Rework` as active; `Human Review` is a non-active human handoff. It moves Todo to In Progress immediately, uses a single `## Codex Workpad` comment for progress and completion, routes certain access blockers to Human Review, and has a human move approved work to Merging before the agent lands the PR and marks Done. Its Rework procedure explicitly closes the existing PR, removes the existing workpad comment, and starts a new branch from origin/main. These are example prompt choices, not requirements of the scheduler. The spec explicitly allows success at a workflow-defined handoff state and does not require Done or a particular merge policy.

Sources: [sample WORKFLOW.md, Status map and Steps 0-4](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/WORKFLOW.md), [specification, Important boundary](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/SPEC.md).

Integration implication: retain local In Review, Backlog/needs-decision, explicit claim/handoff records, project Current overview, and preservation of previous review rounds. Replace the sample Rework reset rather than importing it wholesale. A custom WORKFLOW.md can refer to the canonical instructions instead of establishing a competing protocol.

### 4. Interactive pacing needs an unattended counterpart

The sample prompt says this is unattended and forbids asking humans to perform follow-up actions. In the current reference implementation, ordinary Codex `requestUserInput` and approval/elicitation requirements become blocked runtime entries with the issue still claimed. Blocks are in memory only; the README warns that restarting the orchestrator clears them and can make still-active issues eligible again. The sample sets `approval_policy: never`; AppServer sets `auto_approve_requests` when that value is used and automatically accepts command/file approval requests. Omitted policy defaults are different and more restrictive. Neither posture is mandated by the specification.

Sources: [sample instructions and policy](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/WORKFLOW.md), [blocked-state and policy documentation](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/README.md), [AppServer input and approval handling](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/codex/app_server.ex).

Integration implication: decide task scope and pacing before dispatch; make unresolved decisions durable tracker blockers using the local protocol. Do not rely on an in-memory operator-input block as the sole durable pause. Preserve any explicit stop/resume gates in tracker state and dispatch eligibility.

### 5. The reference runtime assumes POSIX shells

Local AppServer launch calls `System.find_executable("bash")`, then runs `bash -lc`; workspace hooks execute `System.cmd("sh", ["-lc", command], ...)`. The documented packaged release targets are macOS and Linux. The sample hooks use POSIX shell syntax and `mise`/Elixir tooling. This is not a native PowerShell drop-in. A Linux/WSL/remote-worker deployment or a Windows port requires deliberate setup and validation; the inspected source does not establish that Git Bash alone is sufficient.

Sources: [AppServer start_port](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/codex/app_server.ex), [Workspace run_hook](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/workspace.ex), [runtime and release documentation](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/README.md).

### 6. New issue workspaces need explicit instruction and skill provisioning

The runner creates/reuses a workspace per issue and executes hooks before starting Codex. The sample's `after_create` clones the upstream repository; the README directs adopters to customize this hook and optionally copy its commit/push/pull/land/linear skills. Symphony starts a separate `codex app-server` process in that workspace. This does not establish that the desktop task's injected instructions, app tools, uncommitted local skills, or connected accounts will be available there. The service does inject a provider-native tracker tool using host-side credentials.

Sources: [agent runner](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/agent_runner.ex), [workspace setup and tracker-tool documentation](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/README.md), [sample hook](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/WORKFLOW.md).

Integration implication: version and provision the intended AGENTS guidance, skill collection and tools into the actual worker environment; verify what that Codex process loads. Explicitly retain local TDD, two-axis review, per-revision review-start notices and required checks in the workflow contract. The sample's self-review/PR-feedback sweeps are not evidence that those local gates execute.

### 7. Retries and terminal cleanup change the meaning of a finished session

Normal worker completion while the issue remains active schedules a short continuation; `agent.max_turns` bounds one invocation rather than total issue lifetime. Failure retries use backoff. Terminal transitions stop the agent and clean its issue workspace; startup also removes workspaces associated with terminal issues. Therefore a conversational final response alone is not a durable stop, and marking an issue Done can remove its local workspace even when the user's own Done semantics do not require merge.

Sources: [specification, sections 7-9](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/SPEC.md), [orchestrator handle_agent_down, retry_delay and cleanup](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/orchestrator.ex), [max_turns and cleanup notes](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/README.md).

Integration implication: complete durable handoff/evidence and preserve required branch/artifact state before a terminal transition; use a non-active, non-terminal handoff or blocked state when work must remain recoverable.

## Overall upstream assessment

The architecture is compatible with a tracker-driven agent cycle after adaptation. The example is not safe to copy unchanged into this particular cycle. The strongest technical mismatch is readiness-label removal versus required-label continuation. The remaining principal gaps are cross-session ownership, local state/audit semantics, interactive pacing, environment provisioning, and Windows runtime assumptions. No deployment or change to the existing workflow is implied by this assessment.

## Recommended integration boundary

Keep planning and pacing decisions in the current interactive cycle. Treat Symphony as an optional executor for already-scoped, all-at-once work, returning to the existing In Review gate.

1. Establish an admission step that verifies acceptance criteria, dependencies, authorization and absence of a competing owner. Only then assign a persistent routing label such as `symphony-owned` and the intended worker identity. Keep `ready-for-agent` as an admission signal; remove it on claim as today. A persistent label is safe only if that admission process controls who receives it; configuration alone does not enforce the readiness rule.
2. Give a custom WORKFLOW.md explicit references to canonical guidance and the approved pacing choice. Include TDD, visualization, two-axis review, review-start notices, validation evidence, Current overview updates and claim release. Preserve old PR/workpad evidence during rework.
3. Keep In Review and Backlog outside active states. Persist decisions/pauses in the tracker; define separate merge authorization. Export required artifacts and push authorized work before terminal cleanup. A failing `before_remove` hook does not prevent deletion in the reference Workspace implementation, so it cannot be the sole preservation gate.
4. Provision the actual worker host, account-specific remotes, credentials, skills and instruction loader. Test one isolated issue before enabling concurrent dispatch. A native Windows installation is unverified; POSIX assumptions need a deliberate host choice or port.
5. Verify five adoption gates: unready work never starts; removing readiness after a valid claim does not stop work; a desktop-owned issue is not taken over; a decision pause survives restart; and review/Done transitions preserve required evidence. Add explicit task-wide cost/runtime limits for bounded experiments rather than interpreting `max_turns` as such a limit.

These are proposed adaptations, not changes made by this assessment.

## Follow-up: Matt Pocock skills with Symphony as workflow authority

The user subsequently chose to defer the earlier workflow conflicts to Symphony. The preservation-oriented recommendations above describe the original comparison; they are not a requirement to retain the old cycle. No installed skills or runtime settings have been changed.

Checked the installed shared skill root and its `.skills-external.json`: Matt collection `v1.2.3`, commit `6acc160e4e0cd062dbbbd7a1b26ae92855edf07e`. This compares that installed version, not an assertion about latest upstream. The installed `implement` is the local fork; [upstream implement at the installed pin](https://github.com/mattpocock/skills/blob/6acc160e4e0cd062dbbbd7a1b26ae92855edf07e/skills/engineering/implement/SKILL.md) does not contain the pacing interview.

The collections are compatible when Symphony owns dispatch, issue lifecycle, workspaces and landing, and the relevant Matt skills supply preparation and coding practices. Simply loading all skills into an unattended worker does not resolve their explicit interactive requirements.

| Skill or concern | Compatibility finding | Treatment with Symphony in charge |
| --- | --- | --- |
| `tdd` | Explicitly requires user-confirmed test seams before any test; the red/green, public-interface and vertical-slice practices themselves fit. | Confirm the seams in the approved brief before dispatch. Allowing workers to choose new seams autonomously would be an intentional override of this skill. |
| `code-review` | Standards/spec review fits, but it asks for a missing comparison base or specification. Symphony's PR-feedback sweep does not itself perform this two-agent review. | Supply a concrete base revision and issue/spec, provision subagent support, and invoke the review explicitly if retaining it. Ensure implementation commits are included: its comparison is against HEAD, not uncommitted files. |
| `grilling`, `loop-me`, `to-spec`, `to-tickets`, `triage`, setup | Several explicitly wait for user decisions or approval. `loop-me` designs workflow specs; it is not another execution scheduler. | Run preparation before admission. `ask-matt`'s fresh-context-per-ticket route aligns with Symphony's issue workers. |
| Tracker, labels and briefs | Setup supports Linear/custom trackers despite its GitHub default. Tickets use `ready-for-agent`, which by itself does not affect the sample's state-based dispatch. Triage's authoritative Agent Brief is a comment. | Configure the same tracker, map readiness to Symphony's lifecycle, and ensure workers retrieve the accepted brief. Do not equate `ready-for-human` with one state: its issue and PR meanings differ. |
| Wide refactors and handoffs | `to-tickets` permits shared integration branches with green checks promised only at final integration. That conflicts with the sample's independently green PR flow. `handoff` writes to OS temp outside the repository. | Prefer independently green tickets or deliberately configure an integration branch exception. Use Symphony's workpad for worker continuity rather than assuming a temporary handoff file transfers across workers. |

Additional loading caveat: Matt's setup skill prefers editing an existing CLAUDE.md. Ensure the resulting tracker/domain references are also reachable from Codex's discovered instructions; that preference is not proof Codex loads them.

Installed evidence: [TDD](C:/Users/hbar6/.agents/skills/tdd/SKILL.md:22), [review](C:/Users/hbar6/.agents/skills/code-review/SKILL.md:17), [router](C:/Users/hbar6/.agents/skills/ask-matt/SKILL.md:21), [tickets](C:/Users/hbar6/.agents/skills/to-tickets/SKILL.md:39), [triage brief](C:/Users/hbar6/.agents/skills/triage/AGENT-BRIEF.md:3), [handoff](C:/Users/hbar6/.agents/skills/handoff/SKILL.md:7), [setup](C:/Users/hbar6/.agents/skills/setup-matt-pocock-skills/SKILL.md:37). The [pinned upstream TDD source](https://github.com/mattpocock/skills/blob/6acc160e4e0cd062dbbbd7a1b26ae92855edf07e/skills/engineering/tdd/SKILL.md) independently confirms the test-seam approval requirement.
