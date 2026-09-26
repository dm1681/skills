# Consolidating the personal AI development workspace

Research date: 2026-09-24. Primary-source documentation review; no candidate was installed or trialled, and no running service or external record was changed. Product capabilities below are documented, not validated in this user's environment. Sources are linked beside the claims they support.

## Decision

There are credible ways to reduce the number of interfaces, but no verified drop-in product satisfies every requirement. **Paperclip is the closest candidate for replacing the issue tracker and unattended-worker coordinator together. OpenHands Agent Canvas is the strongest documented candidate for interactive coding plus unattended automation across several execution hosts. GitHub is the strongest hosted single-product alternative.** These are fit judgments based on the evidence below, not measured usability rankings.

The key distinction is between **one interface** and **one system**. Keeping Linear as the authoritative tracker means a new agent frontend can consolidate day-to-day interaction without eliminating Linear. Actually replacing all three tools requires moving issue history/workflow into the replacement, as well as moving agent execution. Browser access from three computers is also different from executing agents on all three computers.

## Requirements carried forward

- Personal use; always-on Ubuntu host Hades; LAN access with VPN away from home.
- Find and resume work across three computers, organized by project, with clear host and status information.
- Attention items first, concise progress/next-step refreshers, traceable decisions and results.
- Browser/mobile convenience, image input, accessible completed history, no remote desktop.
- Existing Codex/Claude desktop-session discovery is desirable, but no replacement should require reverse engineering their interfaces.
- Asynchronous issue/comment conversation is acceptable; the worker must appear under a distinct identity.
- Seven-day inactivity reminders, one-week snooze, and explicit archiving are desired conveniences, not permission to build them now.
- Avoid a custom dashboard unless an actual remaining gap warrants it. New deterministic update hooks are deferred.

## Shortlist

| Candidate | Consolidation potential | Fit for Hades and three machines | Principal limitation | Evidence confidence |
|---|---|---|---|---|
| Paperclip | Native issues, agent identities, comments, work tracking and automated execution; strongest potential three-to-one replacement | Self-hostable; local Codex/Claude adapters execute beside the server; arbitrary other hosts need separate integration validation | Not established as a turnkey browser for existing sessions on three machines | High for task/conversation model; incomplete for remote execution fit |
| OpenHands Agent Canvas | Interactive conversations plus automations in one frontend; likely combines much of HERDR and Symphony | Explicit multiple self-hosted backends; phone/tablet documentation | Does not establish a full native Linear replacement; backend switching is not proof of one aggregated cross-host inbox | High for documented backend and automation architecture; trial needed |
| GitHub + Issues/Projects + coding agents | Issues, agent tasks, pull requests and feedback in one hosted product | Browser/mobile; self-hosted agent runners documented | GitHub-hosted control plane, migration away from Linear, no existing desktop-session discovery established | High for documented features; public-preview qualifications apply |
| Devin + Linear | One practical interaction surface through Linear for autonomous tasks, status and replies | Hosted service; not a demonstrated personal LAN deployment | Two services remain, and this changes the execution model rather than aggregating existing Codex/Claude sessions | High for Linear interaction; unsuitable as proven LAN-only replacement |
| Vibe Kanban | Attractive historical combination of coding workspaces and issue boards | Local workspaces and self-host documentation exist | Company shut down; hosted issue/project/comment services were scheduled for removal | High confidence in maintenance caveat; low confidence in turnkey replacement today |

## 1. Paperclip — strongest task-and-worker consolidation

