import json
import tempfile
import unittest
from pathlib import Path

from mark2 import run
from mark2.config import read_config, validate_config


class ConfigTests(unittest.TestCase):
    def test_default_contract_is_valid_and_immutable(self):
        config = read_config(run.DEFAULT_CONFIG)
        self.assertEqual(run.DEFAULT_CONFIG.name, "qwen35_9b_mmlu.json")
        self.assertEqual(config["model"]["id"], "Qwen/Qwen3.5-9B")
        self.assertEqual(config["model"]["revision"], "c202236235762e1c871ad0ccb60c8ee5ba337b9a")
        self.assertEqual(len(config["model"]["revision"]), 40)
        self.assertEqual(len(config["dataset"]["revision"]), 40)
        self.assertFalse(config["generation"]["do_sample"])
        self.assertIsNone(config["model"]["quantization"])

    def test_mutable_revision_and_precision_drift_are_rejected(self):
        config = read_config(run.DEFAULT_CONFIG)
        config["model"]["revision"] = "main"
        with self.assertRaisesRegex(ValueError, "commit SHA"):
            validate_config(config)
        config = read_config(run.DEFAULT_CONFIG)
        config["model"]["dtype"] = "float16"
        with self.assertRaisesRegex(ValueError, "bfloat16"):
            validate_config(config)

    def test_answer_parser_does_not_accept_embedded_letters(self):
        self.assertEqual(run.parse_answer("Answer: c"), "C")
        self.assertIsNone(run.parse_answer("CAB"))
        self.assertIsNone(run.parse_answer("unknown"))


class ArtifactTests(unittest.TestCase):
    def test_mock_runs_are_separate_and_compare_reproducibly(self):
        config = read_config(run.DEFAULT_CONFIG)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = run.execute_run(config, run.DEFAULT_CONFIG, root, "first", run.MockBackend())
            second = run.execute_run(config, run.DEFAULT_CONFIG, root, "second", run.MockBackend())
            self.assertNotEqual(first, second)
            result = run.compare_runs(first, second)
            self.assertTrue(result["reproducible"])
            manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["metrics"]["accuracy"], 1.0)
            self.assertEqual(manifest["result_classification"], "mock-only")

    def test_existing_run_is_never_overwritten(self):
        config = read_config(run.DEFAULT_CONFIG)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run.execute_run(config, run.DEFAULT_CONFIG, root, "same", run.MockBackend())
            with self.assertRaises(FileExistsError):
                run.execute_run(config, run.DEFAULT_CONFIG, root, "same", run.MockBackend())

    def test_failure_is_recorded(self):
        class FailureBackend:
            name = "failure-test"

            def run(self, config, manifest, run_dir):
                manifest["partial_marker"] = True
                raise RuntimeError("simulated")

        config = read_config(run.DEFAULT_CONFIG)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                run.execute_run(config, run.DEFAULT_CONFIG, root, "failed", FailureBackend())
            manifest = json.loads((root / "failed" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["error"]["type"], "RuntimeError")
            self.assertTrue(manifest["partial_marker"])


if __name__ == "__main__":
    unittest.main()
