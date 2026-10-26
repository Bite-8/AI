import unittest
from pathlib import Path

from scripts.ai_workflow_contract import (
    ROOT,
    InvalidState,
    route,
    validate_fixtures,
    validate_repository_contract,
)


class WorkflowContractTests(unittest.TestCase):
    def test_repository_contract_is_synchronized(self):
        validate_repository_contract()

    def test_routing_fixtures(self):
        validate_fixtures(ROOT / "tests/fixtures/ai_workflow_routing.json")

    def test_priority_label_does_not_change_routing(self):
        regular = route("issue", {"ai:issue-review"})
        urgent = route("issue", {"ai:issue-review", "priority:urgent"})
        self.assertEqual(regular, urgent)

    def test_invalid_state_is_not_routed(self):
        with self.assertRaises(InvalidState):
            route("issue", {"ai:issue-review", "ai:changes-requested"})


if __name__ == "__main__":
    unittest.main()
