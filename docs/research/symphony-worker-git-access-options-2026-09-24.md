# Symphony worker Git access: simpler options

Researched 2026-09-24 for this checkout's pinned Symphony revision, `be10a1b79df723d6d7612b5651c8522704dafb2e`. This records the options before the subsequent full-access change; the legacy adapter row below describes the former setup.

## What upstream and other first-party integrations do

| Approach | Evidence | Fit here |
| --- | --- | --- |
| Full Codex access inside a container | [Codex security guidance](https://learn.chatgpt.com/docs/agent-approvals-security) explicitly allows `danger-full-access` when a container supplies the outer isolation boundary. It warns that anything available inside the container, including credentials, remains accessible to a malicious project. | Simplest Codex/Symphony configuration once the worker environment is isolated. |
| Codex permission profile | [Codex permissions](https://learn.chatgpt.com/docs/permissions) supports rules relative to each runtime workspace root. Its documented path-override mechanism appears able to grant `.git` write permission for each worker without computing an absolute path; that specific rule still needs a runtime test. [Codex Action guidance](https://github.com/openai/codex-action/blob/main/docs/security.md) now prefers `:workspace` permission profiles for jobs that edit a checkout and also reduces the action process's host privileges. | Promising native alternative, but not a drop-in setting for our pinned Symphony: the same permissions documentation says profiles do not compose with legacy sandbox settings, and [Symphony's app-server bridge](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/codex/app_server.ex) passes legacy `sandbox` and `sandboxPolicy` on thread/turn start. It needs an upstream bridge change and an end-to-end test. |
| Legacy workspace-write plus a Git writable root | [Codex security guidance](https://learn.chatgpt.com/docs/agent-approvals-security) says `.git` is read-only in the default workspace-write sandbox. This checkout's former worker adapter supplied a per-workspace absolute Git metadata path through `writableRoots`. | Worked in local throwaway app-server tests; retained a custom launch component. |

The [pinned upstream sample workflow](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/WORKFLOW.md) sets `workspace-write` while instructing workers to commit and push. That is a mismatch with Codex's documented `.git` protection, not evidence that commits succeed. Symphony's [specification](https://github.com/openai/symphony/blob/main/SPEC.md) leaves sandbox and approval behavior to the implementation; the example is not a required policy.

## Recommendation for this installation

If simple, unattended Git work is the priority, use `danger-full-access` **inside a dedicated worker container or VM**. Make the intended checkout, required videos/output paths, and only the needed credentials available there. The container/VM then defines the worker's actual access boundary. This follows the documented Codex pattern and permits normal Git operations without per-workspace `writableRoots` injection.

Full access is also technically possible on the current shared WSL host, but its scope is the entire filesystem and credentials accessible to the Symphony OS user, including other projects and mounted Windows files. A cloned per-issue checkout does not restrict those writes. This may be an acceptable conscious choice for a trusted single-owner pilot, but it is materially broader than granting Git metadata writes in one checkout. The existing workflow already enables command network access under workspace-write, so the main change here is filesystem write scope.

The subsequent change removed the Git-specific sandbox adapter code and static workspace-write policy. It did **not** eliminate all local launch customization: this checkout's [model router](../../symphony_models.py) still supplies dynamic per-issue model and effort selection, which the pinned sample workflow otherwise fixes in `codex.command`.

If container setup is more work than the adapter it replaces, keep the working per-workspace Git root for now. The permission-profile route is worth revisiting after Symphony supports profile-based thread and turn settings, but it should not hold up the simpler pilot.
