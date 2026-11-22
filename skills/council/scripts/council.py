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
import json
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
CLAUDE_SETTINGS = HERE / "claude-settings.json"

# Per-user install folders that a non-interactive shell often leaves off PATH
# (npm's --prefix ~/.npm-global, the Antigravity installer's ~/.local/bin).
EXTRA_BIN_DIRS = ("~/.local/bin", "~/.npm-global/bin", "~/.npm/bin")

# Set in every seat's environment. A seat that tries to convene its own
# council is refused, so a council never recurses into nine more calls.
SEAT_MARKER = "COUNCIL_SEAT"

CODEX_MODEL, CODEX_EFFORT = "gpt-6.2-astra", "xhigh"
# Tried only when the server refuses CODEX_MODEL as a model (a ChatGPT login
# is not offered every API model), never after a timeout or an auth error.
CODEX_FALLBACK_MODEL = "gpt-6-astra"
MODEL_REFUSED = re.compile(r"model_not_found|model is not supported", re.IGNORECASE)
CLAUDE_MODEL, CLAUDE_EFFORT = "claude-fable-5-2", "xhigh"
# The Gemini seat runs Antigravity CLI (`agy`), signed in with a personal
# Google account. Gemini CLI's Google sign-in stopped serving personal
# accounts on 2026-06-18, and an API key bills per call.
# agy names each effort level as its own model (`agy models` lists them).
GEMINI_MODEL = "gemini-4-neon-xhigh"
# The oldest agy release these flags were tested against.
GEMINI_MIN_VERSION = "1.5.14"

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
    # Environment variables removed before the seat starts.
    drop_env: tuple = ()
    # The oldest CLI version that accepts the flags this seat passes.
    min_version: str = ""
    # What to tell the user when the CLI says it is not signed in.
    sign_in: str = ""
    # Turns the prompt into the seat's stdin; default: the prompt as is.
    encode: Callable[[str], str] | None = None
    # Reads (answer, error, model) from stdout; default: stdout is the answer.
    decode: Callable[[str], tuple[str, str, str]] | None = None


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


# agy has no file-listing or search tool of its own: it explores with the
# shell. Only commands that can neither write nor run another program may
# run: no find (-delete, -exec) and no rg (--pre). A rule's regex must match
# the whole command; agy checks each part of a pipeline on its own. Any other
# command is soft-denied, since headless agy cannot ask.
READ_ONLY_COMMANDS = r"command(regex:(ls|grep|cat|head|tail|wc)( [^;&|<>`$]*)?)"
REDIRECTION = r"command(regex:.*([<>`]|\$\().*)"


def _gemini_settings(repo: Path) -> str:
    """Settings for one agy session, never saved: read the repository, change nothing."""
    return json.dumps({"permissions": {
        "allow": [f"read_file({repo})", READ_ONLY_COMMANDS],
        # Deny wins over every allow and every mode.
        "deny": ["write_file(*)", REDIRECTION, "mcp(*)", "execute_url(*)", "download_url(*)"],
    }})


def _gemini(_: Path, repo: Path) -> list[str]:
    # No --add-dir: an added folder joins the workspace, and agy then starts
    # the MCP servers and hooks in its .agents/ folder (seen in 1.5.14). The
    # repository is granted by a read rule instead, so the only workspace is
    # the empty working folder.
    return [
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--model", GEMINI_MODEL,
        "--settings", _gemini_settings(repo),
        # Where the machine has one, agy's sandbox confines shell commands too.
        # It does not stop a write outside the workspace (seen in 1.5.14), so
        # the permission rules above are what keep the seat read-only.
        "--sandbox",
        # Print mode, with the prompt read from stdin as one stream message.
        "--print=",
    ]


def _gemini_encode(prompt: str) -> str:
    return json.dumps({"event": "user", "message": {"role": "user", "content": prompt}}) + "\n"


