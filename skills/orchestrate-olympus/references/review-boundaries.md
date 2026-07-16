# Olympus review boundaries

## Contents

1. Classify ownership before severity
2. Finding schema
3. Blocking rules
4. Scope versions and corrections
5. Review trigger matrix
6. Shared disposition and clean signal

## 1. Classify ownership before severity

Before reviewing behavior, classify each changed surface:

- `olympus-authored`: Worker-authored product code, tests, configuration, scripts, docs, or integration logic.
- `generated-artifact`: output produced by a supported tool and tracked or presented by Olympus.
- `upstream`: behavior owned by an external tool, dependency, renderer, report generator, platform, or service.

Review the Worker's full Olympus-authored diff and relevant neighboring code. For generated artifacts, review Olympus's choice to package, track, update, document, link, or rely on the artifact. Do not silently convert upstream behavior into Olympus implementation scope.

## 2. Finding schema

Every finding records:

- stable identifier and exact reviewed head;
- severity;
- provenance: `olympus-authored`, `generated-artifact`, or `upstream`;
- scope category;
- `blocking=true|false`;
- required actor: `worker`, `orchestrator`, `owner`, or `upstream`;
- stable file/line when available;
- failing scenario, evidence, and required outcome;
- disposition and any promotion authority.

Use scope categories such as `correctness`, `security`, `privacy`, `migration`, `integration`, `packaging`, `integrity`, `documentation-claim`, `access-path`, `presentation`, or `upstream-quality`.

## 3. Blocking rules

An Olympus-authored defect may block according to normal severity and acceptance rules.

A generated artifact may block only when the defect is in Olympus's integration responsibility, including:

- corruption, missing or stale required output;
- unsafe tracked content, credentials, private paths, or privacy leakage;
- non-reproducible update/bootstrap/hook behavior;
- inaccurate Olympus documentation or claims;
- a broken access path Olympus advertises;
- incompatibility caused by Olympus-authored packaging or configuration.

Styling, interaction, report semantics, accessibility, or other behavior emitted by an unmodified upstream generator is `Advisory / Non-blocking / No change` unless the owner or Orchestrator explicitly promotes it into Olympus scope with evidence and a new scope version.

The Worker must not patch, post-process, fork, vendor, or reimplement upstream behavior in response to an advisory. Preserve the observation in the ledger and identify the upstream actor when useful. Do not create a backlog issue without owner authorization.

## 4. Scope versions and corrections

Every lane has `scope_version`, starting at 1. The canonical Planner brief or maintenance mini-brief is the current contract. An owner or Orchestrator correction must:

1. increment `scope_version`;
2. say `SUPERSEDES scope_version=N`;
3. list changed ownership, blocking, required-actor, or acceptance decisions;
4. notify Worker and Reviewer with the same canonical correction;
5. update the checkpoint.

Worker and Reviewer must acknowledge the latest version before further mutation or review. Older prompts remain historical evidence, not active instructions.

When a prior review ledger becomes misleading, the Reviewer posts one signed consolidated correction that identifies the authoritative blocking and advisory sets. Reply in affected Reviewer-owned threads and resolve those reclassified as non-blocking. The Worker does not duplicate resolved advisory replies.

## 5. Review trigger matrix

| Event | Reviewer action |
|---|---|
| New PR or new head | Full Standards and Spec review at the exact head |
| Worker disposition on unchanged head | Targeted verification of affected findings |
| Owner scope correction on unchanged head | Reconcile ownership/ledger only; do not launch another full review |
| PR-body or artifact-index correction with unchanged head | Verify claims, links, privacy, and head freshness only |
| Completed final GitHub `@codex review` on the requested unchanged head | Adjudicate its new allegations and threads; do not relaunch duplicate full axes |
| No new head, activity, scope, or disposition | No review, subagent, or GitHub comment |

Do not launch duplicate review axes for an already processed unchanged head. Track processed head, scope version, and activity IDs.

## 6. Shared disposition and clean signal

Blocking findings end as `accepted-fixed`, `accepted-no-change`, or `disputed`. Advisory findings end as `advisory` and never withhold CLEAN.

After one evidence-backed unresolved exchange, mark `disputed`, notify the Orchestrator, and stop. When no blocking findings remain, post exactly one signed CLEAN comment approving all work at the exact SHA. This CLEAN signal is the authorization event for the Orchestrator's final `@codex review` comment after presentation. A new commit invalidates it; a scope-only correction does not invalidate code evidence but may require a corrected ledger before readiness.

The final GitHub Codex review is a separate post-presentation gate. Treat its output as allegations and apply the same ownership rules. If no maintained blocker remains, post one signed `CODEX_REVIEW_ACCEPTED` signal naming the exact head, request comment, and review result. That signal does not replace Olympus Reviewer CLEAN; readiness requires both on the same head.
