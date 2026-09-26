# AI development home dashboard — design decisions

Updated: 2026-09-24. Status: discovery in progress; implementation not started.
Source: the user's grilling session in this conversation.
This is a working design note for a new system, not a commitment to implement it
inside the skills repository. No Linear issue has been mapped to this design.

## Purpose and acceptance

### Latest direction

The user is evaluating whether HERDR, Symphony, and Linear together satisfy the
needs below without a custom dashboard. Treat the dashboard requirements as
desired system capabilities, not authorization or a settled decision to build a
new application. Keep HERDR's existing UI unchanged. The user plans to check the
HERDR installation and integrations on Hades later.

The user subsequently requested research into alternatives that could consolidate
the three tools into one. This authorizes research, not installation, migration,
or a change to the existing tracking workflow. Candidate comparisons belong in
`docs/research/ai-development-consolidation-2026-09-24.md`; no replacement has
been selected.

Asynchronous interaction with Symphony workers through Linear/review feedback is
acceptable; live conversation with a running worker is not required. Responses
should have **one shared Symphony identity as the visible author**, with the
issue/run identifiable, so the conversation does not appear to be the user
talking to themselves. The user accepted the shared identity. Actual bot/agent
identity support, credentials, comment delivery, and feedback pickup behavior
remain unverified and unconfigured. A textual worker label alone is not the
agreed substitute for distinct authorship.

Provide one memorable starting point for ongoing AI development across three
computers and multiple projects. Ease of use comes first, supported by clear
status, concise context, visualization, and traceable work history.

**Confirmed first acceptance criterion:** from any of the three computers, the
user can quickly understand what needs attention and open a supported ongoing
session within one or two clicks. Execution need not move between computers.

## Agreed first version

| Area | Decision |
| --- | --- |
| Scope | Find and resume existing work; creating sessions comes later. |
| Home screen | Attention items first, then remaining projects and their sessions, locations, and statuses. |
| Attention items | Requests for input, blockers, failures, and results ready for review, with a concise required action. |
| Notifications | Attention indicators stay inside the dashboard. No external notifications are needed. |
| Reminder snooze | Allow inactivity reminders to be snoozed for another seven days while keeping the session active. Together with attention items, these form a lightweight in-dashboard notification feature. |
| Attention priority | Show inactivity reminders below blockers, failures, requests for input, and work ready for review. |
| Completed sessions | Move out of the home screen into a separate, searchable history view. Keep them accessible for later inspection. |
| Completion trigger | Move sessions into history only when explicitly completed or archived; inactivity alone never hides unfinished work. The source of explicit completion remains to be specified. |
| Inactivity reminders | Show an in-dashboard reminder after seven days without activity, with a suggestion to review, resume, or archive. Never automatically archive based on inactivity. The exact source activity signal remains to be verified. |
| Cross-machine grouping | Group sessions for the same project together across computers, showing the host for each session. |
| Context | Session and project summaries explain where work left off and its next direction. Summaries update automatically and show their update time. |
| Offline hosts | Retain projects, sessions, and last known summaries. Clearly mark offline or unknown status and last update time. |
| Access | Always-available LAN dashboard, accessible away from home through the user's VPN into the LAN. Hosted on Hades, the user's Ubuntu machine that stays on essentially all the time. |
| Audience | Personal use only. No multi-user accounts or collaboration features are planned; the dashboard remains on the LAN, with remote access through the VPN. |
| Mobile | Include a phone-friendly dashboard in the first version. Session interaction on mobile depends on the supported capabilities of the linked tools and remains to be verified. |
| Interaction | Direct links to existing interfaces are sufficient. No remote desktop. No rebuilding or reverse engineering Codex or Claude session interfaces. |
| Usability | Preserve convenient image copy/paste and clickable links through the chosen interaction tools where supported; capabilities are not yet verified. |
| Discovery | Ideally include sessions started independently in existing apps, not only dashboard-managed sessions. Discovery support needs investigation. |
| Unsupported sessions | Discovered sessions that cannot be reopened still appear, clearly labeled view only. |
| Linear association | Show sessions even without a Linear issue; link related issues when available. |
| History | Short timeline of meaningful decisions and completed work linked to original sessions and Linear issues. |

## Tool responsibilities

These are intended roles, not verified claims about available integrations.

| Component | Intended responsibility |
| --- | --- |
| Home dashboard | Consolidate current activity, attention items, brief context, and navigation. |
| HERDR | Existing interface for interactive sessions across machines; first integration to investigate. The user reports their current server tracks new sessions launched in its terminals. Existing app-session pickup is unknown. |
| Symphony | Unattended development. Initially expose a few monitoring features: status, attention items, and concise progress summaries, with links to its existing interface. |
| Linear | Own project plans, issues, priorities, and durable work history. Project and issue edits remain in Linear for version one. |