def _gemini_decode(stdout: str) -> tuple[str, str, str]:
    """(answer, error, model) from agy's stream-json events."""
    answer, error, model = "", "", ""
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("event") == "init":
            model = str(event.get("init", {}).get("model", ""))
        elif event.get("event") == "result":
            result = event.get("result", {})
            answer = str(result.get("response") or "")
            if result.get("status") != "SUCCESS":
                error = str(result.get("error") or result.get("status") or "the run failed")
            elif not answer.strip() and result.get("denied_actions"):
                denied = ", ".join(a.get("action", "?") for a in result["denied_actions"])
                error = f"the seat stopped after the council denied it: {denied}"
    return answer, error, model


SEATS = {
    "codex": Seat(
        "codex", "codex", f"{CODEX_MODEL} ({CODEX_EFFORT})", _codex(CODEX_MODEL), {}, answer_file=True,
        fallback=Seat("codex", "codex", f"{CODEX_FALLBACK_MODEL} ({CODEX_EFFORT}, fallback)",
                      _codex(CODEX_FALLBACK_MODEL), {}, answer_file=True),
    ),
    "claude": Seat("claude", "claude", f"{CLAUDE_MODEL} ({CLAUDE_EFFORT})", _claude, {}),
    "gemini": Seat(
        "gemini",
        "agy",
        f"{GEMINI_MODEL} (Antigravity CLI)",
        _gemini,
        {},
        # The Google sign-in only, never a key: an exported key for another
        # tool would otherwise be billed per call without anyone choosing it.
        drop_env=("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
                  "GOOGLE_GENAI_USE_VERTEXAI", "AGY_ADC_AUTH"),
        min_version=GEMINI_MIN_VERSION,
        encode=_gemini_encode,
        decode=_gemini_decode,
        sign_in=("Sign in once per machine: run `agy` in a terminal of your own, choose "
                 "Sign in with Google (a personal account on Google AI Pro or Ultra), "
                 "then quit. Over SSH it prints a URL; open it anywhere and paste the code back."),
    ),
}

# A CLI that does not know a flag this script passes is older than the seat needs.
UNKNOWN_FLAG = re.compile(
    r"flag provided but not defined|unknown (?:argument|option|flag)|unexpected argument"
    r"|unrecognized (?:argument|option)", re.IGNORECASE)
NOT_SIGNED_IN = re.compile(
    r"authentication required|not (?:logged|signed) in|please (?:log|sign) in"
    r"|manual authorization is required|login required|unauthenticated|\b401\b", re.IGNORECASE)
QUOTA = re.compile(r"\b429\b|resource_exhausted|quota|rate limit", re.IGNORECASE)
BILLING = re.compile(r"\b402\b|credits? (?:depleted|exhausted)|billing", re.IGNORECASE)
# The line that says what went wrong, in preference to the end of the output
# (a CLI that rejects its arguments prints the error first and help after it).
ERROR_LINE = re.compile(
    r"\b(?:error|fatal|failed|failure|denied|refused|forbidden|unauthori[sz]ed|required"
    r"|unknown|not supported|no longer supported|exhausted|depleted|quota)\b", re.IGNORECASE)
LEADING_ERROR = re.compile(r"\W*(?:error|fatal)\b", re.IGNORECASE)
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclass
class Verdict:
    seat: Seat
    ok: bool
    text: str


Runner = Callable[..., subprocess.CompletedProcess]


