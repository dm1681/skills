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
git init --quiet --template=
git fetch --quiet --depth 1 https://github.com/mattpocock/skills.git v1.2.3
git -c core.hooksPath=.git/no-hooks -c core.autocrlf=false -c core.eol=lf \
  checkout --quiet --detach FETCH_HEAD
git status --porcelain   # must be empty before anything is copied
git ls-tree -r FETCH_HEAD -- skills/   # every blob compared against
git hash-object --no-filters …         # the bytes actually on disk
```

The fetch runs with `GIT_TERMINAL_PROMPT=0` and `GIT_ASKPASS=echo`, so a `401`
— a proxy in the way, a repository URL pointing somewhere private — fails in a
second instead of waiting on a password nobody is there to type.

`git fetch <url> <ref>` rather than `git clone --branch <ref>`, because clone's
`--branch` takes a tag or a branch and refuses a commit SHA. Every install
prints the ref and the commit it resolved to, so `--matt-ref main` still leaves
a record of what actually arrived.

Checkout overrides line-ending conversion because Git for Windows enables
`core.autocrlf` by default. Without the override the same commit installs
different bytes there than everywhere else, and the shell script one upstream
skill ships arrives with a `#!/bin/bash\r` shebang that no POSIX shell can run.

It also keeps the user's own git hooks out of the disposable checkout, by two
doors because closing one leaves the other open: `--template=` stops
`init.templateDir` from seeding this repository with them, and an unreadable
`core.hooksPath` neutralizes a global setting the empty template does not
affect. A `post-checkout` hook would otherwise run before the copy and edit
files that the commit check still calls correct. Since a hook is not the only
thing that can rewrite a working tree, the install then asks git whether the
checkout still matches the commit, and stops without copying if it does not.

That question is asked twice, because `git status` alone cannot answer it. A
`.gitattributes` in the fetched revision can set `eol`, which outranks the
config the checkout passes; git rewrites the files on the way out and then
calls the result clean, because it applies the same attribute on the way back
in. So the install also hashes the bytes as they sit on disk, with filters
off, against the blobs the commit records. Nothing upstream sets such an
attribute today — the check exists so the day it does is a stop with a
readable message rather than a silently different install.

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
# Track upstream.
./install.sh --agent all --matt-skills --matt-ref main

# An older release.
./install.sh --agent all --matt-skills --matt-ref v1.2.2

# An exact commit, named in full: the remote resolves the argument as a
# refspec, and an abbreviated SHA is not one.
./install.sh --agent all --matt-skills \
  --matt-ref 9c9f36ccd3995266cd675468af71639c8dde1ec5
```

A named ref is checked against no second pin — it *is* the revision the caller
chose. An empty one (`--matt-ref "$REF"` with `REF` unset) is refused rather
than quietly falling back to the default.

Updating the pin is a commit somebody reviews, and the diff behind it is
readable before it lands:

```sh
# Not into ./skills: that is this repository's own bundled-skills directory,
# and git refuses a non-empty destination.
git clone https://github.com/mattpocock/skills.git /tmp/mattpocock-skills
git -C /tmp/mattpocock-skills diff v1.2.3..v1.3.0 -- skills/
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
  silently win. The comparison is case-insensitive, because `Foo` and `foo` are
  two directories upstream but one destination on Windows and on a stock macOS
  filesystem. Nothing collides today.

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
