#!/usr/bin/env python3
"""Executable contract for the label-based AI development workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_LABELS = {
    "ai:issue-review",
    "ai:issue-approved",
    "ai:changes-requested",
    "ai:pr-review",
    "ai:human-review",
    "ai:human-action-required",
    "ai:human-action-ready",
    "ai:human-action-cancelled",
}
ESCALATION_LABELS = {
    "ai:human-action-required",
    "ai:human-action-ready",
    "ai:human-action-cancelled",
}
RESUME_TO_ACTIVE = {
    "ai:resume-issue-review": "ai:issue-review",
    "ai:resume-issue-approved": "ai:issue-approved",
    "ai:resume-changes-requested": "ai:changes-requested",
    "ai:resume-pr-review": "ai:pr-review",
}
ACTIVE_TO_RESUME = {
    "ai:issue-review": "ai:resume-issue-review",
    "ai:issue-approved": "ai:resume-issue-approved",
    "ai:pr-review": "ai:resume-pr-review",
}
CONTRACT_FILES = (
    ROOT / "AGENTS.md",
    ROOT / ".codex/agents/work.toml",
    ROOT / ".codex/agents/review.toml",
    ROOT / "docs/ai-development.md",
)


class InvalidState(ValueError):
    """The labels do not identify one safe workflow state."""


def _resume_for(object_type: str, active: str) -> str:
    if active == "ai:changes-requested":
        return "ai:resume-changes-requested"
    resume = ACTIVE_TO_RESUME.get(active)
    if resume is None:
        raise InvalidState(f"{active} cannot enter Human escalation")
    if object_type == "issue" and active == "ai:pr-review":
        raise InvalidState("issue cannot resume PR review")
    if object_type == "pr" and active in {"ai:issue-review", "ai:issue-approved"}:
        raise InvalidState("PR cannot resume an Issue state")
    return resume


def validate_state(object_type: str, labels: set[str]) -> tuple[str, str | None]:
    if object_type not in {"issue", "pr"}:
        raise InvalidState(f"unknown object type: {object_type}")
    active = labels & ACTIVE_LABELS
    if len(active) != 1:
        raise InvalidState(f"expected exactly one active label, got {sorted(active)}")
    state = next(iter(active))
    if object_type == "issue" and state in {"ai:pr-review", "ai:human-review"}:
        raise InvalidState(f"{state} is only valid on a PR")
    if object_type == "pr" and state in {"ai:issue-review", "ai:issue-approved"}:
        raise InvalidState(f"{state} is only valid on an Issue")
    resumes = labels & RESUME_TO_ACTIVE.keys()
    if state in ESCALATION_LABELS:
        if len(resumes) != 1:
            raise InvalidState("an escalation state requires exactly one resume label")
        resume = next(iter(resumes))
        restored = RESUME_TO_ACTIVE[resume]
        _resume_for(object_type, restored)
        return state, resume
    if resumes:
        raise InvalidState("resume metadata is only valid during Human escalation")
    _resume_for(object_type, state) if state != "ai:human-review" else None
    return state, None


def transition(object_type: str, labels: set[str], operation: str) -> set[str]:
    state, resume = validate_state(object_type, labels)
    result = set(labels)
    if operation == "escalate":
        if state in ESCALATION_LABELS or state == "ai:human-review":
            raise InvalidState(f"cannot escalate from {state}")
        result.remove(state)
        result.update({"ai:human-action-required", _resume_for(object_type, state)})
    elif operation == "human_ready":
        if state != "ai:human-action-required":
            raise InvalidState("only a pending Human request can become ready")
        result.remove(state)
        result.add("ai:human-action-ready")
    elif operation == "verify_success":
        if state != "ai:human-action-ready" or resume is None:
            raise InvalidState("successful verification requires ready state and resume metadata")
        result.remove(state)
        result.remove(resume)
        result.add(RESUME_TO_ACTIVE[resume])
    elif operation == "verify_failure":
        if state != "ai:human-action-ready":
            raise InvalidState("failed verification requires ready state")
        result.remove(state)
        result.add("ai:human-action-required")
    elif operation == "cancel":
        if state not in {"ai:human-action-required", "ai:human-action-ready"}:
            raise InvalidState("only a pending escalation can be cancelled")
        result.remove(state)
        result.add("ai:human-action-cancelled")
    else:
        raise InvalidState(f"unknown operation: {operation}")
    validate_state(object_type, result)
    return result


def route(object_type: str, labels: set[str], *, ci: str = "success") -> str | None:
    state, _ = validate_state(object_type, labels)
    if state in {"ai:human-action-required", "ai:human-action-cancelled"}:
        return None
    if state == "ai:human-action-ready":
        return "work:verify_escalation"
    if state == "ai:human-review":
        return "main:merge_if_human_approved" if object_type == "pr" else None
    if state == "ai:changes-requested":
        return f"work:revise_{object_type}"
    if state == "ai:issue-approved":
        return "work:implement_issue"
    if state == "ai:issue-review":
        return "review:issue"
    if state == "ai:pr-review":
        if ci == "pending":
            return None
        return "work:fix_ci" if ci == "failure" else "review:pr"
    raise InvalidState(f"no routing contract for {state}")


def validate_repository_contract() -> None:
    label_config = json.loads((ROOT / ".github/ai-workflow-labels.json").read_text())
    expected = ESCALATION_LABELS | set(RESUME_TO_ACTIVE)
    if set(label_config) != expected:
        raise AssertionError("label config and executable escalation contract differ")
    for label in ESCALATION_LABELS:
        if label_config[label]["kind"] != "active":
            raise AssertionError(f"{label} must be identified as active")
    for label in RESUME_TO_ACTIVE:
        if label_config[label]["kind"] != "resume-metadata":
            raise AssertionError(f"{label} must be identified as resume metadata")
    for path in CONTRACT_FILES:
        content = path.read_text(encoding="utf-8")
        missing = sorted(label for label in expected if label not in content)
        if missing:
            raise AssertionError(f"{path.relative_to(ROOT)} lacks labels: {missing}")


def validate_fixtures(path: Path) -> None:
    fixtures = json.loads(path.read_text(encoding="utf-8"))
    for case in fixtures:
        labels = set(case["labels"])
        try:
            if "operation" in case:
                actual_labels = transition(case["object_type"], labels, case["operation"])
                if actual_labels != set(case["expected_labels"]):
                    raise AssertionError(f"labels {sorted(actual_labels)}")
            actual_route = route(
                case["object_type"],
                set(case.get("expected_labels", case["labels"])),
                ci=case.get("ci", "success"),
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
    fixture_path = ROOT / "tests/fixtures/ai_workflow_transitions.json"
    validate_repository_contract()
    validate_fixtures(fixture_path)
    print(f"validated Human escalation contract and {len(json.loads(fixture_path.read_text()))} fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
