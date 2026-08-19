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
