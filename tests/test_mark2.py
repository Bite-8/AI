import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from mark2 import run
from mark2.config import read_config, validate_config
from mark2.environment import evaluate_preflight, read_profile


EXPECTED_COMMIT = "a" * 40


class FakeProbe:
    def __init__(self, **overrides):
        self.values = {
            "git_commit": EXPECTED_COMMIT,
            "git_tracked_status": "",
            "python_version": [3, 10, 14],
            "packages": {
                "accelerate": "1.15.0",
                "datasets": "5.0.1",
                "safetensors": "0.8.0",
                "torch": "2.14.0",
                "transformers": "5.17.0",
            },
            "disk_free_bytes": 200 * 1024**3,
            "accelerator": {
                "cuda_available": True,
                "bf16_supported": True,
                "gpu_count": 1,
                "gpus": [{"name": "NVIDIA L4", "memory_total_mib": 23034}],
            },
        }
        self.values.update(overrides)

    def snapshot(self):
        return deepcopy(self.values)


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


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.profile = read_profile(run.DEFAULT_PROFILE)

    def test_approved_host_passes_with_machine_readable_checks(self):
        result = evaluate_preflight(self.profile, EXPECTED_COMMIT, FakeProbe())
        self.assertTrue(result["passed"])
        self.assertTrue(result["checks"])
        self.assertTrue(all({"name", "expected", "actual", "passed", "reason"} == set(item) for item in result["checks"]))

    def test_profile_dependency_pins_match_requirements(self):
        requirements = {}
        for line in (run.PACKAGE_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines():
            name, version = line.split("==", 1)
            requirements[name] = version
        self.assertEqual(self.profile["packages"], requirements)

    def test_each_host_contract_mismatch_is_rejected(self):
        cases = {
            "git_commit": {"git_commit": "b" * 40},
            "git_tracked_files_clean": {"git_tracked_status": " M mark2/run.py"},
            "python_version": {"python_version": [3, 9, 20]},
            "package:torch": {"packages": {**FakeProbe().values["packages"], "torch": "0.0.0"}},
            "cuda_available": {"accelerator": {"cuda_available": False, "bf16_supported": False, "gpu_count": 0, "gpus": []}},
            "bf16_supported": {"accelerator": {"cuda_available": True, "bf16_supported": False, "gpu_count": 1, "gpus": [{"name": "NVIDIA L4", "memory_total_mib": 23034}]}},
            "gpu_count": {"accelerator": {"cuda_available": True, "bf16_supported": True, "gpu_count": 2, "gpus": [{"name": "NVIDIA L4", "memory_total_mib": 23034}] * 2}},
            "gpu_name": {"accelerator": {"cuda_available": True, "bf16_supported": True, "gpu_count": 1, "gpus": [{"name": "Different GPU", "memory_total_mib": 23034}]}},
            "gpu_memory_total_mib": {"accelerator": {"cuda_available": True, "bf16_supported": True, "gpu_count": 1, "gpus": [{"name": "NVIDIA L4", "memory_total_mib": 20000}]}},
            "disk_free_bytes": {"disk_free_bytes": 99 * 1024**3},
        }
        for expected_failure, override in cases.items():
            with self.subTest(expected_failure=expected_failure):
                result = evaluate_preflight(self.profile, EXPECTED_COMMIT, FakeProbe(**override))
                self.assertFalse(result["passed"])
                failures = {item["name"] for item in result["checks"] if not item["passed"]}
                self.assertIn(expected_failure, failures)

    def test_failed_preflights_are_saved_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, result = run.execute_preflight(
                run.DEFAULT_PROFILE,
                EXPECTED_COMMIT,
                root,
                "failed-preflight",
                FakeProbe(disk_free_bytes=0),
            )
            self.assertFalse(result["passed"])
            self.assertFalse(json.loads(path.read_text(encoding="utf-8"))["passed"])
            with self.assertRaises(FileExistsError):
                run.execute_preflight(
                    run.DEFAULT_PROFILE, EXPECTED_COMMIT, root, "failed-preflight", FakeProbe()
                )

    def test_transformers_run_stops_before_backend_loader_on_failure(self):
        class LoaderBackend:
            name = "transformers"

            def __init__(self):
                self.called = False

            def run(self, config, manifest, run_dir):
                self.called = True
                raise AssertionError("loader must not be reached")

        backend = LoaderBackend()
        config = read_config(run.DEFAULT_CONFIG)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(RuntimeError, "host preflight failed"):
                run.execute_run(
                    config,
                    run.DEFAULT_CONFIG,
                    root,
                    "gated",
                    backend,
                    expected_commit=EXPECTED_COMMIT,
                    preflight_probe=FakeProbe(accelerator={"cuda_available": False, "bf16_supported": False, "gpu_count": 0, "gpus": []}),
                )
            self.assertFalse(backend.called)
            report = json.loads((root / "gated" / "preflight.json").read_text(encoding="utf-8"))
            manifest = json.loads((root / "gated" / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(report["passed"])
            self.assertEqual(manifest["status"], "failed")


class TransformersBackendTests(unittest.TestCase):
    def test_text_prompt_uses_chat_template_without_vision_content(self):
        class FakeTokenizer:
            def apply_chat_template(self, messages, **kwargs):
                self.messages = messages
                self.kwargs = kwargs
                return {"input_ids": "tokenized"}

        tokenizer = FakeTokenizer()
        result = run.tokenize_prompt(tokenizer, "question")
        self.assertEqual(tokenizer.messages, [{"role": "user", "content": "question"}])
        self.assertEqual(
            tokenizer.kwargs,
            {
                "tokenize": True,
                "add_generation_prompt": True,
                "return_dict": True,
                "return_tensors": "pt",
                "enable_thinking": False,
            },
        )
        self.assertEqual(result, {"input_ids": "tokenized"})

    def test_text_only_runner_imports_tokenizer_without_vision_processor(self):
        class FakeTorch:
            class cuda:
                @staticmethod
                def is_available():
                    return False

        fake_modules = {
            "torch": FakeTorch,
            "datasets": type("FakeDatasets", (), {"load_dataset": None}),
            "transformers": type(
                "FakeTransformers",
                (),
                {
                    "AutoModelForMultimodalLM": object,
                    "AutoTokenizer": object,
                },
            ),
        }
        config = read_config(run.DEFAULT_CONFIG)
        with tempfile.TemporaryDirectory() as folder, patch.dict("sys.modules", fake_modules):
            with self.assertRaisesRegex(RuntimeError, "CUDA is required"):
                run.TransformersBackend().run(config, {}, Path(folder))


if __name__ == "__main__":
    unittest.main()
