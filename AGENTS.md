# Agent guide

This repository is a version-controlled collection of agent skills in the open
`SKILL.md` directory format. Each skill is self-contained under
`skills/<name>/` — entrypoint `SKILL.md`, plus optional `references/`,
`scripts/`, and `agents/`. `install.py` (with `install.sh` / `install.ps1`
wrappers) installs them locally, `skills_tui.py` is the interactive dashboard,
`skills_cli.py` provides the PATH-callable `skills` command, and
`scripts/sync-agent-skills.sh` serves cloud sessions.

## Working in this repo

- Environment: `uv sync --locked` (Python 3.12 via uv; 3.9+ fallback).
- `textual` is the one runtime dependency, and only the dashboard needs it.
  Every scripted path must keep working without it — say so plainly instead of
  raising an `ImportError`.
- Validate skills: `uv run python scripts/validate_repo.py`. Errors fail the
  run; warnings are the skill conventions (entrypoint length, "Use when"
  trigger phrasing) — fix those too.
- Run tests: `uv run python -m unittest discover -s tests`.
- Run both before committing. See `RELEASING.md` for versioning and releases.

## Gotchas the file tree does not show

- Every install path goes through `install.install_one`, so the rules live in
  one place; the TUI never re-implements install logic.
- The receipt each root carries (`.dm1681-skills.json`) is read back by
  `install.root_status`, which reconciles it against the directory and against
  the collection. It was write-only until then, which is how a removed skill
  stayed in a receipt across two releases. `skills status` / `install.py
  --status` renders that reconciliation, needs no `textual`, and exits `3` when
  something needs updating — not `1` or `2`, which already mean the run failed.
- A vendored skill (`install.VENDORED_SKILLS`) records the SHA256 of its
  upstream bytes with line endings normalised. Editing the copy here instead of
  upstream is drift, and the hash is what makes it visible offline. Re-sync
  upstream first, then update both the copy and its recorded hash. That hash
  covers the frontmatter, so a vendored skill carries no `version:` key and is
  exempt from the convention warnings — its entrypoint is not ours to shorten.
- Every install records the root it touched in the machine-wide roots index
  (`~/.dm1681-skills-roots.json`), which is what `--status --all` enumerates.
  It is a cache, never a source of truth: the receipts stay authoritative, it
  holds no skill names, and deleting it costs nothing but the next install
  rebuilds the entry. **Any test that runs a real install must redirect the
  home** — `--home` for `install.py`, `$HOME` for `skills_cli`, which has no
  flag — or it writes the test's temp path into the developer's real index,
  where it lingers as a vanished root long after the directory is gone.
- Both external *collections* — `matt-skills` and `pstack` — go through one
  `install.install_upstream`, parameterized by an `UpstreamCollection`. Do not
  add a third by copying it: the fetch is verified three ways (the commit, then
  `git status`, then hashing the bytes on disk because a `.gitattributes` in
  the fetched revision defeats the first two), and a second hand-written copy
  of that is exactly the drift nobody notices. pstack differs only in data —
  it lives in a monorepo, so it carries a `subdir` and a `verify_prefix`, and
  since upstream publishes no tags its pin is a bare commit checked against the
  version its plugin manifest declares.
- A root records which external collection placed which skills, in
  `.skills-external.json` beside the receipt. It exists because a flat skill
  root cannot say where a directory came from, and both collections hide most
  of what they ship (20 of 35, 39 of 44) — so the dashboard's per-row review
  would otherwise offer to unhide skills that row never installed. It also
  makes a name owned rather than merely present, which is what turns a silent
  overwrite of a shared name (`tdd`, `teach` — both collections ship both, and
  disagree) into a stop. Ownership moves to whoever wrote the directory last,
  or the winner's own next update looks like a conflict with itself. The record
  is newer than the installs it describes, so where none exists attribution
  falls back to the collection's marker directory: a check that trusted the
  record alone would fail open on every root an earlier release wrote, which is
  the upgrade path, not an edge case. `--uninstall` clears the record too —
  the conflict message names it as the remedy, so a record nothing could clear
  would make that advice false.
- **"Who owns skill N in root R" has exactly one answer, `install.ownership`.**
  Three records can claim a name — the receipt, `.skills-external.json`, and
  the directory itself — plus the visibility choice keyed beside them. Six
  callers used to ask that question inline and each was written against
  whichever records existed at the time, so every one added before the external
  manifest silently began answering about two-thirds of the truth: an uninstall
  reported success while leaving an ownership claim behind, the machine-wide
  report went blind to exactly the collections that collide, and a visibility
  choice made about one collection's `tdd` was re-applied to another's. Ask
  through `ownership()` / `claimed_names()`, and remove through
  `forget_records()`, which clears all three or none. Do not add a seventh
  inline answer.
- The TUI's colour contract (documented at the top of `skills_tui.py`) is
  load-bearing: one hue means one thing, and red is reserved for failure, so a
  healthy run contains none.
- The dashboard separates `YOUR SKILLS` (this checkout's own, diffable,
  installed as copy or link) from `EXTERNAL TOOLS` (placed by their own CLI;
  they honour `--scope` but not `--mode`). Register a new external tool in
  `install.EXTERNAL_TOOLS` and wire it in `SkillsApp.external_installers`; a
  test pins the two together.
- `skills setup-path` cannot run on a machine that has no `skills` command
  yet; bootstrap with `./install.sh --setup-path`, which delegates to the
  same code.

## Cloud sessions and new repos

Cloud/web sessions start from a fresh container without your local skills.
Options, lightest first: enable skills on claude.ai, a cloud environment setup
script, or the per-repo `SessionStart` hook (scaffold one with
`scripts/init-repo.sh <target-repo>`). See
[`docs/cloud-skills-sync.md`](docs/cloud-skills-sync.md).

## Global (user-level) instructions

`global/AGENTS.md` holds instructions that apply to every project, not just
this repo. Installing them is opt-in and writes two pointer files that chain
back here, so this checkout stays the single source of truth:

    ~/.claude/CLAUDE.md  ->  ~/.agents/AGENTS.md  ->  <repo>/global/AGENTS.md

Install with `./install.sh --global-instructions`; both pointer files are
backed up before being replaced. Use `--global-instructions copy` for agents
that do not resolve `@path` imports and for machines without this checkout.
The `SessionStart` sync script honours `AGENT_GLOBAL_INSTRUCTIONS=link|copy`,
forcing `copy` when it installs from a temporary clone.

## Conventions

- `AGENTS.md` is the single source of agent guidance; `CLAUDE.md` imports it
  (`@AGENTS.md`) so Claude Code and other agents share the same content. Edit
  `AGENTS.md`, never duplicate into `CLAUDE.md`.
- Update `docs/agent-support.md` and the installer mapping together when agent
  skill-directory conventions change.

## Review agents

An agent performing a review — pull request, code, or document — announces
itself before it starts. Post a "review started" comment on the review target
before reading the diff or forming any findings (or say it in the session
output when the target has no comment surface), stating who is reviewing, the
exact revision under review (full head SHA for a PR), and that findings will
follow in a later comment. One start comment per review round; when
re-reviewing after new commits, post a fresh start comment naming the new head
SHA instead of editing the old one, so the thread records every round.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
