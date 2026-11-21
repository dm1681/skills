#!/usr/bin/env python3
"""Convene a council: put one brief to Codex, Claude and Gemini in parallel.

Every seat runs read-only with the brief on stdin. Its working directory is a
new, empty folder, and the repository given by --cwd is granted read access
separately. A working directory is where each CLI loads project settings,
hooks, MCP servers and folder trust from, and the repository under review is
not trusted to supply any of them. Each answer is written to <out>/<seat>.md and the combined report is
printed to stdout. Standard library only.

Exit codes: 0 when at least one seat answered, 1 when none did, 2 for a usage
error (no brief, an unknown seat, or a call from inside a council seat).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
GEMINI_SETTINGS = HERE / "gemini-settings.json"
CLAUDE_SETTINGS = HERE / "claude-settings.json"

# Set in every seat's environment. A seat that tries to convene its own
# council is refused, so a council never recurses into nine more calls.
SEAT_MARKER = "COUNCIL_SEAT"

CODEX_MODEL, CODEX_EFFORT = "gpt-6.2-astra", "xhigh"
# Tried only when the server refuses CODEX_MODEL as a model (a ChatGPT login
# is not offered every API model), never after a timeout or an auth error.
CODEX_FALLBACK_MODEL = "gpt-6-astra"
MODEL_REFUSED = re.compile(r"model_not_found|model is not supported", re.IGNORECASE)
CLAUDE_MODEL, CLAUDE_EFFORT = "claude-fable-5-2", "xhigh"
# Gemini CLI sets thinking effort per model alias, not per call. The alias is
# defined in gemini-settings.json: gemini-4-neon at thinking level XHIGH.
GEMINI_ALIAS, GEMINI_LABEL = "council-neon", "gemini-4-neon (XHIGH)"

PREAMBLE = """\
You hold one seat on an advisory council. Another coding agent is asking
several independent models for advice before it acts. You are advising, not
acting.

- Work read-only. The repository under discussion is at {repo}; you may
  read its files to check a claim. Change nothing, run nothing that writes,
  and convene no council or subagent of your own.
- Answer from your own judgement. Where the brief states a belief or a
  preferred option, test it rather than adopt it. Disagreement is useful.
- Say which statements you checked against the code or the docs and which
  are inference.

Answer in this shape:

## Recommendation
One or two sentences: what to do.

## Reasoning
Why, with the evidence you checked.

## Risks
What could go wrong with your recommendation, and how to notice it early.

## What would change my mind
The fact or result that would flip your advice.

## Confidence
low, medium or high, and why.

