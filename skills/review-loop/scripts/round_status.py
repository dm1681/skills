#!/usr/bin/env python3
"""Report one review round's state: the gate, and each surface's verdict.

The fetching is deterministic and the correlation rules are fiddly enough
that hand-written variants keep getting them wrong — an ad-hoc version of
this script written while building the skill shipped two of the defects the
rules below exist to prevent. Deciding what a verdict *means* stays with the
agent; this only gathers and correlates.

Standard library only, so the skill stays self-contained.

    python3 round_status.py --pr 28 --surface 'chatgpt-codex-connector[bot]'
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def gh_json(args: list, paginate: bool = True) -> list:
    """Run a `gh api` call and return its rows.

    `--paginate` streams one JSON array per page rather than a single merged
    array, so the pages are flattened here. Counting or slicing without this
    silently sees only the first page — the failure mode behind several
    review findings against this skill.
    """
    command = ["gh", "api"]
    if paginate:
        command.append("--paginate")
    command.append("--jq")
    command.append(".[]")
    command.extend(args)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh api failed")
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def select_review(reviews: list, head: str, bot: str) -> dict:
    """This surface's most recent review of this exact head, or {}.

    Both filters are load-bearing. Matching on `commit_id` alone lets a human
    or another bot who reviewed the same head stand in as this surface's
    verdict — including the review objects that in-thread replies create.
    """
    matching = [
        review
        for review in reviews
        if review.get("commit_id") == head
        and (review.get("user") or {}).get("login") == bot
    ]
    return matching[-1] if matching else {}


def findings_for(comments: list, review_id) -> list:
    """Inline comments belonging to one review.

    Correlating by review id rather than by head keeps an earlier round's
    findings from dirtying a clean current review.
    """
    if not review_id:
        return []
    return [
        comment
        for comment in comments
        if comment.get("pull_request_review_id") == review_id
    ]


def gate_failed(checks: list) -> list:
    """Names of failing checks. Empty means the gate is passing."""
    failing = ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE")
    return [
        check.get("name") or check.get("context") or "?"
        for check in checks
        if (check.get("conclusion") or check.get("state") or "").upper() in failing
    ]


def surface_state(review: dict, findings: list) -> str:
    """How far this surface got — never whether its verdict is acceptable.

    `reported` means the surface spoke for this head; the agent still reads
    the body, because an empty review is not evidence of a clean one.
    """
    if not review:
        return "awaiting"
    return "reported-with-findings" if findings else "reported-empty"


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", required=True, help="pull request number")
    parser.add_argument("--repo", help="owner/name (default: current repo)")
    parser.add_argument(
        "--surface",
        action="append",
        default=[],
        metavar="BOT_LOGIN",
        help="a reviewer's login, repeatable",
    )
    args = parser.parse_args(argv)

    repo = args.repo
    if not repo:
        probe = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            print("could not resolve the repository; pass --repo", file=sys.stderr)
            return 2
        repo = probe.stdout.strip()

    view = subprocess.run(
        [
            "gh", "pr", "view", args.pr, "--repo", repo,
            "--json", "headRefOid,baseRefName,state,statusCheckRollup",
        ],
        capture_output=True,
        text=True,
    )
    if view.returncode != 0:
        print(view.stderr.strip(), file=sys.stderr)
        return 2
    pull = json.loads(view.stdout)
    head = pull["headRefOid"]

    reviews = gh_json(["repos/%s/pulls/%s/reviews" % (repo, args.pr)])
    comments = gh_json(["repos/%s/pulls/%s/comments" % (repo, args.pr)])

    surfaces = {}
    for bot in args.surface:
        review = select_review(reviews, head, bot)
        findings = findings_for(comments, review.get("id"))
        surfaces[bot] = {
            "state": surface_state(review, findings),
            "review_id": review.get("id"),
            "findings": len(findings),
            "paths": sorted({finding.get("path") for finding in findings if finding.get("path")}),
        }

    failing = gate_failed(pull.get("statusCheckRollup") or [])
    print(json.dumps(
        {
            "head": head,
            "base": pull.get("baseRefName"),
            "pr_state": pull.get("state"),
            "gate": "fail" if failing else "pass",
            "gate_failing": failing,
            "surfaces": surfaces,
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
