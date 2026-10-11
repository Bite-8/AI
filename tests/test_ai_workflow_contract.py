import unittest
from pathlib import Path

from scripts.ai_workflow_contract import (
    ROOT,
    InvalidState,
    route,
    transition,
    validate_fixtures,
    validate_repository_contract,
)


class HumanEscalationContractTests(unittest.TestCase):
    def test_repository_contract_is_synchronized(self):
        validate_repository_contract()

    def test_transition_fixtures(self):
        validate_fixtures(ROOT / "tests/fixtures/ai_workflow_transitions.json")

    def test_priority_labels_survive_every_transition(self):
        labels = {"ai:issue-approved", "priority:urgent"}
        for operation in ("escalate", "human_ready", "verify_failure", "human_ready", "verify_success"):
            labels = transition("issue", labels, operation)
            self.assertIn("priority:urgent", labels)

    def test_invalid_state_is_not_routed(self):
        with self.assertRaises(InvalidState):
            route("issue", {"ai:human-action-ready"})


if __name__ == "__main__":
    unittest.main()
