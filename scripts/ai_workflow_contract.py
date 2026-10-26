#!/usr/bin/env python3
"""Executable contract for the label-based AI development workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_LABELS = {
    "ai:issue-review",
    "ai:issue-approved",
    "ai:changes-requested",
    "ai:pr-review",
    "ai:human-review",
}
PRIORITY_LABELS = {"priority:urgent"}
VALID_OBJECT_TYPES = {"issue", "pr"}
CONTRACT_FILES = {
    ROOT / "AGENTS.md": ACTIVE_LABELS | PRIORITY_LABELS,
    ROOT / ".codex/agents/work.toml": ACTIVE_LABELS - {"ai:human-review"} | PRIORITY_LABELS,
    ROOT / ".codex/agents/review.toml": ACTIVE_LABELS | PRIORITY_LABELS,
    ROOT / "docs/ai-development.md": ACTIVE_LABELS | PRIORITY_LABELS,
}
OUTCOME_CONTRACT_FILES = {
    ROOT / "AGENTS.md": {"成果形態", "Issue記録", "Outcome: failed"},
    ROOT / ".codex/agents/work.toml": {
        "成果形態",
        "Issue記録",
        "Outcome: succeeded",
        "Outcome: failed",
    },
    ROOT / ".codex/agents/review.toml": {"成果形態", "Issue記録", "Close Comment"},
    ROOT / "docs/ai-development.md": {"成果形態", "Issue記録", "Outcome: failed"},
    ROOT / ".github/ISSUE_TEMPLATE/ai-development.yml": {"成果形態", "PR", "Issue記録"},
}


class InvalidState(ValueError):
    """The labels do not identify one safe workflow state."""


def validate_state(object_type: str, labels: set[str]) -> str:
    if object_type not in VALID_OBJECT_TYPES:
        raise InvalidState(f"unknown object type: {object_type}")
    active = labels & ACTIVE_LABELS
    if len(active) != 1:
        raise InvalidState(f"expected exactly one active label, got {sorted(active)}")
    state = next(iter(active))
    if object_type == "issue" and state in {"ai:pr-review", "ai:human-review"}:
        raise InvalidState(f"{state} is only valid on a PR")
    if object_type == "pr" and state in {"ai:issue-review", "ai:issue-approved"}:
        raise InvalidState(f"{state} is only valid on an Issue")
    return state


def route(
    object_type: str,
    labels: set[str],
    *,
    ci: str = "success",
    actionable: bool = True,
) -> str | None:
    """Return the next action after contextual feasibility has been assessed."""
    state = validate_state(object_type, labels)
    if not actionable:
        return None
    if state == "ai:human-review":
        return "main:merge_if_human_approved"
    if state == "ai:changes-requested":
        return f"work:revise_{object_type}"
    if state == "ai:issue-approved":
        return "work:implement_issue"
    if state == "ai:issue-review":
        return "review:issue"
    if state == "ai:pr-review":
        if ci == "pending":
            return None
        if ci == "failure":
            return "work:fix_ci"
        if ci == "success":
            return "review:pr"
        raise InvalidState(f"unknown CI state: {ci}")
    raise InvalidState(f"no routing contract for {state}")


def select_candidate(candidates: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Select the first routable candidate from an already priority-ordered queue."""
    for candidate in candidates:
        next_action = route(
            candidate["object_type"],
            set(candidate["labels"]),
            ci=candidate.get("ci", "success"),
            actionable=candidate.get("actionable", True),
        )
        if next_action is not None:
            return str(candidate["id"]), next_action
    return None


def validate_repository_contract() -> None:
    label_config = json.loads((ROOT / ".github/ai-workflow-labels.json").read_text())
    expected = ACTIVE_LABELS | PRIORITY_LABELS
    if set(label_config) != expected:
        raise AssertionError("label config and executable workflow contract differ")
    for label in ACTIVE_LABELS:
        if label_config[label]["kind"] != "active":
            raise AssertionError(f"{label} must be identified as active")
    for label in PRIORITY_LABELS:
        if label_config[label]["kind"] != "priority":
            raise AssertionError(f"{label} must be identified as priority")
    for label, definition in label_config.items():
        object_types = set(definition.get("object_types", []))
        if not object_types or not object_types <= VALID_OBJECT_TYPES:
            raise AssertionError(f"{label} has invalid object types")
    for path, required_labels in CONTRACT_FILES.items():
        content = path.read_text(encoding="utf-8")
        missing = sorted(label for label in required_labels if label not in content)
        if missing:
            raise AssertionError(f"{path.relative_to(ROOT)} lacks labels: {missing}")
    for path, required_terms in OUTCOME_CONTRACT_FILES.items():
        content = path.read_text(encoding="utf-8")
        missing = sorted(term for term in required_terms if term not in content)
        if missing:
            raise AssertionError(f"{path.relative_to(ROOT)} lacks outcome contract terms: {missing}")


def validate_fixtures(path: Path) -> None:
    fixtures = json.loads(path.read_text(encoding="utf-8"))
    for case in fixtures:
        try:
            if "candidates" in case:
                actual = select_candidate(case["candidates"])
                expected = case.get("expected_selection")
                expected_selection = tuple(expected) if expected is not None else None
                if actual != expected_selection:
                    raise AssertionError(f"selection {actual!r}")
            else:
                actual_route = route(
                    case["object_type"],
                    set(case["labels"]),
                    ci=case.get("ci", "success"),
                    actionable=case.get("actionable", True),
                )
                if case.get("invalid", False):
                    raise AssertionError("expected InvalidState")
                if actual_route != case.get("expected_route"):
                    raise AssertionError(f"route {actual_route!r}")
        except InvalidState:
            if not case.get("invalid", False):
                raise
        except AssertionError as error:
            raise AssertionError(f"fixture {case['name']}: {error}") from error


def main() -> int:
    fixture_path = ROOT / "tests/fixtures/ai_workflow_routing.json"
    validate_repository_contract()
    validate_fixtures(fixture_path)
    print(f"validated AI workflow routing contract and {len(json.loads(fixture_path.read_text()))} fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
