import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AgentConfigurationTests(unittest.TestCase):
    def load_agent(self, filename):
        with (ROOT / ".codex" / "agents" / filename).open("rb") as handle:
            return tomllib.load(handle)

    def test_only_minimal_work_and_review_agents_are_defined(self):
        agent_files = sorted(path.name for path in (ROOT / ".codex" / "agents").glob("*.toml"))
        self.assertEqual(agent_files, ["review-agent.toml", "work-agent.toml"])
        self.assertEqual(self.load_agent("work-agent.toml")["name"], "work_agent")
        self.assertEqual(self.load_agent("review-agent.toml")["name"], "review_agent")

    def test_agents_select_separate_permission_profiles(self):
        self.assertEqual(
            self.load_agent("review-agent.toml")["default_permissions"], "review-agent"
        )
        self.assertEqual(
            self.load_agent("work-agent.toml")["default_permissions"], "work-agent"
        )

    def test_permission_profiles_allow_only_work_agent_to_write(self):
        with (ROOT / ".codex" / "config.toml").open("rb") as handle:
            config = tomllib.load(handle)
        permissions = config["permissions"]
        self.assertEqual(config["default_permissions"], "main-agent")
        self.assertEqual(permissions["main-agent"]["extends"], ":read-only")
        self.assertEqual(permissions["review-agent"]["extends"], ":read-only")
        self.assertEqual(permissions["work-agent"]["extends"], ":workspace")
        self.assertEqual(permissions["work-agent"]["filesystem"]["glob_scan_max_depth"], 64)
        work_filesystem = permissions["work-agent"]["filesystem"][":workspace_roots"]
        self.assertEqual(work_filesystem["."], "write")
        self.assertEqual(work_filesystem[".git"], "write")
        self.assertEqual(work_filesystem[".codex"], "read")
        self.assertEqual(work_filesystem[".env*"], "deny")
        self.assertEqual(work_filesystem["**/.env*"], "deny")
        review_filesystem = permissions["review-agent"]["filesystem"]
        self.assertEqual(review_filesystem[":tmpdir"], "write")
        self.assertEqual(review_filesystem[":slash_tmp"], "write")

    def test_legacy_sandbox_settings_are_not_mixed_with_permission_profiles(self):
        paths = [ROOT / ".codex" / "config.toml", *(ROOT / ".codex" / "agents").glob("*.toml")]
        for path in paths:
            self.assertNotIn("sandbox_mode", path.read_text(encoding="utf-8"), path)


class WorkflowContractTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_templates_have_workflow_markers_and_required_sections(self):
        issue_template = self.read(".github/ISSUE_TEMPLATE/ai-development-task.yml")
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

    def test_main_prompt_routes_exactly_the_two_named_agents(self):
        prompt = self.read(".codex/prompts/ai-development-loop.md")
        names = set(re.findall(r"`(work_agent|review_agent)`", prompt))
        self.assertEqual(names, {"work_agent", "review_agent"})
        self.assertIn("spawn exactly one", prompt)
        self.assertIn("Never merge it", prompt)
        self.assertIn("every expected CI check", prompt)
        self.assertIn("AWAITING_CI", prompt)

    def test_review_markers_bind_to_mutable_artifacts(self):
        reviewer = self.load_reviewer_instructions()
        self.assertIn("<!-- ai-workflow:issue-review -->", reviewer)
        self.assertIn("issue_hash", reviewer)
        self.assertIn("<!-- ai-workflow:pr-review -->", reviewer)
        self.assertIn("head_sha", reviewer)

    def load_reviewer_instructions(self):
        with (ROOT / ".codex" / "agents" / "review-agent.toml").open("rb") as handle:
            return tomllib.load(handle)["developer_instructions"]


if __name__ == "__main__":
    unittest.main()
