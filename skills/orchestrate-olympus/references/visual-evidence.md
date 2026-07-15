# Olympus visual evidence and presentation

## Contents

1. Ownership model
2. When to visualize
3. Color and accessibility
4. Artifact contract
5. Presentation gate
6. Reviewer boundary

## 1. Ownership model

Do not create an always-on visualization agent. Assign responsibility by role:

- Planner identifies relationships or acceptance criteria that benefit from visual proof.
- Worker produces exact-head evidence for materially visual or structurally complex changes.
- Reviewer verifies Olympus-authored visuals and factual claims under the provenance rules.
- Orchestrator owns progress visualization, artifact index, PR presentation, and final delivery report.

Use an optional Visual QA subagent only for a substantial Olympus-authored visual artifact. Do not use one merely to critique an unmodified upstream visualization.

Maintain one canonical progress visual when the lane has at least three meaningful phases, branches, dependencies, or evidence groups. Refresh it at meaningful transitions such as planning complete, first PR head, review/repair, Reviewer CLEAN, and merge. Link or embed the same canonical artifact in the relevant issue or PR handoff and final report; do not post a new visualization comment on unchanged heartbeats.

## 2. When to visualize

Use the smallest form that materially improves understanding:

- flow, state, or timeline for dependent progress and transitions;
- architecture, data-model, or interface diagram for relationships;
- table for exact mappings or feature evidence;
- screenshot or short recording for user-visible, responsive, or interaction behavior;
- chart only for quantitative evidence.

Skip decorative diagrams and explicitly mark non-visual work when no visual would help.

## 3. Color and accessibility

Use a stable semantic status palette unless Olympus's product design system defines another:

- green: verified or complete;
- blue: informational, active, or planned;
- amber: owner action, attention, or in progress;
- red: blocked or failing;
- gray: pending, paused, or inactive.

Keep the same concept mapped to the same color across related artifacts. Include a visible legend. Pair every color with labels and at least one non-color cue such as icons, shapes, patterns, line styles, or explicit state text. Use color-vision-safe choices and sufficient light/dark/print contrast.

## 4. Artifact contract

Every material artifact records:

- purpose and acceptance criterion;
- exact head SHA;
- source or generation command;
- verification status;
- direct durable link or embedded preview;
- caption or alt text;
- relevant limitations.

Store durable project evidence in the repository when appropriate; otherwise use the Codex visualization workspace. Never make an ephemeral local path the only handoff. Maintain one canonical artifact index rather than scattering duplicate lists.

Surface every material artifact in the canonical issue brief, PR body or disposition, Reviewer evidence when applicable, and the final delivery report. Prefer a direct link plus a small preview or concise caption so the evidence is visible without hunting through task history.

Inspect artifacts for secrets, credentials, idempotency keys, sensitive Session Update content, private filesystem paths, credential-bearing remotes, personal data, and unintended environment details.

## 5. Presentation gate

After exact-head Reviewer CLEAN, enter `PRESENTING` before reporting ready:

1. Verify the PR head and clean signal still match.
2. Update the PR body or canonical disposition with a compact color-coordinated lane view.
3. Refresh exact-head SHAs, counts, screenshots, artifact links, test results, and owner action.
4. Test that links open through the documented authenticated path; do not advertise raw private HTML as executable.
5. State network, offline, compatibility, privacy, migration, and generated-artifact limitations truthfully.
6. Ensure color is supplementary and the text alone communicates status.
7. Re-audit head, checks, threads, mergeability, and escalation after presentation changes.
8. Hand the stable presented head to the final GitHub `@codex review` gate; presentation alone never enters a ready or merge phase.

PR-body-only changes do not require code re-review when the head is unchanged, but stale, broken, unsafe, or misleading presentation blocks the presentation gate.

## 6. Reviewer boundary

For Olympus-authored visuals, review accuracy, rendering, accessibility, mobile behavior, captions, and acceptance coverage.

For unmodified upstream/generated visuals, review only Olympus-owned packaging and claims: artifact integrity, freshness, privacy/security, documented access path, and whether it opens as claimed. Upstream report semantics, keyboard behavior, styling, and contrast are advisory unless explicitly promoted into scope.
