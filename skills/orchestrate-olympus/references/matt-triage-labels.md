# Matt Pocock triage-label gate

Use this gate after the parent Orchestrator and reusable Reviewer identity are
verified, and before dispatching any Planner or Worker. GitHub labels are
repository-wide, so one verified label set serves both issues and pull
requests.

## Resolve the configured vocabulary

Read `docs/agents/triage-labels.md` from the live Olympus default branch. Treat
its tracker-label column as authoritative, including intentional custom names.
The mapping must define each canonical Matt Pocock role exactly once:

- `needs-triage`
- `needs-info`
- `ready-for-agent`
- `ready-for-human`
- `wontfix`

Require five non-empty tracker names and reject a mapping that assigns one
tracker label to multiple roles. If the file is absent, stale relative to the
live default branch, or malformed, enter `ESCALATED`, make no label mutation,
and direct the owner to run `setup-matt-pocock-skills` in Olympus. Do not guess
from issue history or silently replace a configured custom vocabulary with the
defaults.

## Verify and repair the live repository labels

List the complete repository label set, not only labels currently attached to
an issue or PR:

```sh
gh label list --repo dm1681/Olympus --limit 1000 --json name
```

Compare the five configured tracker names with the returned names. Create only
missing mapped labels with `gh label create --repo dm1681/Olympus`, using the
role descriptions from the mapping. Use these stable Olympus colors when a
new label needs a color:

| Canonical role | Color |
| --- | --- |
| `needs-triage` | `FBCA04` |
| `needs-info` | `D4C5F9` |
| `ready-for-agent` | `0E8A16` |
| `ready-for-human` | `1D76DB` |
| `wontfix` | `FFFFFF` |

Never rename, delete, or overwrite an existing label, and never use
`gh label create --force`. Existing descriptions and colors are maintainer
metadata, not part of the Matt Pocock vocabulary contract. Re-list labels after
creation and require all five configured names to be present before the gate
passes.

If listing, creation, or final verification fails, enter `ESCALATED`, preserve
the current lane and worktrees, and dispatch no new Planner or Worker. Report
the configured mapping, labels found, labels created, exact failure, and one
recovery action. A successful no-change verification produces no GitHub
comment.
