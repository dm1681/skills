---
name: push
description:
  Push current branch changes to origin and create or update the corresponding
  pull request; use when asked to push, publish updates, or create pull request.
---

# Push

Read `.symphony-worker.json` for `base_branch` and `validation_command`; substitute the actual branch in command examples. Preserve project coding standards and use the configured validation command instead of upstream repository-specific checks.

## Prerequisites

- `gh` CLI is installed and available in `PATH`.
- `gh auth status` succeeds for GitHub operations in this repo.

## Goals

- Push current branch changes to `origin` safely.
- Create a PR if none exists for the branch, otherwise update the existing PR.
- Keep branch history clean when remote has moved.

## Related Skills

- `pull`: use this when push is rejected or sync is not clean (non-fast-forward,
  merge conflict risk, or stale branch).

## Steps

1. Identify current branch and confirm remote state. Refuse to push if HEAD is
   detached or the current branch is `base_branch`; create or recover the issue's
   feature branch first.
2. Run local validation (the configured project validation command) before pushing.
3. Push branch to `origin` with upstream tracking if needed, using whatever
   remote URL is already configured.
4. If push is not clean/rejected:
   - If the failure is a non-fast-forward or sync problem, run the `pull`
     skill to merge `origin/<base_branch>`, resolve conflicts, and rerun validation.
   - Push again; use `--force-with-lease` only when history was rewritten.
   - If the failure is due to auth, permissions, or workflow restrictions on
     the configured remote, stop and surface the exact error instead of
     rewriting remotes or switching protocols as a workaround.

5. Ensure a PR exists for the branch:
   - If no PR exists, create one.
   - If a PR exists and is open, update it.
   - If branch is tied to a closed/merged PR, create a new branch + PR.
   - Write a proper PR title that clearly describes the change outcome
   - For branch updates, explicitly reconsider whether current PR title still
     matches the latest scope; update it if it no longer does.
6. Write/update the PR body before creating or editing the PR. Use
   `.github/pull_request_template.md` if present; otherwise describe the concrete
   problem, resulting behavior, validation and any material limitations:
   - Fill every section with concrete content for this change.
   - Replace all placeholder comments (`<!-- ... -->`).
   - Keep bullets/checkboxes where template expects them.
   - If PR already exists, refresh body content so it reflects the total PR
     scope (all intended work on the branch), not just the newest commits,
     including newly added work, removed work, or changed approach.
   - Do not reuse stale description text from earlier iterations.
7. Check the PR body against any available project template and documented PR validator.
8. Reply with the PR URL from `gh pr view`.

## Commands

```sh
# Identify branch
branch=$(git branch --show-current)
base_branch=$(python3 -c 'import json; print(json.load(open(".symphony-worker.json"))["base_branch"])')
if [ -z "$branch" ] || [ "$branch" = "$base_branch" ]; then
  echo "Refusing to push without an issue feature branch." >&2
  exit 1
fi

# Minimal validation gate
# Run validation_command from .symphony-worker.json

# Initial push: respect the current origin remote.
git push -u origin HEAD

# If that failed because the remote moved, use the pull skill. After
# pull-skill resolution and re-validation, retry the normal push:
git push -u origin HEAD

# If the configured remote rejects the push for auth, permissions, or workflow
# restrictions, stop and surface the exact error.

# Only if history was rewritten locally:
git push --force-with-lease origin HEAD

# Ensure a PR exists (create only if missing)
pr_state=$(gh pr view --json state -q .state 2>/dev/null || true)
if [ "$pr_state" = "MERGED" ] || [ "$pr_state" = "CLOSED" ]; then
  echo "Current branch is tied to a closed PR; create a new branch + PR." >&2
  exit 1
fi

# Write a clear, human-friendly title that summarizes the shipped change.
pr_title="<clear PR title written for this change>"
# Draft /tmp/pr_body.md with real newlines and the full current scope first.
# Follow the project template if present; otherwise use the fallback in step 6.
if [ -z "$pr_state" ]; then
  gh pr create --base "$base_branch" --head "$branch" --title "$pr_title" --body-file /tmp/pr_body.md
else
  # Reconsider title/body on every update; edit if scope shifted.
  gh pr edit --title "$pr_title" --body-file /tmp/pr_body.md
fi

tmp_pr_body=$(mktemp)
gh pr view --json body -q .body > "$tmp_pr_body"
# Run a project PR-body validator if one is documented.
rm -f "$tmp_pr_body"

# Show PR URL for the reply
gh pr view --json url -q .url
```

## Notes

- Do not use `--force`; only use `--force-with-lease` as the last resort.
- Distinguish sync problems from remote auth/permission problems:
  - Use the `pull` skill for non-fast-forward or stale-branch issues.
  - Surface auth, permissions, or workflow restrictions directly instead of
    changing remotes or protocols.
