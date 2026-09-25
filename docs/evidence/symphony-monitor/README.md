# Synthetic browser evidence

Captured with `scripts/prove_symphony_dashboard.py` on Linux, 2026-09-24.
All endpoints and issue rows are local fixtures. No Symphony process, model turn,
tracker credential or live issue mutation is involved.

- [Overview](overview.png): two distinct instances, same issue identifiers, two
  active workers and two retries; duplicate registration does not double totals.
  The third project explicitly has its dashboard disabled. The literal script
  label is an escaping test and does not execute.
- [Filtered](filtered.png): one project and retrying status selected.
- [Offline](offline.png): one failing instance excluded from current totals;
  its last successful observation remains visible.
- [Machine-readable results](results.json): additionally covers malformed API,
  recovery, empty registry, links, private-text exclusion, zero page errors and
  GET-only fixture traffic.

Rerun the documented proof command to regenerate evidence. Runtime adapter
contract sources are in `tests/fixtures/symphony/README.md`.
