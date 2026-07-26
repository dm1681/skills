# Cloud skills sync (Claude Code on the web)

Cloud sessions run in a fresh, ephemeral container. The repository is cloned in,
but your local `~/.claude/skills` is not — so personal skills you installed with
`./install.sh` on your own machine are absent in web sessions. Only the bundled
Claude skills and skills committed inside the cloned repo are present.

The `SessionStart` hook at [`.claude/hooks/session-start.sh`](../.claude/hooks/session-start.sh)
closes that gap: on cloud session start it installs the skills from this
collection into the session's `~/.claude/skills`, so they are discovered like
any other skill. It is registered for this repo in
[`.claude/settings.json`](../.claude/settings.json).

## How it works

The hook runs only when `CLAUDE_CODE_REMOTE=true` (web sessions), so it never
touches your local setup. It installs in one of two modes:

1. **Local** — if the current repo already contains the skills (a `skills/`
   directory with `<skill>/SKILL.md` entries), it copies them straight from the
   working tree. No network, no auth. This is what runs inside this repo and for
   any repo that vendors the skills.
2. **Clone** — otherwise it clones the source repo and installs from it. The
   source repo must be reachable from the session (see the private-repo note
   below).

Installing = copying each `<skill>/SKILL.md` directory into `~/.claude/skills`,
replacing any existing copy of the same skill name. It is idempotent and safe to
re-run.

## Reuse in another repo

Drop the hook into any repo whose cloud sessions should load these skills:

1. Copy `.claude/hooks/session-start.sh` to `<repo>/.claude/hooks/session-start.sh`
   and `chmod +x` it.
2. Add the `SessionStart` hook entry from `.claude/settings.json` to that repo's
   `.claude/settings.json` (merge if it already exists).
3. Commit both to the repo's **default branch** — hooks only take effect once
   they are on the branch the cloud session checks out.

Point it at a different source or a different in-repo location with env vars in
the hook entry's environment (all optional):

| Variable | Default | Meaning |
| --- | --- | --- |
| `CLAUDE_SKILLS_REPO` | `dm1681/skills` | `owner/name` of the skills source repo (clone mode) |
| `CLAUDE_SKILLS_REF` | `main` | branch or tag to install from (clone mode) |
| `CLAUDE_SKILLS_SUBDIR` | `skills` | directory holding `<skill>/SKILL.md` entries |

## Private source repos

`dm1681/skills` is private. In **local mode** this is a non-issue — the skills
are read from the current working tree. In **clone mode**, the clone only
succeeds if the source repo is reachable from that session's credentials. For a
private source, the reliable options are:

- **Vendor the skills** into the target repo (copy them in, or add a git
  submodule) so the hook uses local mode — no auth required. Set
  `CLAUDE_SKILLS_SUBDIR` if you vendor them somewhere other than `skills/`.
- **Add the source repo to the session's scope** so the clone is authorized.

If the clone fails, the hook logs a warning and lets the session start normally
rather than blocking it.

## Notes

- Web container state is cached after the hook completes, so the skills are part
  of the session's environment from startup.
- Skills install by name; a skill here that shares a name with a bundled Claude
  skill will replace the bundled copy for that session.
- The hook writes only to `~/.claude/skills` and never modifies the target
  repo's files.
