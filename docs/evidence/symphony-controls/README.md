# Synthetic repository control walkthrough

Produced by `scripts/prove_symphony_controls.py` on 2026-09-24 using the existing
Playwright Chromium installation, two isolated Python HTTP processes, and a
file-backed deterministic service-manager fixture. No production Symphony or
Codex process, tracker, service or credential was used.

- [Two repositories](two-repositories.png): Alpha running/active and Beta stopped.
- [Start](started.png): explicit UI confirmation starts Beta once; Alpha remains active.
- [Stop](stopped.png): explicit Stop terminates Beta's fake process; Alpha remains active.
- [Readiness failure](readiness-failure.png): rejected fixture setup gate launches no process.
- [Recovery](recovered.png): correcting the fixture gate permits a new explicit start.
- [Machine-readable results](results.json): includes duplicate Start HTTP 409, multiple
  browser tabs, browser closure and zero JavaScript errors.

Reproduce with an existing Playwright interpreter:

```sh
/path/to/playwright/python scripts/prove_symphony_controls.py \
  --output .symphony/controls-proof
```

The manager fixture proves the shared UI/API path and request validation. It does
**not** prove real systemd unit creation, cgroup ownership after a parent crash,
or descendant cleanup on SIGTERM. The corresponding opt-in test is checked in:

```sh
SKILLS_SYMPHONY_SYSTEMD_TEST=1 uv run python -m unittest discover -s tests \
  -p test_symphony_systemd.py -v
```

That test failed before any unit mutation in this worker: the systemd user bus
is inaccessible (`systemctl --user show` reports `No data available`). It uses a
unique transient unit and generated fake runtime/worker processes, never an
existing service. It remains required acceptance work; these screenshots are
not a claim that the production manager integration passed.
