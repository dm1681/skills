"""Bounded, local task routing; no extra model turns or tracker requests."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

PROFILES = {
    "simple": ("gpt-6-luna", "low"),
    "standard": ("gpt-6-sol", "medium"),
    "complex": ("gpt-6-astra", "high"),
}
COMPLEX = re.compile(r"\b(security|sandbox|authentication|authorization|cryptograph\w*|architect\w*|concurren\w*|race condition|distributed|migration|deadlock|data loss|durable output)\b", re.I)
SIMPLE = re.compile(r"^(?:fix\s+(?:a\s+)?typo|docs?\b|document\b|correct\s+spelling|update\s+(?:the\s+)?readme|format\b|rename\b)", re.I)
BLOCKED = re.compile(r"permission|read.only|rate.limit|quota|credential|authenticat|network|unavailable|missing tool", re.I)


def validate_catalog(rows: list[dict]) -> None:
    available = {row.get("model"): {item.get("reasoningEffort") for item in row.get("supportedReasoningEfforts", [])} for row in rows}
    missing = [f"{model}/{effort}" for model, effort in PROFILES.values() if effort not in available.get(model, set())]
    if missing:
        raise ValueError("Dynamic routing requires available Codex profiles: " + ", ".join(missing))


def assess(text: str) -> dict:
    # Restrict rules to the issue block, excluding the shared workflow instructions.
    match = re.search(r"Issue context:\s*\nIdentifier: ([^\n]+)\nTitle: ([^\n]+)\nCurrent status: [^\n]+\nLabels: ([^\n]*)\nURL: [^\n]*\n\nDescription:\n(.*?)\nInstructions:", text, re.S)
    if not match:
        return {"profile": "standard", "reason": "Issue context unavailable; conservative standard default", "override": False}
    _, title, labels, description = match.groups()
    overrides = set(re.findall(r"(?<![\w:-])symphony:(simple|standard|complex)(?![\w:-])", labels))
    if len(overrides) > 1:
        raise ValueError("Conflicting Symphony model labels; choose exactly one")
    if overrides:
        profile = overrides.pop()
        return {"profile": profile, "reason": "Explicit Linear label symphony:" + profile, "override": True}
    description = description.split("## Context and execution boundaries", 1)[0].split("## Handoff", 1)[0]
    if COMPLEX.search(title + "\n" + description):
        return {"profile": "complex", "reason": "Issue includes architecture, security, concurrency or data-integrity work", "override": False}
    if SIMPLE.search(title.strip()):
        return {"profile": "simple", "reason": "Narrow documentation, spelling, formatting or rename task", "override": False}
    return {"profile": "standard", "reason": "Ordinary implementation or debugging; no narrow/simple or complex signal", "override": False}


def read_record(path: Path) -> dict | None:
    if path.is_symlink():
        raise ValueError("Routing records must not be symlinks")
    if not path.exists():
        return None
    if path.stat().st_size > 8192:
        raise ValueError("Routing record exceeds size limit")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Routing record must be an object")
    return value


class Router:
    """Persist the decision outside disposable clones; allow one bounded promotion."""
    def __init__(self, project: Path, cwd: Path):
        directory = project / ".symphony" / "model-routing"
        if directory.is_symlink() or (project / ".symphony").is_symlink():
            raise ValueError("Routing directory must be project-local")
        directory.mkdir(exist_ok=True)
        self.path = directory / (cwd.name + ".json")
        self.request_path = cwd / ".git" / "symphony-model-escalation.json"
        self.state = read_record(self.path)
        if self.state is not None:
            if (self.state.get("profile") not in PROFILES or
                    type(self.state.get("escalations")) is not int or self.state["escalations"] not in (0, 1) or
                    type(self.state.get("override")) is not bool or not isinstance(self.state.get("reason"), str)):
                raise ValueError("Invalid saved routing decision")
        self.first = True

    def apply(self, params: dict) -> None:
        inputs = params.get("input")
        if not isinstance(inputs, list):
            raise ValueError("Model routing requires turn input")
        if self.first:
            text = "\n".join(item.get("text", "") for item in inputs if item.get("type") == "text")
            decision = assess(text)
            if self.state is None or decision["override"] or self.state["override"]:
                self.state = {**decision, "escalations": 0 if self.state is None else self.state["escalations"]}
            self.first = False
        request = read_record(self.request_path)
        if request is not None:
            reason = request.get("reason", "")
            eligible = (request.get("category") == "complexity" and isinstance(reason, str) and
                        10 <= len(reason) <= 500 and not BLOCKED.search(reason))
            if eligible and not self.state["override"] and self.state["escalations"] == 0 and self.state["profile"] != "complex":
                self.state["profile"] = "standard" if self.state["profile"] == "simple" else "complex"
                self.state["reason"] = "Worker requested complexity escalation: " + reason
                self.state["escalations"] = 1
            self.request_path.unlink()
        model, effort = PROFILES[self.state["profile"]]
        self.state.update(model=model, effort=effort)
        # Unique files avoid leaving a crash-created lock that blocks future pickups.
        with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, prefix=self.path.stem + "-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(self.state, indent=2) + "\n")
        try:
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        params.update(model=model, effort=effort)
        inputs.append({"type": "text", "text": (
            "Symphony model selection: " + json.dumps(self.state) + ". Record this model, effort and reason in the existing Codex Workpad. "
            "For demonstrated technical complexity, request at most one profile promotion by writing "
            '.git/symphony-model-escalation.json as {"category":"complexity","reason":"specific technical evidence"}. '
            "It takes effect on the next turn; continue normally until then. Explicit label overrides are fixed. "
            "Never request escalation for permissions, authentication, unavailable tools, network errors or rate limits. "
            "The cap is one promotion per issue, up to Astra/high; normal Symphony turn limits still apply."
        )})
