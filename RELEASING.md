# Releasing

The repository follows Semantic Versioning and is released as a single skills
collection.

## What the number means

Semantic Versioning, read against what this repository actually ships: a
collection of skills plus the installer and CLI that place them. The question
is always whether a consumer who did something that worked has to change
anything.

**MAJOR** — something that worked before now does not.

- A skill is removed or renamed (`8.0.0` retired `orchestrate-olympus`).
- An interface is replaced rather than extended (`9.0.0` swapped the
  prompt-driven wizard for the Textual dashboard).
- Input that used to be accepted is now rejected — a validator promoted from
  advisory to enforced, a stricter schema, a narrowed flag.
- A prerequisite is swapped for a different one, so a machine that could run a
  path no longer can.

**MINOR** — new surface, nothing invalidated.

- A skill is added (`7.1.0` added `semantic-pr-review`).
- A command, subcommand, or flag is added.
- Behaviour changes inside an interactive flow without breaking a scripted one
  (`8.1.0` stopped the wizard asking about `--scope`). A default someone can
  still override is a minor; a default they cannot is a major.

**PATCH** — a defect fixed inside the existing contract, or documentation,
comments, and tests on their own.

Two rules that keep this cheap to apply:

1. **The number is decided when a release is cut, not per push.** Entries
   accumulate under `Unreleased`; the pending bump is simply the highest any
   single entry warrants. Assessing a push means asking whether it escalates
   that, which is usually "no".
2. **When two readings are defensible, take the larger one.** A version is a
   promise to whoever installs without reading the diff, and this collection
   has never been shy about majors — 6.x through 9.x inside three weeks.

## A skill's version vs. the collection's

Every non-vendored `SKILL.md` carries its own `version:` in frontmatter,
separate from `VERSION` at the repository root. They answer different
questions and move on different clocks.

`VERSION` versions the collection: the installer, the CLI, and the release as
a whole. A skill's `version:` versions that one skill's contract — what an
agent that already uses it can rely on. Bumping one does not bump the other.
Adding a skill is a collection **MINOR** (a new skill starts its own history
at `1.0.0`) but touches no other skill's version; fixing a typo in
`wow-addon-dev`'s SKILL.md is that skill's **PATCH** and need not move
`VERSION` at all unless it is the only change in the release.

Read MAJOR/MINOR/PATCH above against the skill itself, not the collection:

**MAJOR** — a workflow that used to work against this skill now does not: a
step removed, a required input renamed, an assumption the skill documented
(a tool it required, a format it produced) replaced rather than extended.

**MINOR** — new surface inside the skill that invalidates nothing already
there: a new step, a new reference file, a new trigger phrase added to
`description` alongside the existing ones.

**PATCH** — a wording fix, a corrected example, a broken link — the skill's
contract with whoever already relies on it is unchanged.

This is self-enforcing, not just documented: the validator resolves the most
recent `vMAJOR.MINOR.PATCH` tag *before* HEAD and errors on any skill whose
files changed since that tag but whose `version:` did not
(`scripts/validate_repo.py`, `bump_errors`). A version nobody is forced to
bump is worse than no version — it looks like a promise instead of admitting
it stopped being tracked.

Two details make it actually run rather than merely exist. It steps back past
a tag on HEAD when `skills/` is untouched beside it, because the release
workflow checks out the pushed tag and every skill would otherwise diff clean
against itself — but only then, so an edit made the minute after a release is
still checked against the release it changes. And it counts untracked files,
because adding a `references/` file is the usual way to grow a skill and `git
diff` cannot see one before it is staged.

The check goes quiet, not red, wherever it cannot answer the question: no
`git` on the machine, no tag yet, or a release archive with no `.git` at
all — the same posture `checkout_behind_origin` already takes for the
collection-wide freshness check. That is also why CI checks out with
`fetch-depth: 0`: a shallow clone has no tags, and a check that cannot run is
a check that always passes.

`skills/olympus-report-progress` carries no `version:` and is exempt from
this check entirely — it is vendored, pinned by the SHA256 of its upstream
bytes rather than by a local version, and a version key there would hash as
drift the skill never actually had (see `install.VENDORED_SKILLS`).

## Prepare a release

1. Update `VERSION` and `project.version` in `pyproject.toml` to the same
   `MAJOR.MINOR.PATCH` value without a `v` prefix.
2. Run `uv lock` to refresh the locked project version.
3. Move the relevant `CHANGELOG.md` entries from `Unreleased` into a heading
   named `## [MAJOR.MINOR.PATCH] - YYYY-MM-DD`.
4. Run `uv sync --locked`, the repository validator, and tests through `uv run`.
5. Merge the version change to `main`.

## Publish

Use the **Release** workflow in GitHub Actions and enter the exact value from
`VERSION`. The workflow validates the repository, packages `.tar.gz` and `.zip`
archives, writes SHA-256 checksums, creates tag `vMAJOR.MINOR.PATCH`, and
publishes a GitHub release with generated notes.

Pushing a matching `v*` tag manually runs the same validation and packaging
path. A tag that does not exactly match `VERSION` fails before publishing.

## Verify

```sh
gh release view vMAJOR.MINOR.PATCH --repo dm1681/skills
gh release download vMAJOR.MINOR.PATCH --repo dm1681/skills --pattern 'SHA256SUMS'
```
