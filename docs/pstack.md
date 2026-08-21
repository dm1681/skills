# pstack skills (optional)

[`pstack`](https://github.com/cursor/plugins/tree/main/pstack) is a Cursor
plugin by Lauren Tan, MIT-licensed, that ships rigorous agent workflows
(`poteto-mode`, `architect`, `interrogate`, `why`, `how`) alongside 21
`principle-*` skills stating one coding principle each. No skill bundled in
this collection depends on them, so they are a pure opt-in. When requested, the
complete plugin is installed so those workflows and the principles they cite
remain coherent.

## Install behavior

The wizard never prompts for third-party downloads. Installing them is always
explicit:

```sh
./install.sh --agent all --pstack
```

The installer shallow-fetches one revision of the upstream repository into a
disposable checkout, then copies every skill it discovers into the same resolved
roots used for the bundled skills. That preserves `~/.agents/skills` for shared
user installs and applies the installer's existing backup-before-replace policy.

The effective commands have this form:

```sh
git init --quiet --template=
git fetch --quiet --depth 1 https://github.com/cursor/plugins.git 51a96e0…
git -c core.hooksPath=.git/no-hooks -c core.autocrlf=false -c core.eol=lf \
  checkout --quiet --detach FETCH_HEAD
git status --porcelain   # must be empty before anything is copied
git ls-tree -r FETCH_HEAD -- pstack/   # every blob compared against
git hash-object --no-filters …         # the bytes actually on disk
```

This is the same fetch, the same verification, and the same copy that
`--matt-skills` runs — one implementation, parameterized, rather than two. The
reasoning behind each step is written out in
[`docs/matt-pocock-skills.md`](matt-pocock-skills.md): why `fetch` rather than
`clone --branch`, why the line-ending overrides matter on Windows, why the
user's git hooks are kept out by two separate doors, and why the working tree
is checked twice — once with `git status` and once by hashing the bytes as they
sit on disk, because a `.gitattributes` in the fetched revision can defeat the
first check but not the second.

Two things differ, and both come from pstack living inside a monorepo:

- The byte comparison is scoped to `pstack/` rather than the whole revision.
  At the pinned commit that is 156 blobs rather than the repository's 478, and
  the 322 it skips are other plugins — files no install can reach, whose
  `.gitattributes` could otherwise fail a pstack install.
- Skill discovery is rooted at `pstack/skills/`, so a sibling plugin's skills
  can never be picked up by it.

Git is the only requirement. `--dry-run` prints the exact commands and final
destinations without network access. Custom `--target` paths are supported
because destination resolution remains under this installer's control.

## Which revision gets installed

`cursor/plugins` publishes no tags. `mattpocock/skills` does, which is why that
pin is a tag plus the commit behind it — the tag is what a human reads and the
commit is what actually pins. Here the tag half is missing, so the pin is a
bare commit and there is nothing readable in it: `51a96e0` names no release
anybody can look up.

So the readable half comes from the plugin itself. `PSTACK_REF` in `install.py`
pins the commit and `PSTACK_VERSION` records the version that commit's
`.cursor-plugin/plugin.json` declares. A default install verifies both, and
stops if they have come apart — which is what a monorepo commit pointing at a
different pstack release than this repository documents looks like. Update the
two together.

That check runs *after* the byte verification, never before: a version read out
of a tree that something rewrote on the way to disk is not evidence of
anything.

Override the ref per run:

```sh
# Track upstream.
./install.sh --agent all --pstack --pstack-ref main

# An exact commit, named in full: the remote resolves the argument as a
# refspec, and an abbreviated SHA is not one.
./install.sh --agent all --pstack \
  --pstack-ref 51a96e0dd838404da19ba83dc70aa21eef71f868
```

A named ref is checked against no second pin — it *is* the revision the caller
chose, and its declared version is reported rather than enforced. An empty one
(`--pstack-ref "$REF"` with `REF` unset) is refused rather than quietly falling
back to the default.

Because the pin is a monorepo commit, it moves whenever anything in
`cursor/plugins` moves, not only when pstack does. Reviewing an update means
reading the plugin's diff, not the repository's:

```sh
git clone https://github.com/cursor/plugins.git /tmp/cursor-plugins
git -C /tmp/cursor-plugins diff 51a96e0..main -- pstack/
```

## What gets installed

44 skills, every directory under `pstack/skills/`, flattened to `<name>/` in
each selected root. Two things upstream ships are deliberately left out:

- **`pstack/automations/benny/`** — three more skills (`setup-benny`,
  `triage-issue-reports`, `reproduce-and-fix-issues`). The plugin manifest
  declares two pointers, `"skills": "./skills/"` and `"agents": "./agents/"`,
  and benny is under neither — so these are not part of what a pstack user
  normally gets. They also drive a Slack-and-tracker pipeline that does nothing
  until its services are configured.
- **`pstack/agents/`** — the manifest's second pointer, holding two Cursor
  subagent personas. This repository installs skills into skill roots and has
  no concept of an agent root to put these in, and inventing one would write
  into a directory nothing here can later report on or clean up. Two skills
  name an agent that will not be there: `no-comments` spawns *Comment Sicko*,
  and `poteto-mode` routes to `poteto-agent`. Both still describe what they
  want done.

Every selected root receives the same files, and a checkout that does not
contain `setup-pstack` fails the install, because that is the shape of the
collection changing under us and a partial install is worse than a stop.

## Two collections, one directory

A skill root is one flat directory, so a name is a name. pstack and
`mattpocock/skills` both ship **`tdd`** and **`teach`**, and they disagree:

- `tdd` — pstack's is a narrow bug-fix regression workflow that explicitly
  allows skipping the test when the path is expensive or unclear. Matt's is a
  broad TDD reference for features and bugs alike, with no such escape hatch.
- `teach` — pstack's is a single-file code explainer for an existing subsystem
  or diff. Matt's is a stateful multi-session tutoring workspace with its own
  `MISSION.md` and lesson files.

Installing one over the other is not an error a moment later: nothing fails,
and an agent asked to run `tdd` quietly runs the other collection's workflow.
So the second install stops and names the conflict instead:

```
error: mattpocock/skills ships 2 skill(s) that another collection already owns
in ~/.claude/skills: tdd (owned by pstack), teach (owned by pstack). … Either
rerun with --force to replace them, or remove the other copy first with
`--uninstall --skill tdd --skill teach` … Both back the old copy up before
touching it.
```

Every root is checked before any root is written, so a conflict in the second
one does not leave the first half-replaced.

Asking for both in one command (`--matt-skills --pstack`) hits this too:
`mattpocock/skills` installs first and completely, then pstack stops on the two
shared names. That is the intended answer rather than a rough edge — the
command asked for two collections that cannot both own `tdd`, and the only
alternatives are to pick a winner silently or to refuse both. Decide which
collection should own those names and add `--force`, or install one of them
without the other.

`--force` accepts the replacement, backing the old copy up first. Ownership
then moves with the files: the collection that wrote the directory last owns
the name, so its own next update is an update rather than a conflict with
itself, and asking to flip the name back is a fresh stop. A visibility choice
recorded against the old owner is dropped rather than re-applied — the name now
means a different skill, and "show me `tdd`" was said about the one that just
lost it.

The other remedy works too: `--uninstall --skill tdd` removes the copy and
clears the ownership with it, after which the blocked install goes through. A
skill an external collection placed through this installer counts as this
installer's to remove, even though no receipt records it — on a root that
predates the record, add `--force` there as well, because nothing then proves
who put the directory there.

This is recorded in `.skills-external.json` beside each root's receipt — which
collection placed which skills, at which revision. Nothing in a skill directory
says where it came from, and that record is the only thing that can say.

## Skills hidden from the model

pstack sets `disable-model-invocation: true` on 39 of its 44 skills, keeping
their descriptions out of every session's context. The cost is that a harness
routing slash commands through the model reports "that skill is not installed"
for a skill sitting right there on disk.

The dashboard's `pstack` row unfolds those skills so they can be enabled
individually, and `--enable-skill NAME` does the same from a script. Choices
are recorded and re-applied after an update, so enabling one does not have to
be done twice.

That review is per-collection, which is what the `.skills-external.json` record
above makes possible: `mattpocock/skills` hides 20 of its 35 and pstack hides
39 of its 44, and without a record of who installed what, each row would list
the union and unhiding under one would silently unhide the other's skills.

A root installed before that record existed has none, so attribution there
falls back to the marker directory — the one thing that says which collection
wrote a root that predates the bookkeeping.

## Written for Cursor

pstack is a Cursor plugin and does not hide it. 28 of its markdown files
reference `.cursor` paths or Cursor-only affordances: six name `AskQuestion`, a
Cursor tool with no Claude Code equivalent, and `setup-pstack` writes a
machine-level rules file at `~/.cursor/rules/` naming specific model slugs.

Installed under Claude Code these skills still read as instructions and the
prose still applies — the `principle-*` set and the writing skills (`unslop`,
`technical-writing`) carry no Cursor coupling at all. But the setup step and
the model-routing skills assume a harness this collection does not install
into, and nothing here rewrites them: a vendored edit to somebody else's skill
is drift that no hash would catch.

## One-time repository setup

Installing the files is the machine-level step. Then invoke `/setup-pstack`
once from inside the target repository to configure which models pstack uses
per role. This is a user or agent action; the terminal installer cannot invoke
a coding-agent slash command on the user's behalf. On a non-Cursor harness that
step is the one most likely to need adapting, since what it writes is a Cursor
rules file.

Skipping these skills entirely is fully supported: every skill bundled in this
collection installs and runs without them.
