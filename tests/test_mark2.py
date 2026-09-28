import json
import hashlib
import io
import shutil
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from mark2 import run
from mark2.config import read_config, validate_config
from mark2.environment import evaluate_preflight, read_profile


EXPECTED_COMMIT = "a" * 40


def make_measured_artifact(path, run_id):
    path.mkdir()
    config = read_config(run.DEFAULT_CONFIG)
    shutil.copyfile(run.DEFAULT_CONFIG, path / "contract.json")
    (path / "chat_template.txt").write_text("fixed template", encoding="utf-8")
    model_config = {"model_type": "qwen3_5"}
    run.write_json(path / "model_config.json", model_config)
    source_dir = path / "source"
    source_dir.mkdir()
    (source_dir / "run.py").write_text("pinned source", encoding="utf-8")
    source_hashes = {"run.py": hashlib.sha256((source_dir / "run.py").read_bytes()).hexdigest()}
    rows = []
    for index in range(config["dataset"]["sample_size"]):
        rows.append(
            {
                "question_sha256": hashlib.sha256(f"question-{index}".encode()).hexdigest(),
                "subject": "fixture",
                "target": "A",
                "prediction": "A",
                "correct": True,
                "output_text": "Answer: A",
                "generation_seconds": 0.1,
                "index": index,
                "input_tokens": 10,
                "output_tokens": 2,
            }
        )
    with (path / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    question_hashes = [row["question_sha256"] for row in rows]
    profile = read_profile(run.DEFAULT_PROFILE)
    preflight = evaluate_preflight(profile, EXPECTED_COMMIT, FakeProbe())
    run.write_json(path / "preflight.json", preflight)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "completed",
        "backend": "transformers",
        "result_classification": "repository-measured",
        "contract_sha256": run.sha256_json(config),
        "contract": config,
        "git_commit": EXPECTED_COMMIT,
        "git_status": "",
        "environment": {},
        "source_sha256": source_hashes,
        "dataset_selection": {
            "count": len(rows),
            "question_hashes": question_hashes,
            "sha256": hashlib.sha256("\n".join(question_hashes).encode("ascii")).hexdigest(),
        },
        "chat_template_sha256": hashlib.sha256(b"fixed template").hexdigest(),
        "model_config_sha256": run.sha256_json(model_config),
        "runtime": {"backend": "transformers"},
        "metrics": run.aggregate(rows),
        "preflight": {"passed": True, "report": "preflight.json", "profile": str(run.DEFAULT_PROFILE)},
    }
    run.write_json(path / "manifest.json", manifest)


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

    def test_repository_measured_runs_are_qualified_with_complete_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "first", root / "second"
            make_measured_artifact(first, "first")
            make_measured_artifact(second, "second")
            result = run.qualify_baseline_runs(first, second)
            self.assertTrue(result["eligible"])
            self.assertEqual(result["mode"], "repository-measured-baseline-qualification")
            self.assertTrue(result["checks"])
            self.assertTrue(all({"name", "expected", "actual", "passed", "reason"} == set(item) for item in result["checks"]))

    def test_qualification_rejects_representative_artifact_tampering(self):
        def change_prediction(manifest, rows):
            rows[0].update(prediction="B", correct=False)
            manifest["metrics"] = run.aggregate(rows)

        mutations = {
            "mock_only": lambda manifest, rows: manifest.update(backend="mock", result_classification="mock-only"),
            "unverified": lambda manifest, rows: manifest.update(result_classification="unverified"),
            "incomplete": lambda manifest, rows: manifest.update(status="running"),
            "failed_preflight": lambda manifest, rows: manifest["preflight"].update(passed=False),
            "dirty_tree": lambda manifest, rows: manifest.update(git_status=" M mark2/run.py"),
            "contract_hash": lambda manifest, rows: manifest.update(contract_sha256="0" * 64),
            "source_hash": lambda manifest, rows: manifest["source_sha256"].update({"run.py": "0" * 64}),
            "dataset_hash": lambda manifest, rows: manifest["dataset_selection"].update(sha256="0" * 64),
            "chat_template_hash": lambda manifest, rows: manifest.update(chat_template_sha256="0" * 64),
            "model_config_hash": lambda manifest, rows: manifest.update(model_config_sha256="0" * 64),
            "missing_prediction_field": lambda manifest, rows: rows[0].pop("target"),
            "wrong_prediction_type": lambda manifest, rows: rows[0].update(target=1),
            "prediction_count": lambda manifest, rows: rows.pop(),
            "duplicate_question": lambda manifest, rows: rows.__setitem__(1, {**rows[1], "question_sha256": rows[0]["question_sha256"]}),
            "incorrect_metric": lambda manifest, rows: manifest["metrics"].update(accuracy=0.0),
            "different_prediction": change_prediction,
            "different_commit": lambda manifest, rows: manifest.update(git_commit="b" * 40),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                first, second = root / "first", root / "second"
                make_measured_artifact(first, "first")
                make_measured_artifact(second, "second")
                manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
                rows = run._predictions(second / "predictions.jsonl")
                mutate(manifest, rows)
                run.write_json(second / "manifest.json", manifest)
                with (second / "predictions.jsonl").open("w", encoding="utf-8") as handle:
                    for row in rows:
                        handle.write(json.dumps(row) + "\n")
                result = run.qualify_baseline_runs(first, second)
                self.assertFalse(result["eligible"])
                self.assertTrue(any(not item["passed"] for item in result["checks"]))

    def test_qualification_rejects_same_run_and_cli_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "first", root / "second"
            make_measured_artifact(first, "same")
            make_measured_artifact(second, "same")
            with patch.object(sys, "argv", ["mark2.run", "qualify", str(first), str(second)]), patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(run.main(), 1)

    def test_qualification_rejects_different_fixed_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "first", root / "second"
            make_measured_artifact(first, "first")
            make_measured_artifact(second, "second")
            profile = read_profile(run.DEFAULT_PROFILE)
            changed_probe = FakeProbe(python_version=[3, 11, 9])
            run.write_json(second / "preflight.json", evaluate_preflight(profile, EXPECTED_COMMIT, changed_probe))
            result = run.qualify_baseline_runs(first, second)
            self.assertFalse(result["eligible"])
            failed = {item["name"] for item in result["checks"] if not item["passed"]}
            self.assertIn("pair.same_fixed_environment", failed)


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
