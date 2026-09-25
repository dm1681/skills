# Pinned state fixture

Synthetic data matching OpenAI Symphony commit
`be10a1b79df723d6d7612b5651c8522704dafb2e`:

- [`Presenter.state_payload`, running/retry projections](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir_web/presenter.ex)
- [`Router` GET state route](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir_web/router.ex)
- [`Orchestrator` codex_totals](https://github.com/openai/symphony/blob/be10a1b79df723d6d7612b5651c8522704dafb2e/elixir/lib/symphony_elixir/orchestrator.ex)

Inspected at the exact pin on 2026-09-24. No real prompts, credentials, issue
changes, or model turns. The sentinels prove that upstream message/error fields
are not forwarded. Titles are absent from this API. Tests replace timestamps
with an injected clock or current fixture time.
