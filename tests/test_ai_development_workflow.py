import os
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AgentConfigurationTests(unittest.TestCase):
    def load_agent(self, filename):
        with (ROOT / ".codex" / "agents" / filename).open("rb") as handle:
            return tomllib.load(handle)

    def test_only_work_and_review_agents_are_defined(self):
        agent_files = sorted(path.name for path in (ROOT / ".codex" / "agents").glob("*.toml"))
        self.assertEqual(agent_files, ["review-agent.toml", "work-agent.toml"])
        self.assertEqual(self.load_agent("work-agent.toml")["name"], "work_agent")
        self.assertEqual(self.load_agent("review-agent.toml")["name"], "review_agent")

    def test_agent_instructions_are_japanese_and_roles_are_complete(self):
        work = self.load_agent("work-agent.toml")["developer_instructions"]
        review = self.load_agent("review-agent.toml")["developer_instructions"]
        for phase in ("ISSUE_CREATE", "IMPLEMENT", "PR_REVISE"):
            self.assertIn(phase, work)
        for phase in ("ISSUE_REVIEW", "PR_REVIEW"):
            self.assertIn(phase, review)
        self.assertIn("あなたは", work)
        self.assertIn("あなたは", review)

    def test_agents_use_separate_permission_profiles(self):
        self.assertEqual(
            self.load_agent("review-agent.toml")["default_permissions"], "review-agent"
        )
        self.assertEqual(
            self.load_agent("work-agent.toml")["default_permissions"], "work-agent"
        )


class WorkflowContractTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_templates_have_markers_and_required_sections(self):
        issue_path = ROOT / ".github/ISSUE_TEMPLATE/autonomous-development.yml"
        self.assertTrue(issue_path.is_file())
        self.assertFalse(
            (ROOT / ".github/ISSUE_TEMPLATE/ai-development-task.yml").exists()
        )
        issue_template = issue_path.read_text(encoding="utf-8")
        self.assertIn("<!-- ai-workflow:task -->", issue_template)
        self.assertIn("- codex", issue_template)
        for section in (
            "背景",
            "GOALとの関係",
            "現状",
            "解決すべき差分",
            "実施内容",
            "Scope",
            "Out of Scope",
            "完了条件",
            "検証方法",
            "関連ファイル・Issue",
        ):
            self.assertIn(section, issue_template)

        pr_template = self.read(".github/pull_request_template.md")
        self.assertIn("<!-- ai-workflow:pr -->", pr_template)
        for section in (
            "対応Issue",
            "変更目的",
            "変更内容",
            "GOALへの寄与",
            "実装上の判断",
            "Test・検証結果",
            "影響範囲",
            "Known limitations",
            "Reviewerが重点的に確認する箇所",
        ):
            self.assertIn(section, pr_template)

    def test_main_prompt_is_a_thin_japanese_router(self):
        prompt = self.read(".codex/prompts/ai-development-loop.md")
        self.assertIn("work_agent", prompt)
        self.assertIn("review_agent", prompt)
        self.assertIn("1つだけ", prompt)
        self.assertIn("Agentはmergeしない", prompt)
        self.assertNotIn("/approve-issue", prompt)
        self.assertNotIn("AWAITING_CI", prompt)

    def test_review_markers_bind_to_mutable_artifacts(self):
        reviewer = self.load_agent_instructions("review-agent.toml")
        self.assertIn("<!-- ai-workflow:issue-review -->", reviewer)
        self.assertIn("issue_hash", reviewer)
        self.assertIn("<!-- ai-workflow:pr-review -->", reviewer)
        self.assertIn("head_sha", reviewer)

    def test_entrypoint_and_scheduler_are_present(self):
        script = ROOT / "scripts/run-ai-development.sh"
        self.assertTrue(os.access(script, os.X_OK))
        script_text = script.read_text(encoding="utf-8")
        self.assertIn("flock -n", script_text)
        self.assertIn("AI_DEVELOPMENT_LOG_DIR", script_text)
        self.assertIn("codex exec --strict-config", script_text)
        service = self.read("scheduler/systemd/ai-development.service")
        timer = self.read("scheduler/systemd/ai-development.timer")
        self.assertIn("scripts/run-ai-development.sh", service)
        self.assertIn("OnCalendar=hourly", timer)

    def test_no_new_github_actions_workflow_is_added(self):
        self.assertFalse((ROOT / ".github/workflows/ci.yml").exists())
        runbook = self.read("docs/development/ai-development-workflow.md")
        self.assertIn("branch protectionとCODEOWNERSへ委ねる", runbook)
        self.assertIn("CI gateは追加しない", runbook)

    def load_agent_instructions(self, filename):
        with (ROOT / ".codex" / "agents" / filename).open("rb") as handle:
            return tomllib.load(handle)["developer_instructions"]


if __name__ == "__main__":
    unittest.main()