---- BRIEF ----
"""


@dataclass(frozen=True)
class Seat:
    name: str
    binary: str
    label: str
    command: Callable[[Path, Path], list[str]]  # (answer file, repository)
    env: dict[str, str]
    # Codex writes its final message to a file; the others answer on stdout.
    answer_file: bool = False
    # The seat to ask instead when the server refuses this one's model.
    fallback: Seat | None = None


def _codex(model: str) -> Callable[[Path, Path], list[str]]:
    def command(out_file: Path, _repo: Path) -> list[str]:
        # The read-only sandbox can read the repository from any working directory.
        return [
            "exec",
            "-m", model,
            "-c", f'model_reasoning_effort="{CODEX_EFFORT}"',
            "-s", "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "-o", str(out_file),
            "-",
        ]
    return command


def _claude(_: Path, repo: Path) -> list[str]:
    return [
        "-p",
        "--add-dir", str(repo),
        # User settings only, with every hook off: nothing in the repo runs.
        "--setting-sources", "user",
        "--settings", str(CLAUDE_SETTINGS),
        "--model", CLAUDE_MODEL,
        "--effort", CLAUDE_EFFORT,
        "--tools", "Read,Grep,Glob",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format", "text",
    ]


def _gemini(_: Path, repo: Path) -> list[str]:
    return [
        "-m", GEMINI_ALIAS,
        "--approval-mode", "plan",
        # Trusts only the empty working folder. The repository is included for
        # reading, which loads none of its settings, hooks or MCP servers.
        "--skip-trust",
        "--include-directories", str(repo),
        "-o", "text",
        "-p", "Answer the council brief above.",
    ]


SEATS = {
    "codex": Seat(
        "codex", "codex", f"{CODEX_MODEL} ({CODEX_EFFORT})", _codex(CODEX_MODEL), {}, answer_file=True,
        fallback=Seat("codex", "codex", f"{CODEX_FALLBACK_MODEL} ({CODEX_EFFORT}, fallback)",
                      _codex(CODEX_FALLBACK_MODEL), {}, answer_file=True),
    ),
    "claude": Seat("claude", "claude", f"{CLAUDE_MODEL} ({CLAUDE_EFFORT})", _claude, {}),
    "gemini": Seat(
        "gemini",
        "gemini",
        GEMINI_LABEL,
        _gemini,
        # Points the CLI at the alias without touching the user's own
        # ~/.gemini/settings.json. It replaces the system settings layer.
        {"GEMINI_CLI_SYSTEM_SETTINGS_PATH": str(GEMINI_SETTINGS)},
    ),
}


@dataclass
class Verdict:
    seat: Seat
    ok: bool
    text: str


Runner = Callable[..., subprocess.CompletedProcess]


def consult(seat: Seat, prompt: str, repo: Path, out_dir: Path, timeout: int,
            run: Runner = subprocess.run, which=shutil.which) -> Verdict:
    """Put the prompt to one seat and return its answer or why it has none."""
    exe = which(seat.binary)
    if exe is None:
        return Verdict(seat, False, f"`{seat.binary}` is not on PATH; this seat is empty.")
    answer_path = out_dir / f"{seat.name}.md"
    argv = [exe, *seat.command(answer_path, repo)]
    env = {**os.environ, **seat.env, SEAT_MARKER: "1"}
    # A fresh temp folder sits outside every repository, so no CLI finds a
    # project config by walking up from it - whatever --out is.
    workdir = tempfile.mkdtemp(prefix=f"council-{seat.name}-")
    try:
        done = run(argv, input=prompt, cwd=workdir, env=env, capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return Verdict(seat, False, f"No answer within {timeout} s.")
    except OSError as error:
        return Verdict(seat, False, f"Could not start `{seat.binary}`: {error}")

    if seat.answer_file and answer_path.exists():
        answer = answer_path.read_text(encoding="utf-8", errors="replace").strip()
    else:
        answer = (done.stdout or "").strip()
    if done.returncode != 0 or not answer:
        output = f"{done.stderr or ''}\n{done.stdout or ''}"
        if seat.fallback is not None and MODEL_REFUSED.search(output):
            verdict = consult(seat.fallback, prompt, repo, out_dir, timeout, run, which)
            refused = seat.label.split(" (")[0]
            verdict.text = f"_`{refused}` was refused by the server; this is the fallback._\n\n{verdict.text}"
            return verdict
        tail = "\n".join((done.stderr or done.stdout or "").strip().splitlines()[-12:])
        return Verdict(seat, False, f"Exited {done.returncode} without an answer.\n\n```\n{tail}\n```")
    answer_path.write_text(answer + "\n", encoding="utf-8")
    return Verdict(seat, True, answer)


def report(verdicts: list[Verdict], out_dir: Path) -> str:
    answered = sum(v.ok for v in verdicts)
    lines = [f"# Council report: {answered} of {len(verdicts)} seats answered", "",
             f"Answers saved in {out_dir}", ""]
    for v in verdicts:
        status = "answered" if v.ok else "NO ANSWER"
        lines += [f"## {v.seat.name}: {v.seat.label}, {status}", "", v.text, ""]
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ask Codex, Claude and Gemini for advice on one brief.")
    p.add_argument("--brief", type=Path, help="file holding the brief (default: read stdin)")
    p.add_argument("--seats", default="codex,claude,gemini",
                   help="comma-separated seats to convene (default: all three)")
    p.add_argument("--cwd", type=Path, default=Path.cwd(),
                   help="repository the seats may read, never run from (default: current directory)")
    p.add_argument("--out", type=Path, help="directory for the answers (default: a new temp dir)")
    p.add_argument("--timeout", type=int, default=1200, help="seconds each seat may take (default: 1200)")
    p.add_argument("--dry-run", action="store_true", help="print each seat's command and stop")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if os.environ.get(SEAT_MARKER):
        print("council: refused - this process is already a council seat.", file=sys.stderr)
        return 2
    names = [n.strip() for n in args.seats.split(",") if n.strip()]
    unknown = [n for n in names if n not in SEATS]
    if unknown or not names:
        print(f"council: unknown seat(s) {unknown or names}; choose from {', '.join(SEATS)}.", file=sys.stderr)
        return 2
    seats = [SEATS[n] for n in names]

    if args.dry_run:
        for seat in seats:
            for role, s in (("", seat), (" (if refused)", seat.fallback)):
                if s is None:
                    continue
                extra = " ".join(f"{k}={v}" for k, v in s.env.items())
                cmd = " ".join([s.binary, *s.command(Path("<out>") / f"{s.name}.md", args.cwd.resolve())])
                print(f"{s.name}{role}: {(extra + ' ') if extra else ''}{cmd} < brief")
        return 0

    brief = (args.brief.read_text(encoding="utf-8") if args.brief else sys.stdin.read()).strip()
    if not brief:
        print("council: the brief is empty; pass --brief FILE or pipe it on stdin.", file=sys.stderr)
        return 2
    out_dir = args.out or Path(tempfile.mkdtemp(prefix="council-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    repo = args.cwd.resolve()
    prompt = PREAMBLE.format(repo=repo) + brief + "\n"
    (out_dir / "brief.md").write_text(brief + "\n", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=len(seats)) as pool:
        verdicts = list(pool.map(
            lambda s: consult(s, prompt, repo, out_dir, args.timeout), seats))
    if hasattr(sys.stdout, "reconfigure"):  # a redirected stdout may not have it
        sys.stdout.reconfigure(encoding="utf-8")
    print(report(verdicts, out_dir))
    return 0 if any(v.ok for v in verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())
