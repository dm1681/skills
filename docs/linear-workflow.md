# Linear workflow setup

## Symphony projects

For a new Symphony project use [project onboarding](symphony.md): create from the
Agent-Ready Software Project template, supervise the included harness setup
issue, configure/check Symphony without dispatch, review evidence and mark the
setup issue Done, then start explicitly. Record the exact setup issue in project
configuration. Use the upstream lifecycle and persistent workpad; the legacy
label/claim/Current-overview/handoff protocol below does not apply to workers.
Use native project membership, blocker relations, related links and attached PRs.

## Status updates are part of execution

Follow [required status synchronization](../global/AGENTS.md#required-status-synchronization)
at pickup, meaningful checkpoints and before ending substantive issue work.
Update the actual issue state field and fetch it again; a comment is not a state
transition. Record failures honestly if the update cannot be verified.

A supervised setup issue starts in Backlog, moves to In Progress when authorized
implementation starts, and moves to Human Review when its deliverable satisfies
the review bar. Done requires human acceptance. "Keep incomplete" never means
leave active work in Backlog. Workers retain upstream routing: they do not start
Backlog work or reset Human Review/Merging merely because a session resumes.

These are instructions agents must load and follow, not a runtime guarantee.
Fresh-session loading and commit/sync verification remain necessary; do not claim
an uncommitted instruction edit is active on other devices or remote clones.

## Legacy interactive tracking (projects not using Symphony)

The shared workflow lives in [`global/AGENTS.md`](../global/AGENTS.md#linear-work-tracking-and-handoffs).
Load that source through the existing global-instruction installation; keep
only the repository mapping and exceptions in each project's `AGENTS.md`.
There is no additional skill or connector installation in this workflow.

## Onboard a repository

Verify the intended project and team through a live Linear read, then adapt
this example in the target repository's `AGENTS.md`. Replace all placeholders
with verified values; a similarly named project is not proof of a mapping.

```markdown
## Linear

- Repository: <canonical repository URL>
- Project: <verified Linear project URL> (ID: <verified project ID>)
- Team: <verified team name/key>
- Shared workflow: follow the Linear section of the installed global agent
  instructions. If it is absent, read <path to skills checkout>/global/AGENTS.md
  before starting tracked work.
- Pending handoffs: docs/handoffs/<issue-or-task>.md
- Workflow exceptions: none; use the shared state/label conventions.
- Technical policies and acceptance checks: see <repo-specific document>.
```

Confirm the project's workflow has the states and labels named in the shared
guidance, or document its equivalents here. Keep experiment rules and technical
acceptance policies in the target repo. A project mapping does not grant
permission to execute, send messages, publish or deploy.

## Deliver and verify the guidance

On a durable checkout, `./install.sh --global-instructions` writes the existing
link chain. On Windows use `./install.ps1 --global-instructions`; the dashboard
is also available through `./install.ps1 --interactive`. Copy installations use
`--global-instructions copy` and need reinstalling after source changes.

For POSIX/cloud sync, opt in with `AGENT_GLOBAL_INSTRUCTIONS=link` or `copy`;
temporary clones always use copy. See [cloud sync](cloud-skills-sync.md) for
source selection. Only a checkout containing this change can deliver it;
uncommitted work on one device is not available to another device's clone.

Check the [agent loading matrix](agent-support.md#global-instruction-loading)
before claiming delivery. Inspect the written file or resolve its pointer to
the canonical source, then verify in a fresh agent session that the Linear
section is loaded. Verify connector access independently with a read of the
mapped project. File installation, instruction loading and Linear access are
three separate checks; record the devices/environments actually checked.

If any check fails, retain a pending local handoff using the shared workflow.
Never copy connector credentials into this repository or its synced guidance.
