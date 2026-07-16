# Olympus agentic documentation

Documentation is a navigation layer for agents. It should reduce the cost of
finding the right abstraction, understanding a contract, and changing code
without violating an invariant. Do not impose a comment-coverage quota.

## Documentation hierarchy

Put information at the narrowest durable layer that owns it:

- `/** ... */` documentation comments: symbol purpose and caller contract.
- Tests: executable examples, edge cases, and observable behavior.
- `CONTEXT.md`: canonical domain terms and rejected synonyms.
- `docs/adr/`: durable architectural decisions and rationale.
- README or runbook: public setup, operation, and troubleshooting paths.

Do not duplicate a full domain rule or ADR inside a symbol comment. Name the
rule concisely and use `@see` with a repository-relative canonical path when a
reader needs the larger decision.

## Documentation decision rule

Prefer `/** ... */` documentation comments. Require one for a changed or newly
introduced symbol when an agent using or modifying that symbol cannot recover a
material contract from its name, type, nearby code, and canonical linked docs.
This includes:

- exported APIs, schemas, types, components, and utilities whose purpose or
  contract is not fully evident from the name and type;
- boundary functions with side effects, persistence, network behavior, error
  translation, ordering, lifecycle, security, or migration responsibilities;
- internal abstractions with a non-obvious invariant that a future agent could
  plausibly violate while making a nearby change.

Do not require comments for obvious data aliases, mechanical wrappers, local
helpers whose behavior is clear from code and types, or every exported React
component merely because it is exported.

Tests prove behavior; they do not replace a nearby comment when callers need
the contract to use a public or boundary API safely. For a purely internal
symbol, clear code plus a focused test is sufficient unless a future agent
could plausibly violate the invariant while changing nearby code without
discovering the test.

If ordering or lifecycle behavior is caller-visible and durable, document it at
the public boundary and verify it in a test. If it is only an implementation
detail, do not elevate it into documentation; test it only when correctness
depends on preserving it.

## Content standard

Write the shortest comment that preserves the contract. Include only relevant
facts:

- why the symbol exists and what responsibility it owns;
- caller-visible guarantees, preconditions, or postconditions;
- non-obvious invariants, units, ordering, side effects, or failure behavior;
- the canonical term or decision that constrains it.

Be precise and explicit. Do not restate the symbol name, signature, or type. Do
not narrate the implementation, predict future work, copy acceptance criteria,
or leave claims that cannot be verified from code, tests, or canonical docs.
Use Olympus glossary terms from `CONTEXT.md`.

## Role ownership

- Planner identifies documentation surfaces, the ambiguity to remove, and the
  correct destination: code comment, test, `CONTEXT.md`, ADR, or runbook.
- Worker authors or updates documentation with the implementation and removes
  stale comments made false by the change.
- Reviewer enforces accuracy, placement, concision, domain vocabulary, and
  agent usefulness. The Reviewer never edits code or authors documentation.
- Orchestrator reports material documentation changes and ensures durable
  project documentation is included in presentation when it affects use or
  future delivery.

## Review severity

A Blocking documentation finding requires evidence that the change leaves a
material public contract, non-obvious invariant, side effect, failure mode, or
canonical claim missing, false, contradictory, or likely to mislead a future
agent. Record it under `documentation-claim`; the required actor is the Worker.
Documentation that the canonical brief explicitly requires is also blocking
until it is present and accurate.

Style-only preferences are advisory. A missing comment is not blocking when
the name, type, tests, and neighboring code already make the contract clear.
