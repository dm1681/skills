# Curated Matt-derived skills

This repository owns and versions a supported subset of
[Matt Pocock's skills](https://github.com/mattpocock/skills), based on v1.2.3,
commit `6acc160e4e0cd062dbbbd7a1b26ae92855edf07e`. Each fork retains the MIT license.
`curated-skills.json` records the upstream paths and normalized SHA256 of every
source/supporting file. This is a deliberate fork, not an immutable vendored copy.

## Install and migrate

Choose individual skills in the dashboard's YOUR SKILLS list, use
`skills install tdd codebase-design`, or install the supported subset:

```sh
./install.sh --curated-skills --scope project --project-dir /path/to/project
```

`--matt-skills` is a compatibility alias for this subset. It no longer downloads
the broad collection. `--matt-ref` is retired and fails before writes. There is no
`setup-matt-pocock-skills` follow-up. Existing project tracker mapping and linked
issues/specs supply review context. Ordinary scripted installation needs Python,
not Textual or a network fetch.

Existing upstream copies require `--force` to back up and replace the selected
names. Ownership transfers to the local receipt and old visibility decisions for
replaced names are cleared. Unrelated skills such as triage remain installed and
retain their records; migration never implicitly uninstalls them. The legacy
Matt dashboard row remains for old-install visibility and explicit migration;
the owned forks themselves are listed under YOUR SKILLS.

## Supported subset

| Skill | Interactive session | Symphony worker |
| --- | --- | --- |
| codebase-design | Shared design vocabulary | Same vocabulary |
| domain-modeling | Interview, glossary and ADR creation | Consume prepared glossary/ADRs; skill excluded |
| diagnosing-bugs | Reproduction and diagnosis; ask for missing evidence | Record blockers in workpad; record architectural follow-up |
| tdd | Confirm test seams with user | Choose and document seams autonomously |
| research | Delegate within session when available; otherwise investigate | Same, retaining Symphony ownership |
| writing-for-agents | Instruction authoring | Same |
| grilling | Preserve interview/wait behavior | Excluded |
| code-review | Parallel Standards and Spec reviews; manual Human Review | Excluded |
| handoff | Explicit interactive handoff | Workpad replaces this skill |
| claude-handoff | Explicit invocation, existing workflow unchanged | Explicit invocation remains available; no ownership transfer |
| implement | Interactive pacing choice; display name Implement (interactive) | Excluded |

The supported set omits triage, to-tickets, loop-me, ask-matt and the broad setup
router. Retained skills' local references and support files are included. The
mandatory global visualization-first rule is removed; viz-driven-dev remains
available interactively and is explicitly disabled for workers.

## Forking implement

The pre-existing implement fork keeps its internal name and interactive pacing
behavior. Descriptions and UI metadata identify it as interactive. The name stays
stable so an explicitly requested `/implement` still reaches it.

`SHADOWED_SKILLS` in `install.py` protects all retained same-name forks at the
flattened skill-name stage of the shared upstream installer. Category skipping
is not a substitute: `skills/engineering/implement` is not a category called
implement. Original upstream copies cannot overwrite these forks on a collection
refresh. Other collections' ownership conflicts still use `ownership()` and
`claimed_names()`; removals/migrations clear records through `forget_records()`.

## Deliberate upstream maintenance

Compare the recorded revision and file hashes with a separately verified upstream
checkout. Review supporting-file changes as well as entrypoints. Apply accepted
improvements to source files here, bump the affected skill versions, and update
the provenance record and shadow entries together. Do not edit installed home
copies or move the fork base merely because an upstream collection pin changed.
A default upstream fetch detects shadow drift and stops for reconciliation.
