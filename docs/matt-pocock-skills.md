# Matt Pocock skills (optional)

[`mattpocock/skills`](https://github.com/mattpocock/skills) provides
implementation, test-driven development, and two-axis review workflows. No skill
bundled in this collection depends on them, so they are a pure opt-in. When
requested, the complete collection is installed so those workflows and their
transitive skill dependencies remain coherent.

## Install behavior

The wizard never prompts for third-party downloads. Installing them is always
explicit:

```sh
./install.sh --agent all --matt-skills
```

The installer shallow-fetches one revision of the upstream repository into a
disposable checkout, then copies every skill it discovers into the same resolved
roots used for the bundled skills. That preserves `~/.agents/skills` for shared
user installs and applies the installer's existing backup-before-replace policy.

The effective commands have this form:

```sh
git init --quiet
git fetch --quiet --depth 1 https://github.com/mattpocock/skills.git v1.2.3
git checkout --quiet --detach FETCH_HEAD
```

`git fetch <url> <ref>` rather than `git clone --branch <ref>`, because clone's
`--branch` takes a tag or a branch and refuses a commit SHA. Every install
prints the ref and the commit it resolved to, so `--matt-ref main` still leaves
a record of what actually arrived.

Git is the only requirement; there is no Node.js dependency. `--dry-run` prints
the exact commands and final destinations without network access. Custom
`--target` paths are supported because destination resolution remains under this
installer's control.

## Which revision gets installed

`MATT_SKILLS_REF` in `install.py` pins the default, so two installs a week apart
are the same install. A tag is a movable label, so `MATT_SKILLS_COMMIT` records
the commit behind it and the default install stops if upstream has force-moved
the tag since — update the two together. Override the ref per run:

```sh
./install.sh --agent all --matt-skills --matt-ref main       # track upstream
./install.sh --agent all --matt-skills --matt-ref v1.2.2     # an older release
./install.sh --agent all --matt-skills --matt-ref 9c9f36c    # an exact commit
```

A named ref is checked against no second pin — it *is* the revision the caller
chose. An empty one (`--matt-ref "$REF"` with `REF` unset) is refused rather
than quietly falling back to the default.

Updating the pin is a commit somebody reviews, and the diff behind it is
readable before it lands:

```sh
git clone https://github.com/mattpocock/skills.git
git -C skills diff v1.2.3..v1.3.0 -- skills/
```

## What gets installed

Upstream files its skills under `skills/<category>/<name>/`; every consumer,
including upstream's own CLI, installs them flat as `<name>/`. Discovery walks
the checkout for `SKILL.md` rather than assuming that depth, so a reorganization
upstream costs nothing here. Two exceptions:

- `skills/deprecated/` is skipped — matched on the first path component only, so
  a skill that merely has `deprecated` deeper in its path still installs.
  Upstream retires skills there instead of deleting them, and a retirement
  should not arrive as a fresh install.
- Two categories claiming one name stops the install rather than letting one
  silently win. Nothing collides today.

Every selected root receives the same files. The skills carry no agent-specific
content — upstream's CLI wrote byte-identical trees to each agent it was given —
so there is no agent mapping to keep in step any more.

An upstream checkout that does not contain `setup-matt-pocock-skills` fails the
install, because that is the shape of the collection changing under us and a
partial install is worse than a stop.

## One-time repository setup

Installing the files is the machine-level step. Then invoke
`/setup-matt-pocock-skills` once from inside the target repository to configure
the issue tracker, triage labels, and documentation layout. This is a user or
agent action; the terminal installer cannot invoke a coding-agent slash command
on the user's behalf.

Skipping these skills entirely is fully supported: every skill bundled in this
collection installs and runs without them.
