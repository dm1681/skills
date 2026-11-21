---
name: council
description: Convene a council - put one brief to Codex (GPT-6.2 Astra), Claude (Fable 5.2) and Gemini (Neon), each at extra-high effort, read-only and in parallel, then weigh their independent advice before acting. Use when a decision is costly to reverse, when two attempts at a bug or task have failed, when choosing between designs or plans, before trusting a risky diagnosis, or when the user asks for a second opinion, other models' views, or the council.
version: 1.0.0
---

# Council

Three frontier models from three labs give **independent** advice on one
**brief**; you weigh it and decide. The value is in where they **dissent**:
one model's blind spot is rarely another's. A council advises — you stay the
one who acts, verifies, and answers to the user.

A council costs three extra-high-effort runs and several minutes. Convene it
when being wrong costs more than that.

## When to convene

- **One-way doors** — a schema or data migration, a public API shape, a
  dependency or framework choice, deleting or rewriting a subsystem.
- **Stuck** — two honest attempts at a bug or task have failed and the next
  idea is a guess. Ask for hypotheses, not fixes.
- **A fork in the plan** — two or three viable designs and no clear winner;
  ask each seat to argue for one and against the others.
- **Checking your own diagnosis** — a root cause you are about to act on that
  rests on inference rather than a reproduction.
- **Pre-mortem** — before a long autonomous run or a large refactor: "this
  plan failed; what most likely caused it?"
- **Security or correctness review** of a small, high-stakes diff (auth,
  money, concurrency, crypto, destructive scripts).
- **Ambiguous requirements** — the user's request reads two ways and you
  cannot ask them; the council shows which reading is the natural one.
- **The user asks** for a second opinion, other models, or the council.

Skip it for lookups, routine edits, anything a test run settles faster, and
taste calls the user has already made.

## 1. Write the brief

The seats start cold: no conversation, no memory, only the brief and
read-only access to `--cwd`. Write it so a stranger could answer it.

- **Question** — one sentence, ending in a question mark, asking for a
  decision or a ranked set of hypotheses.
- **Context** — the goal, the relevant files by path, what the code does
  today. Paste the short excerpts that matter; seats can read the rest.
- **Constraints** — what cannot change, deadlines, the user's stated
  preferences.
- **Already tried or ruled out** — with the evidence, so seats spend their
  effort past it.
- **Options on the table** — stated neutrally. Keep your own leaning out, or
  label it as yours; a brief that argues a case gets that case back.

Leave secrets, tokens, and private user data out of the brief: it goes to
three outside services.

Done when the brief names a single question and a seat could answer it
without asking you anything.

## 2. Convene

Save the brief to a file, then run, from any directory:

    python <this-skill>/scripts/council.py --brief brief.md --cwd <repo>

Each seat runs read-only, in parallel, with up to `--timeout` seconds
(default 1200). Answers go to a temp directory printed in the report;
`--out DIR` picks it. `--seats codex,claude` convenes a subset — use it to
leave out the seat whose model you are, or to re-ask one seat. `--dry-run`
prints the exact commands.

Run it in the background when your host allows, and keep working on
anything that does not depend on the answer.

A seat with no answer is reported as such — a missing CLI, an auth or
billing error, a timeout. Two answering seats still make a council; one does
not, so say so instead of presenting it as consensus.

## 3. Weigh the advice

Read every answer in full before forming a view. Then:

1. **Agreement** — what all answering seats recommend. Agreement among
   models is evidence, not proof: they share training data and blind spots.
2. **Dissent** — where they differ and *why*. A dissent grounded in a
   fact the others missed outweighs a majority.
3. **Verify** — every factual claim your decision rests on (an API exists,
   a function behaves a certain way, a file says X): check it yourself
   before acting. Seats hallucinate like any model.
4. **Decide** — your call, with the reason. You may overrule the whole
   council; say what you know that it did not.

Done when every recommendation is accepted, rejected or deferred with a
reason, and every claim you act on is checked.

## Reporting to the user

Lead with the decision and its reason, then the council in a few lines:
where the seats agreed, where they split, and which seat changed your mind
if one did. Attribute views to seats by name. Point to the answers directory
for the full text rather than pasting it.

## Seats

| Seat | CLI | Model | Effort |
| --- | --- | --- | --- |
| codex | `codex exec` | `gpt-6.2-astra`, or `gpt-6-astra` when the server refuses it | `xhigh` |
| claude | `claude -p` | `claude-fable-5-2` | `xhigh` |
| gemini | `gemini -p` | `gemini-4-neon` via the `council-neon` alias | `XHIGH` |

Model ids live at the top of `scripts/council.py`. The Codex fallback runs
only when the server refuses the model itself (a ChatGPT login is not
offered every API model), and its answer is labelled as the fallback;
report it as such. Gemini CLI sets thinking effort per model alias, so the
Gemini effort lives in `scripts/gemini-settings.json`, copied in as the
seat's workspace settings; the user's own settings are never written. A
seat cannot convene a council of its own: the script refuses when
`COUNCIL_SEAT` is set.

The Gemini seat signs in with Google, never an API key: it drops
`GEMINI_API_KEY` and `GOOGLE_API_KEY` from its environment. It needs a
one-time interactive sign-in; when it reports "Manual authorization is
required", tell the user to run, in a terminal of their own:

    Remove-Item Env:GEMINI_API_KEY; $env:GOOGLE_GENAI_USE_GCA='true'; gemini

and choose **Sign in with Google**. A POSIX shell uses
`env -u GEMINI_API_KEY GOOGLE_GENAI_USE_GCA=true gemini`.

`--cwd` may be a repository nobody vetted, so no seat runs inside it. Each
seat's working directory is a new, empty temp folder — the place every CLI
loads project settings, hooks, MCP servers and folder trust from — and the
repository is granted for reading only (`--add-dir` for Claude, which also
loads user settings alone with hooks off; `--include-directories` for
Gemini; Codex's read-only sandbox reads it directly).