HERDR, Symphony, and Linear all belong in the intended initial scope; HERDR is
first in integration order. The dashboard is not intended to duplicate Linear's
project management. A separate detailed project page was proposed but not agreed.

## Deferred decisions and features

- Create new sessions on connected machines from one place, without SSH or remote desktop.
- Broader Symphony dashboard coverage. Full feature parity is not a launch requirement; add features as needs emerge.
- Deterministic Linear hooks, event queues, retries, and delivery confirmation. The user explicitly deferred these unless existing update reliability proves inadequate.
- Starting or stopping Symphony workers from this dashboard; initially use existing interfaces.

Meaningful progress, decisions, blockers, and results should continue to be
recorded in Linear through the existing workflow. Do not treat the deferred
reliability mechanisms as implementation requirements.

## Open questions and factual investigation

- Verify the exact HERDR project/version, existing deployment, supported session discovery, and direct session links.
- Inspect the actual Symphony deployment/dashboard/API to identify a small supported monitoring surface.
- Determine supported discovery and reopening paths for independently started Codex and Claude app sessions, including cross-machine behavior and image handling.
- Determine how Hades receives status from each computer.
- Decide how project/session identities, summaries, and timeline entries are derived without duplicating Linear ownership.

## Continuation

Keep interviewing with **one concise question at a time**, accompanied by a
recommendation. The user explicitly replaced the grilling skill's multi-question
round format with this preference. Record accepted decisions here and distinguish
them from proposals and unverified capabilities.

The user approved read-only investigation of HERDR and Symphony and requested
frequent progress updates. Implementation remains unapproved.

Next design question: is opening HERDR and selecting the target pane an acceptable
initial navigation path when a direct pane URL is unavailable?
Next technical investigation: identify the installed HERDR deployment and inspect
its supported interfaces before proposing an integration architecture.

Only documentation has been created in this turn. No services, integrations,
Linear records, or existing source files were changed. This new system has no
confirmed repository or Linear project mapping yet; do not attach it to the
skills repository's Symphony pilot issue merely because this note lives here.

## Read-only feasibility findings — 2026-09-24

Live HERDR web endpoint: `http://192.168.0.52:8787/` on Hades.
Inspected GET responses and the served client asset
`/assets/index-Bb5J46jd.js`; no commands, selection writes, uploads, terminal
attachments, or configuration changes were performed.

| Requirement | Evidence and boundary |
| --- | --- |
| Live monitoring | GET `/api/snapshot` returned workspace/tab/pane identifiers, working directories, agent statuses, and layouts. GET `/api/agent-activity` returned status-transition timestamps. |
| Cross-machine web use | Served client supports multiple configured bridge URLs. This does not prove all three machines have working bridges; their deployment inventory is still needed. |
| Open a specific session | Client selection uses in-app state, persisted browser selection, and optionally POST `/api/selection` for shared selection. No incoming URL query/hash routing to a pane was found. A direct session URL is not established. Opening HERDR then selecting a pane is a candidate, not a tested two-click guarantee. |
| Existing outside sessions | The inspected API models HERDR terminal panes. Official agent documentation describes detection inside those panes. No supported import/discovery path for independently started desktop-app sessions was established; do not claim universal discovery. |
| Images and mobile | Served client contains paste-file extraction, a paste handler, and upload requests. Upstream herdr-web documentation confirms image/file paste and mobile controls. End-to-end image delivery and phone usability were not tested. |
| Status semantics | Client recognizes idle, working, blocked, done, and unknown. Upstream describes screen-based status detection for Codex and Claude; unfamiliar prompts may be reported idle. Treat status as a source observation, not proof of completion or an exhaustive attention signal. |
| Inactivity | `last_status_transition_at` is not last meaningful progress. Seven-day reminders need a suitable activity signal; do not substitute status age without clarifying the meaning. |
| Summaries and history | Snapshot and activity data do not establish durable narrative summaries or complete history. Linear/workpad context and dashboard persistence still need design. |
| Symphony | Local GET `/api/v1/state` on ports 8789, 8790, and 8791 returned running, retrying, blocked, counts, totals, rate limits, and generated-at fields. Each had zero running/retrying/blocked entries during the observation; row details were not validated. Ports 8790 and 8791 were loopback-only, so reachability from Hades is not established. |

SSH to the configured Hades alias failed DNS resolution. Connecting by LAN IP
reached SSH but strict host verification refused an unknown key. No host key was
accepted or bypassed; the installed server version and configuration remain
unverified. The web surface was sufficient for the bounded checks above.

Primary references consulted (upstream documentation may differ from the installed
revision):

- <https://github.com/kcosr/herdr-web> — bridge API, uploads, mobile interface, and terminal ownership.
- <https://herdr.dev/docs/agents/> — pane detection, status authority, and agent attachment.

Next technical action: verify the user-visible navigation path in an isolated
browser without attaching to or changing an active terminal; if inspection would
take terminal ownership or change selection, stop at the read-only boundary.