def consult(seat: Seat, prompt: str, repo: Path, out_dir: Path, timeout: int,
            run: Runner = subprocess.run, which=shutil.which) -> Verdict:
    """Put the prompt to one seat and return its answer or why it has none."""
    exe = find_cli(seat.binary, which)
    if exe is None:
        dirs = ", ".join(EXTRA_BIN_DIRS)
        return Verdict(seat, False, f"`{seat.binary}` is not on PATH or in {dirs}; this seat is empty.")
    answer_path = out_dir / f"{seat.name}.md"
    argv = [exe, *seat.command(answer_path, repo)]
    env = {k: v for k, v in os.environ.items() if k not in seat.drop_env}
    env.update(seat.env)
    env[SEAT_MARKER] = "1"
    # A fresh temp folder sits outside every repository, so no CLI finds a
    # project config by walking up from it - whatever --out is.
    workdir = tempfile.mkdtemp(prefix=f"council-{seat.name}-")
    try:
        stdin = seat.encode(prompt) if seat.encode else prompt
        done = run(argv, input=stdin, cwd=workdir, env=env, capture_output=True,
                   text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return Verdict(seat, False, f"No answer within {timeout} s.")
    except OSError as error:
        return Verdict(seat, False, f"Could not start `{seat.binary}`: {error}")

    error, model = "", ""
    if seat.answer_file and answer_path.exists():
        answer = answer_path.read_text(encoding="utf-8", errors="replace").strip()
    elif seat.decode:
        answer, error, model = seat.decode(done.stdout or "")
        answer = answer.strip()
    else:
        answer = (done.stdout or "").strip()
    if done.returncode != 0 or not answer or error:
        # A decoded error names the failure; the raw stream-json would bury it.
        output = f"{error}\n{done.stderr or ''}" if seat.decode else f"{done.stderr or ''}\n{done.stdout or ''}"
        if seat.fallback is not None and MODEL_REFUSED.search(output):
            verdict = consult(seat.fallback, prompt, repo, out_dir, timeout, run, which)
            refused = seat.label.split(" (")[0]
            verdict.text = f"_`{refused}` was refused by the server; this is the fallback._\n\n{verdict.text}"
            return verdict
        return Verdict(seat, False, explain_failure(seat, done.returncode, output))
    answer_path.write_text(answer + "\n", encoding="utf-8")
    if model:
        answer = f"_Model reported by `{seat.binary}`: {model}._\n\n{answer}"
    return Verdict(seat, True, answer)


def find_cli(binary: str, which=shutil.which) -> str | None:
    """The CLI on PATH, else in a per-user install folder PATH often lacks."""
    found = which(binary)
    if found is not None:
        return found
    for folder in EXTRA_BIN_DIRS:
        found = which(binary, path=os.path.expanduser(folder))
        if found is not None:
            return found
    return None


def error_line(output: str) -> str:
    """The line of the output that says what went wrong, else its last line."""
    lines = [ANSI.sub("", line).strip() for line in output.splitlines()]
    lines = [line for line in lines if line]
    # A known failure first, then a line that leads with "error", then any
    # line naming one: help text printed before the error can mention "error".
    tests = [p.search for p in (UNKNOWN_FLAG, NOT_SIGNED_IN, BILLING, QUOTA)]
    tests += [LEADING_ERROR.match, ERROR_LINE.search]
    for test in tests:
        for line in lines:
            if test(line):
                return line
    return lines[-1] if lines else "(no output)"


def explain_failure(seat: Seat, code: int, output: str) -> str:
    """Say what went wrong and what to do about it, in that order."""
    line = error_line(output)
    if UNKNOWN_FLAG.search(output):
        advice = (f"`{seat.binary}` rejected a flag this script passes: update it to at least "
                  f"version {seat.min_version or 'the latest'}.")
    elif NOT_SIGNED_IN.search(output):
        advice = f"`{seat.binary}` is not signed in. {seat.sign_in}".strip()
    elif BILLING.search(output):
        advice = "The account has run out of paid credits; nothing more is billed until it is topped up."
    elif QUOTA.search(output):
        advice = "The account's usage quota is used up for now; try again after it resets."
    else:
        advice = ""
    text = f"Exited {code} without an answer: {line}"
    tail = "\n".join(ANSI.sub("", output).strip().splitlines()[-8:])
    return f"{text}\n\n{advice}\n\n```\n{tail}\n```" if advice else f"{text}\n\n```\n{tail}\n```"


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