Paperclip provides native issues with agent assignment, comment threads, attachments and run ownership. Mentions can wake an agent; comments can request interruption or reopen a task. This directly fits the desired asynchronous conversation with an identified worker. The issue API also describes optional automatic final-output summaries when an agent did not leave its own comment. This is a real task system, rather than a collection of links into other applications. [Issues API](https://docs.paperclip.ing/reference/api/issues/)

Its experimental Chat-Style Tasks interface renders human and agent messages separately, with agent name/icon, streaming activity, collapsed turn summaries and file/image attachments through paste or drop. **That interface is explicitly experimental and off by default**, so it should not be presented as the standard stable experience. [Chat-Style Tasks](https://docs.paperclip.ing/experimental/task-chat/)

Codex and Claude Code adapters support persistent sessions and structured output. However, the local adapters run on the Paperclip host. Remote HTTP invocation is an integration mechanism, not evidence that Paperclip automatically finds or resumes the user's existing desktop sessions. Some runtime choices are not yet selectable in the normal UI. [Adapter reference](https://docs.paperclip.ing/reference/adapters/overview/), [choosing adapters](https://docs.paperclip.ing/guides/org/agent-adapters/)

Self-hosting is documented, including Docker and private access. [Deployment documentation](https://docs.paperclip.ing/)

**Fit:** First candidate to evaluate if replacing Linear is acceptable and most new work can initially execute on Hades. Use one plainly named worker; the product's company/org-chart model need not be taken as a requirement to create an elaborate hierarchy. Validate mobile usability, automatic summaries, and the cost/credential model in a bounded trial. External adapter extensibility itself is alpha. [Adapter Manager](https://docs.paperclip.ing/guides/org/adapters/)

## 2. OpenHands Agent Canvas — strongest explicit multi-backend architecture

The current OpenHands repository describes Agent Canvas as a self-hosted frontend for conversations and automation, supporting OpenHands, Claude Code, Codex and other ACP agents. Its README marks the project beta. Agent Server and Automation Server are distinct services within that system, so “one app” does not mean one process to maintain. [Current project README](https://github.com/OpenHands/OpenHands)

Canvas can register several backends by URL/key. Those can be local processes, containers, remote VMs or hosted services. **The displayed state, configuration and automations follow the selected backend**: the documentation proves a backend switcher, not a unified attention list across all machines. This nevertheless maps unusually well to Hades plus additional computers. [Backends](https://docs.openhands.dev/openhands/usage/agent-canvas/backends)

ACP integration launches the chosen coding CLI as a subprocess owned by the Agent Server. This is not import of desktop-app conversations. The guide documents reuse of local CLI authentication and notes a remaining concurrent-session isolation limitation in shared containers; use a pinned release and validate the precise agent/backend combination. [ACP integration](https://github.com/OpenHands/OpenHands/blob/main/docs/ACP_AGENTS.md)

Automations support schedules and external events, with prebuilt GitHub review/repository-monitor examples and a management view. This covers unattended execution in principle but does not prove parity with the user's Symphony lifecycle. [Automations](https://docs.openhands.dev/openhands/usage/agent-canvas/prebuilt-automations)

Phone/tablet access is documented. [Mobile access](https://docs.openhands.dev/openhands/usage/agent-canvas/mobile-access)

**Fit:** Strong trial choice if the main pain is switching between interactive sessions and unattended work on different machines. Expect to retain Linear initially; no reviewed source established a native issue tracker with full replacement semantics. Worker identity in external comments depends on the integration credentials and must be checked explicitly.

## 3. GitHub — credible single product if a hosted control plane is acceptable

GitHub supports asynchronous coding tasks through its Agents tab, issue assignment, PR mentions and GitHub Mobile. Claude and Codex are supported third-party agents in public preview for paid Copilot plans. Agents make pull requests and can iterate through review comments; provider GitHub Apps give the work distinct agent identities. Usage consumes AI credits and Actions minutes. [Third-party agents](https://docs.github.com/en/copilot/concepts/agents/about-third-party-coding-agents)

Copilot cloud-agent execution can use self-hosted Ubuntu x64 or Windows 64-bit runners. GitHub recommends ephemeral runners; this does **not** convert the GitHub UI into a LAN-hosted service or make it a browser for arbitrary sessions already running on a workstation. [Agent environment](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/customize-the-agent-environment)

GitHub Agentic Workflows provide scheduled/event-triggered repository automation, with explicit write outputs and model-engine configuration. They are also public preview, and are an additional configured workflow rather than automatic Symphony compatibility. [Agentic Workflows](https://docs.github.com/en/copilot/concepts/agents/about-github-agentic-workflows)

**Fit:** If the user is willing to move issue tracking to GitHub and accept the hosted UI, this offers a coherent issue-to-agent-to-PR conversation without maintaining a new personal control panel. Check the chosen third-party agent's runner support before assuming every runner option applies identically. Existing desktop sessions and general non-repository projects remain outside the established fit.

## 4. Devin with Linear — one conversation surface, not one service

Devin can be assigned Linear tickets, invoked through mentions or labels, and launched by status/label transitions. Its Linear agent session shows progress, plans, follow-up messages, a stop action and PR/session links. This directly addresses the request to converse with an identifiable unattended worker through Linear, rather than seeing comments authored as oneself. [Devin's Linear integration](https://docs.devin.ai/integrations/linear)

**Fit:** Useful as a benchmark for how polished the desired experience can be with an existing integration. It could replace much of the Symphony role while leaving Linear as the main interaction surface. It does not eliminate Linear, establish LAN-only hosting, or aggregate existing HERDR/Codex/Claude sessions. Treat it as an alternative workflow and commercial service, not a drop-in bridge between the present three tools. No price or self-hosting entitlement was assumed.

## 5. Vibe Kanban — do not choose based on older feature lists

Vibe Kanban's documented feature set includes agent workspaces and issue tracking, and its remote-access announcement described controlling agents on another computer from a phone. [Remote-access announcement](https://vibekanban.com/blog/remote-access), [issues documentation](https://vibekanban.com/docs/cloud/issues)

However, the official April 10, 2026 announcement says bloop shut down, that the project would become community-maintained, and that remote services including issues, comments, projects and organizations would remain only another 30 days. Local workspaces were to keep functioning. **Older marketing and docs are not proof those hosted services remain available today.** [Shutdown announcement](https://vibekanban.com/blog/shutdown)

Self-host instructions still describe the cloud components, including database, sync service and optional relay. That is evidence that source deployment is documented, not a verified maintenance or hosted-availability guarantee. [Docker Compose deployment](https://vibekanban.com/docs/self-hosting/deploy-docker)

**Fit:** A secondary option only if the user explicitly wants to operate a community-maintained stack and a fresh release/source audit establishes its current state. It should not be the first ease-of-use recommendation.

## What this research does not establish

No candidate has been shown to import all independently started Codex or Claude desktop-app sessions. No trial has verified this user's exact two-click navigation, mobile image pasting, offline stale-state retention, or seven-day/snooze behavior. Summary availability is not the same as summary accuracy. A known run status is not proof of meaningful progress or completion.

No recommendation here depends on the earlier conversation's claims of successful local HERDR/Symphony inspection; this report evaluates current external primary sources. Product versions, release maturity and operational behavior must be checked before migration.

## Recommended bounded evaluation

Start with **Paperclip if the goal is genuinely replacing all three applications**, or **Agent Canvas if preserving Linear and consolidating execution is acceptable**. Do not install both and migrate everything at once.

For the chosen candidate, a proposed trial is one disposable repository, one named agent, and two tasks on Hades: one interactive task with an image, and one unattended task that pauses for a human answer and then resumes. Open the same work from another computer and a phone. Verify that the worker's messages have a distinct author, that progress and history are findable, and that completion is explicit. Only after that succeeds, attach a second execution host and verify host selection and offline behavior.

Pass criteria: no SSH or remote desktop needed during ordinary use; the same work is reachable from another client; feedback reaches the intended worker; output and next steps are readable; histories persist; the agent does not make unrequested changes to other repositories. Record whether the product actually replaced a tool or merely linked to it.

This is a recommendation for a later authorized trial, not a started installation or migration. The next decision is whether Linear must remain authoritative: that determines whether three-to-one is the right target or whether one daily interface over two systems is the better outcome.
