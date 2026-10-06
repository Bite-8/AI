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
from mark2.config import (
    read_config,
    read_experiment_contract,
    validate_config,
    validate_experiment_contract,
)
from mark2.environment import evaluate_preflight, read_profile


EXPECTED_COMMIT = run.command(
    ["git", "-C", str(run.REPOSITORY_ROOT), "rev-parse", "HEAD"]
)["output"]


def make_measured_artifact(path, run_id):
    path.mkdir()
    config = read_config(run.DEFAULT_CONFIG)
    shutil.copyfile(run.DEFAULT_CONFIG, path / "contract.json")
    (path / "chat_template.txt").write_text("fixed template", encoding="utf-8")
    model_config = {"model_type": "qwen3_5"}
    run.write_json(path / "model_config.json", model_config)
    source_hashes = run._snapshot(path)
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
        "runtime": {
            "backend": "transformers",
            "dtype": "bfloat16",
            "quantization": None,
            "tf32": False,
            "cuda": "12.8",
            "gpu_count": 1,
            "gpu_names": ["NVIDIA L4"],
        },
        "metrics": run.aggregate(rows),
        "preflight": {"passed": True, "report": "preflight.json", "profile": str(run.DEFAULT_PROFILE)},
    }
    run.write_json(path / "manifest.json", manifest)


def attach_experiment_contract(path, contract=None):
    contract = contract or read_experiment_contract(run.DEFAULT_EXPERIMENT_CONTRACT)
    run.write_json(path / "experiment_contract.json", contract)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        experiment_contract=contract,
        experiment_contract_sha256=run.sha256_json(contract),
        experiment_contract_file="experiment_contract.json",
    )
    run.write_json(manifest_path, manifest)


def set_artifact_correct_indices(path, correct_indices):
    correct_indices = set(correct_indices)
    rows = run._predictions(path / "predictions.jsonl")
    for index, row in enumerate(rows):
        correct = index in correct_indices
        row.update(
            prediction="A" if correct else "B",
            correct=correct,
            output_text="Answer: A" if correct else "Answer: B",
        )
    with (path / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"] = run.aggregate(rows)
    run.write_json(manifest_path, manifest)


class MeasuredBackend:
    name = "transformers"

    def run(self, config, manifest, run_dir):
        (run_dir / "chat_template.txt").write_text("fixed template", encoding="utf-8")
        model_config = {"model_type": "qwen3_5"}
        run.write_json(run_dir / "model_config.json", model_config)
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
        question_hashes = [row["question_sha256"] for row in rows]
        manifest.update(
            dataset_selection={
                "count": len(rows),
                "question_hashes": question_hashes,
                "sha256": hashlib.sha256("\n".join(question_hashes).encode("ascii")).hexdigest(),
            },
            chat_template_sha256=hashlib.sha256(b"fixed template").hexdigest(),
            model_config_sha256=run.sha256_json(model_config),
            runtime={
                "backend": "transformers",
                "dtype": "bfloat16",
                "quantization": None,
                "tf32": False,
                "cuda": "12.8",
                "gpu_count": 1,
                "gpu_names": ["NVIDIA L4"],
            },
        )
        return rows


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


class ExperimentContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = read_experiment_contract(run.DEFAULT_EXPERIMENT_CONTRACT)

    def test_fixed_example_is_valid_but_not_an_experiment_result(self):
        self.assertEqual(self.contract["schema_version"], 1)
        self.assertEqual(self.contract["primary_metric"]["name"], "exact_match_accuracy")
        self.assertIn("not-evaluated", self.contract["hypothesis_id"])

    def test_exact_keys_are_required_at_every_level(self):
        cases = []
        for path, key in (
            ((), "hypothesis_id"),
            (("independent_variable",), "description"),
            (("primary_metric",), "direction"),
            (("decision_rule",), "paired_test"),
        ):
            missing = deepcopy(self.contract)
            target = missing
            for part in path:
                target = target[part]
            target.pop(key)
            cases.append(missing)

            unknown = deepcopy(self.contract)
            target = unknown
            for part in path:
                target = target[part]
            target["unknown"] = "value"
            cases.append(unknown)

        for contract in cases:
            with self.subTest(contract=contract):
                with self.assertRaisesRegex(ValueError, "exactly"):
                    validate_experiment_contract(contract)

    def test_ids_descriptions_and_enums_are_strict(self):
        mutations = (
            lambda value: value.update(schema_version=True),
            lambda value: value.update(experiment_id=""),
            lambda value: value.update(hypothesis_id="contains spaces"),
            lambda value: value["independent_variable"].update(id="x" * 81),
            lambda value: value["independent_variable"].update(description=" "),
            lambda value: value["independent_variable"].update(description=" padded"),
            lambda value: value["primary_metric"].update(name="accuracy"),
            lambda value: value["primary_metric"].update(direction="decrease"),
            lambda value: value["decision_rule"].update(paired_test="t-test"),
        )
        for mutate in mutations:
            contract = deepcopy(self.contract)
            mutate(contract)
            with self.subTest(contract=contract):
                with self.assertRaises(ValueError):
                    validate_experiment_contract(contract)

    def test_numeric_boolean_and_boundary_values_are_strict(self):
        valid_boundaries = ((0, 0.0001), (1, 0.9999))
        for minimum, significance in valid_boundaries:
            contract = deepcopy(self.contract)
            contract["decision_rule"].update(
                minimum_accuracy_difference=minimum, significance_level=significance
            )
            validate_experiment_contract(contract)

        invalid_values = (
            ("minimum_accuracy_difference", True),
            ("minimum_accuracy_difference", -0.01),
            ("minimum_accuracy_difference", 1.01),
            ("minimum_accuracy_difference", float("nan")),
            ("minimum_accuracy_difference", float("inf")),
            ("significance_level", False),
            ("significance_level", 0),
            ("significance_level", 1),
            ("significance_level", "0.05"),
            ("require_identical_variant_predictions", 1),
        )
        for field, invalid in invalid_values:
            contract = deepcopy(self.contract)
            contract["decision_rule"][field] = invalid
            with self.subTest(field=field, invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_experiment_contract(contract)


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
            self.assertNotIn("experiment_contract", manifest)

    def test_experiment_contract_is_recorded_before_backend_and_detects_tampering(self):
        class InspectingBackend(run.MockBackend):
            def run(self, config, manifest, run_dir):
                saved = json.loads((run_dir / "experiment_contract.json").read_text(encoding="utf-8"))
                self.recorded_before_run = (
                    manifest["experiment_contract"] == saved
                    and manifest["experiment_contract_sha256"] == run.sha256_json(saved)
                    and manifest["experiment_contract_file"] == "experiment_contract.json"
                )
                return super().run(config, manifest, run_dir)

        config = read_config(run.DEFAULT_CONFIG)
        experiment = read_experiment_contract(run.DEFAULT_EXPERIMENT_CONTRACT)
        backend = InspectingBackend()
        with tempfile.TemporaryDirectory() as folder:
            artifact = run.execute_run(
                config,
                run.DEFAULT_CONFIG,
                Path(folder),
                "experiment",
                backend,
                experiment_contract=experiment,
                experiment_contract_path=run.DEFAULT_EXPERIMENT_CONTRACT,
            )
            self.assertTrue(backend.recorded_before_run)
            manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
            saved = json.loads((artifact / manifest["experiment_contract_file"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["experiment_contract"], saved)
            self.assertEqual(manifest["experiment_contract_sha256"], run.sha256_json(saved))

            saved["hypothesis_id"] = "tampered-hypothesis"
            run.write_json(artifact / manifest["experiment_contract_file"], saved)
            self.assertNotEqual(manifest["experiment_contract_sha256"], run.sha256_json(saved))

    def test_invalid_experiment_contract_is_rejected_before_artifact_or_backend(self):
        class TrackingBackend(run.MockBackend):
            called = False

            def run(self, config, manifest, run_dir):
                self.called = True
                return super().run(config, manifest, run_dir)

        config = read_config(run.DEFAULT_CONFIG)
        experiment = read_experiment_contract(run.DEFAULT_EXPERIMENT_CONTRACT)
        experiment["decision_rule"]["significance_level"] = 0
        backend = TrackingBackend()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):
                run.execute_run(
                    config,
                    run.DEFAULT_CONFIG,
                    root,
                    "invalid-experiment",
                    backend,
                    experiment_contract=experiment,
                    experiment_contract_path=run.DEFAULT_EXPERIMENT_CONTRACT,
                )
            self.assertFalse(backend.called)
            self.assertFalse((root / "invalid-experiment").exists())

    def test_experiment_contract_source_change_during_setup_cannot_change_saved_copy(self):
        config = read_config(run.DEFAULT_CONFIG)
        original = read_experiment_contract(run.DEFAULT_EXPERIMENT_CONTRACT)
        changed = deepcopy(original)
        changed["hypothesis_id"] = "changed-after-validation"

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "experiment_contract.json"
            shutil.copyfile(run.DEFAULT_EXPERIMENT_CONTRACT, source)
            original_collect = run.collect

            def change_source_during_setup(run_dir):
                run.write_json(source, changed)
                return original_collect(run_dir)

            with patch("mark2.run.collect", side_effect=change_source_during_setup):
                artifact = run.execute_run(
                    config,
                    run.DEFAULT_CONFIG,
                    root,
                    "source-change",
                    run.MockBackend(),
                    experiment_contract=original,
                    experiment_contract_path=source,
                )

            manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
            saved = json.loads((artifact / manifest["experiment_contract_file"]).read_text(encoding="utf-8"))
            self.assertEqual(original, saved)
            self.assertNotEqual(changed, saved)
            self.assertEqual(manifest["experiment_contract"], saved)
            self.assertEqual(manifest["experiment_contract_sha256"], run.sha256_json(saved))

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

    def test_execute_run_artifacts_are_qualified(self):
        config = read_config(run.DEFAULT_CONFIG)

        def successful_git_command(args):
            output = "" if "status" in args else EXPECTED_COMMIT
            return {"status": "ok", "output": output}

        with tempfile.TemporaryDirectory() as folder, patch.object(run, "command", side_effect=successful_git_command):
            root = Path(folder)
            first = run.execute_run(
                config,
                run.DEFAULT_CONFIG,
                root,
                "first",
                MeasuredBackend(),
                expected_commit=EXPECTED_COMMIT,
                preflight_probe=FakeProbe(),
            )
            second = run.execute_run(
                config,
                run.DEFAULT_CONFIG,
                root,
                "second",
                MeasuredBackend(),
                expected_commit=EXPECTED_COMMIT,
                preflight_probe=FakeProbe(),
            )
            result = run.qualify_baseline_runs(first, second)
            self.assertTrue(result["eligible"])
            manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["git_commit"], EXPECTED_COMMIT)
            self.assertEqual(manifest["git_status"], "")

    def test_qualification_rejects_missing_required_snapshot_file_and_manifest_entry(self):
        config = read_config(run.DEFAULT_CONFIG)

        def successful_git_command(args):
            output = "" if "status" in args else EXPECTED_COMMIT
            return {"status": "ok", "output": output}

        with tempfile.TemporaryDirectory() as folder, patch.object(run, "command", side_effect=successful_git_command):
            root = Path(folder)
            artifacts = [
                run.execute_run(
                    config,
                    run.DEFAULT_CONFIG,
                    root,
                    run_id,
                    MeasuredBackend(),
                    expected_commit=EXPECTED_COMMIT,
                    preflight_probe=FakeProbe(),
                )
                for run_id in ("first", "second")
            ]
            for artifact in artifacts:
                (artifact / "source" / "config.py").unlink()
                manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
                manifest["source_sha256"].pop("config.py")
                run.write_json(artifact / "manifest.json", manifest)

            result = run.qualify_baseline_runs(*artifacts)
            self.assertFalse(result["eligible"])
            failed_checks = {item["name"] for item in result["checks"] if not item["passed"]}
            self.assertEqual(
                {"run1.source_integrity", "run2.source_integrity"},
                failed_checks & {"run1.source_integrity", "run2.source_integrity"},
            )

    def test_qualification_rejects_source_tampering_with_updated_manifest_hash(self):
        config = read_config(run.DEFAULT_CONFIG)

        def successful_git_command(args):
            output = "" if "status" in args else EXPECTED_COMMIT
            return {"status": "ok", "output": output}

        with tempfile.TemporaryDirectory() as folder, patch.object(run, "command", side_effect=successful_git_command):
            root = Path(folder)
            artifacts = [
                run.execute_run(
                    config,
                    run.DEFAULT_CONFIG,
                    root,
                    run_id,
                    MeasuredBackend(),
                    expected_commit=EXPECTED_COMMIT,
                    preflight_probe=FakeProbe(),
                )
                for run_id in ("first", "second")
            ]
            replacement = b"self-consistent but not committed source\n"
            replacement_hash = hashlib.sha256(replacement).hexdigest()
            for artifact in artifacts:
                (artifact / "source" / "run.py").write_bytes(replacement)
                manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
                manifest["source_sha256"]["run.py"] = replacement_hash
                run.write_json(artifact / "manifest.json", manifest)

            result = run.qualify_baseline_runs(*artifacts)
            self.assertFalse(result["eligible"])
            failed_checks = {item["name"] for item in result["checks"] if not item["passed"]}
            self.assertIn("run1.source_integrity", failed_checks)
            self.assertIn("run2.source_integrity", failed_checks)

    def test_qualification_cli_reports_source_directory_symlink_as_strict_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = (root / "first", root / "second")
            for artifact, run_id in zip(artifacts, ("first", "second")):
                make_measured_artifact(artifact, run_id)
                source = artifact / "source"
                external_source = root / f"{run_id}-external-source"
                source.rename(external_source)
                source.symlink_to(external_source, target_is_directory=True)

            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 1)

            report = json.loads(
                stdout.getvalue(), parse_constant=lambda value: self.fail(f"non-finite JSON constant: {value}")
            )
            self.assertFalse(report["eligible"])
            for check_name in ("run1.source_integrity", "run2.source_integrity"):
                check = next(item for item in report["checks"] if item["name"] == check_name)
                self.assertFalse(check["passed"])
                self.assertIn(
                    {"source_directory_error": "artifact entry must be a regular directory"},
                    check["actual"],
                )

    def test_qualification_cli_reports_prediction_symlink_as_strict_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = (root / "first", root / "second")
            for artifact, run_id in zip(artifacts, ("first", "second")):
                make_measured_artifact(artifact, run_id)
                predictions = artifact / "predictions.jsonl"
                external_predictions = root / f"{run_id}-external-predictions.jsonl"
                predictions.rename(external_predictions)
                predictions.symlink_to(external_predictions)

            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 1)

            report = json.loads(
                stdout.getvalue(), parse_constant=lambda value: self.fail(f"non-finite JSON constant: {value}")
            )
            self.assertFalse(report["eligible"])
            for check_name in ("run1.predictions_readable", "run2.predictions_readable"):
                check = next(item for item in report["checks"] if item["name"] == check_name)
                self.assertFalse(check["passed"])
                self.assertEqual(check["actual"], "artifact entry must be a regular file")

    def test_command_failure_cannot_qualify_as_git_evidence(self):
        config = read_config(run.DEFAULT_CONFIG)
        failed = {"status": "error", "returncode": 128}
        with tempfile.TemporaryDirectory() as folder, patch.object(run, "command", return_value=failed):
            root = Path(folder)
            first = run.execute_run(
                config,
                run.DEFAULT_CONFIG,
                root,
                "first",
                MeasuredBackend(),
                expected_commit=EXPECTED_COMMIT,
                preflight_probe=FakeProbe(),
            )
            second = run.execute_run(
                config,
                run.DEFAULT_CONFIG,
                root,
                "second",
                MeasuredBackend(),
                expected_commit=EXPECTED_COMMIT,
                preflight_probe=FakeProbe(),
            )
            result = run.qualify_baseline_runs(first, second)
            self.assertFalse(result["eligible"])
            failed_checks = {item["name"] for item in result["checks"] if not item["passed"]}
            self.assertIn("run1.manifest_schema", failed_checks)
            self.assertIn("run1.commit_preflight_consistency", failed_checks)

    def test_qualification_rejects_self_consistent_fixed_file_tampering(self):
        cases = ("contract", "profile")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                first, second = root / "first", root / "second"
                make_measured_artifact(first, "first")
                make_measured_artifact(second, "second")
                for artifact in (first, second):
                    if case == "contract":
                        contract = json.loads((artifact / "contract.json").read_text(encoding="utf-8"))
                        contract["metric"]["reproducibility"]["max_accuracy_delta"] = 1.0
                        run.write_json(artifact / "contract.json", contract)
                        manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
                        manifest["contract"] = contract
                        manifest["contract_sha256"] = run.sha256_json(contract)
                        run.write_json(artifact / "manifest.json", manifest)
                    else:
                        preflight = json.loads((artifact / "preflight.json").read_text(encoding="utf-8"))
                        preflight["profile"]["packages"]["torch"] = "0.0.0"
                        preflight["observed"]["packages"]["torch"] = "0.0.0"
                        preflight = evaluate_preflight(
                            preflight["profile"], preflight["expected_commit"], FakeProbe(packages=preflight["observed"]["packages"])
                        )
                        run.write_json(artifact / "preflight.json", preflight)
                result = run.qualify_baseline_runs(first, second)
                self.assertFalse(result["eligible"])
                failed_checks = {item["name"] for item in result["checks"] if not item["passed"]}
                self.assertIn(f"run1.fixed_{case}", failed_checks)

    def test_qualification_cli_reports_malformed_nested_artifacts(self):
        cases = {
            "preflight_observed": ("preflight.json", lambda value: value.update(observed=[]), "run2.preflight_passed"),
            "contract_dataset": ("contract.json", lambda value: value.update(dataset=[]), "run2.contract_schema"),
        }
        for name, (filename, mutate, expected_failed_check) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                first, second = root / "first", root / "second"
                make_measured_artifact(first, "first")
                make_measured_artifact(second, "second")
                artifact_path = second / filename
                value = json.loads(artifact_path.read_text(encoding="utf-8"))
                mutate(value)
                run.write_json(artifact_path, value)

                stdout = io.StringIO()
                with patch.object(
                    sys, "argv", ["mark2.run", "qualify", str(first), str(second)]
                ), patch.object(sys, "stdout", stdout):
                    self.assertEqual(run.main(), 1)
                report = json.loads(stdout.getvalue())
                self.assertFalse(report["eligible"])
                failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
                self.assertIn(expected_failed_check, failed_checks)

    def test_qualification_cli_rejects_non_choice_answer_values(self):
        for answer_value in ("", "AB"):
            with self.subTest(answer_value=answer_value), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                artifacts = (root / "first", root / "second")
                for artifact, run_id in zip(artifacts, ("first", "second")):
                    make_measured_artifact(artifact, run_id)
                    rows = run._predictions(artifact / "predictions.jsonl")
                    for row in rows:
                        row.update(target=answer_value, prediction=answer_value, correct=True)
                    with (artifact / "predictions.jsonl").open("w", encoding="utf-8") as handle:
                        for row in rows:
                            handle.write(json.dumps(row) + "\n")

                stdout = io.StringIO()
                with patch.object(
                    sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
                ), patch.object(sys, "stdout", stdout):
                    self.assertEqual(run.main(), 1)
                report = json.loads(stdout.getvalue())
                self.assertFalse(report["eligible"])
                failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
                self.assertIn("run1.prediction_schema", failed_checks)
                self.assertIn("run2.prediction_schema", failed_checks)

    def test_qualification_cli_rejects_output_text_prediction_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = (root / "first", root / "second")
            for artifact, run_id in zip(artifacts, ("first", "second")):
                make_measured_artifact(artifact, run_id)
                rows = run._predictions(artifact / "predictions.jsonl")
                for row in rows:
                    row["output_text"] = "Answer: B"
                with (artifact / "predictions.jsonl").open("w", encoding="utf-8") as handle:
                    for row in rows:
                        handle.write(json.dumps(row) + "\n")

            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 1)
            report = json.loads(stdout.getvalue())
            self.assertFalse(report["eligible"])
            failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
            self.assertIn("run1.prediction_schema", failed_checks)
            self.assertIn("run2.prediction_schema", failed_checks)

    def test_qualification_cli_reports_model_artifact_symlink_as_strict_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = (root / "first", root / "second")
            for artifact, run_id in zip(artifacts, ("first", "second")):
                make_measured_artifact(artifact, run_id)
            chat_template = artifacts[0] / "chat_template.txt"
            chat_template.unlink()
            chat_template.symlink_to("/proc/self/mem")

            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 1)

            report = json.loads(
                stdout.getvalue(), parse_constant=lambda value: self.fail(f"non-finite JSON constant: {value}")
            )
            self.assertFalse(report["eligible"])
            failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
            self.assertIn("run1.model_artifact_integrity", failed_checks)
            check = next(item for item in report["checks"] if item["name"] == "run1.model_artifact_integrity")
            self.assertEqual(check["actual"]["chat_template_error"], "artifact entry must be a regular file")

    def test_qualification_cli_rejects_non_finite_generation_seconds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = (root / "first", root / "second")
            for artifact, run_id in zip(artifacts, ("first", "second")):
                make_measured_artifact(artifact, run_id)
                predictions = artifact / "predictions.jsonl"
                predictions.write_text(
                    predictions.read_text(encoding="utf-8").replace('"generation_seconds": 0.1', '"generation_seconds": 1e309'),
                    encoding="utf-8",
                )

            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 1)
            report = json.loads(stdout.getvalue())
            self.assertFalse(report["eligible"])
            failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
            self.assertIn("run1.prediction_schema", failed_checks)
            self.assertIn("run2.prediction_schema", failed_checks)

    def test_qualification_cli_reports_non_finite_metric_as_strict_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = (root / "first", root / "second")
            for artifact, run_id in zip(artifacts, ("first", "second")):
                make_measured_artifact(artifact, run_id)
                manifest_path = artifact / "manifest.json"
                manifest_path.write_text(
                    manifest_path.read_text(encoding="utf-8").replace('"accuracy": 1.0', '"accuracy": NaN'),
                    encoding="utf-8",
                )

            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 1)

            def reject_non_finite(value):
                raise ValueError(f"non-finite JSON constant: {value}")

            report = json.loads(stdout.getvalue(), parse_constant=reject_non_finite)
            self.assertFalse(report["eligible"])
            failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
            self.assertIn("run1.metric_integrity", failed_checks)
            self.assertIn("run2.metric_integrity", failed_checks)
            metric_checks = [item for item in report["checks"] if item["name"].endswith(".metric_integrity")]
            self.assertTrue(
                all(item["actual"]["accuracy"] == {"non_finite_number": "NaN"} for item in metric_checks)
            )

    def test_qualification_cli_rejects_oversized_numbers_as_strict_json(self):
        oversized = 10 ** 1000
        for field in ("generation_seconds", "accuracy"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                artifacts = (root / "first", root / "second")
                for artifact, run_id in zip(artifacts, ("first", "second")):
                    make_measured_artifact(artifact, run_id)
                    if field == "generation_seconds":
                        rows = run._predictions(artifact / "predictions.jsonl")
                        for row in rows:
                            row[field] = oversized
                        with (artifact / "predictions.jsonl").open("w", encoding="utf-8") as handle:
                            for row in rows:
                                handle.write(json.dumps(row) + "\n")
                    else:
                        manifest_path = artifact / "manifest.json"
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        manifest["metrics"][field] = oversized
                        run.write_json(manifest_path, manifest)

                stdout = io.StringIO()
                with patch.object(
                    sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
                ), patch.object(sys, "stdout", stdout):
                    self.assertEqual(run.main(), 1)

                report = json.loads(
                    stdout.getvalue(),
                    parse_constant=lambda value: self.fail(f"non-finite JSON constant: {value}"),
                )
                self.assertFalse(report["eligible"])
                failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
                check_suffix = "prediction_schema" if field == "generation_seconds" else "metric_integrity"
                self.assertIn(f"run1.{check_suffix}", failed_checks)
                self.assertIn(f"run2.{check_suffix}", failed_checks)

    def test_qualification_cli_reports_json_integer_conversion_failure(self):
        oversized = "9" * 5001
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = (root / "first", root / "second")
            for artifact, run_id in zip(artifacts, ("first", "second")):
                make_measured_artifact(artifact, run_id)
                predictions = artifact / "predictions.jsonl"
                predictions.write_text(
                    predictions.read_text(encoding="utf-8").replace(
                        '"generation_seconds": 0.1', f'"generation_seconds": {oversized}'
                    ),
                    encoding="utf-8",
                )

            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 1)

            report = json.loads(
                stdout.getvalue(),
                parse_constant=lambda value: self.fail(f"non-finite JSON constant: {value}"),
            )
            self.assertFalse(report["eligible"])
            failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
            self.assertIn("run1.predictions_readable", failed_checks)
            self.assertIn("run2.predictions_readable", failed_checks)

    def test_qualification_cli_rejects_self_consistent_invalid_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = (root / "first", root / "second")
            for artifact, run_id in zip(artifacts, ("first", "second")):
                make_measured_artifact(artifact, run_id)
                manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
                manifest["runtime"] = {
                    "backend": "transformers",
                    "dtype": "float32",
                    "quantization": "4bit",
                    "tf32": True,
                    "cuda": "unexpected",
                    "gpu_count": 8,
                    "gpu_names": ["unexpected"] * 8,
                }
                run.write_json(artifact / "manifest.json", manifest)

            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 1)
            report = json.loads(stdout.getvalue())
            self.assertFalse(report["eligible"])
            failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
            self.assertIn("run1.runtime_consistency", failed_checks)
            self.assertIn("run2.runtime_consistency", failed_checks)

    def test_qualification_cli_rejects_type_invalid_metrics(self):
        cases = {
            "boolean_accuracy": lambda metrics: metrics.update(accuracy=True),
            "float_count": lambda metrics: metrics.update(correct=float(metrics["correct"])),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                artifacts = (root / "first", root / "second")
                for artifact, run_id in zip(artifacts, ("first", "second")):
                    make_measured_artifact(artifact, run_id)
                    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
                    mutate(manifest["metrics"])
                    run.write_json(artifact / "manifest.json", manifest)

                stdout = io.StringIO()
                with patch.object(
                    sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
                ), patch.object(sys, "stdout", stdout):
                    self.assertEqual(run.main(), 1)
                report = json.loads(stdout.getvalue())
                self.assertFalse(report["eligible"])
                failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
                self.assertIn("run1.metric_integrity", failed_checks)
                self.assertIn("run2.metric_integrity", failed_checks)

    def test_qualification_cli_rejects_type_invalid_dataset_selection_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = (root / "first", root / "second")
            for artifact, run_id in zip(artifacts, ("first", "second")):
                make_measured_artifact(artifact, run_id)
                manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
                manifest["dataset_selection"]["count"] = float(manifest["dataset_selection"]["count"])
                run.write_json(artifact / "manifest.json", manifest)

            stdout = io.StringIO()
            with patch.object(
                sys, "argv", ["mark2.run", "qualify", *(str(path) for path in artifacts)]
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 1)
            report = json.loads(stdout.getvalue())
            self.assertFalse(report["eligible"])
            failed_checks = {item["name"] for item in report["checks"] if not item["passed"]}
            self.assertIn("run1.dataset_selection_integrity", failed_checks)
            self.assertIn("run2.dataset_selection_integrity", failed_checks)

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


class ExperimentQualificationTests(unittest.TestCase):
    def make_artifacts(self, root):
        artifacts = tuple(root / name for name in ("baseline-1", "baseline-2", "variant-1", "variant-2"))
        for artifact, run_id in zip(artifacts, ("baseline-1", "baseline-2", "variant-1", "variant-2")):
            make_measured_artifact(artifact, run_id)
            attach_experiment_contract(artifact)
        return artifacts

    def test_four_artifact_experiment_is_eligible_and_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = self.make_artifacts(root)
            report_path = root / "report.json"
            stdout = io.StringIO()
            with patch.object(
                sys,
                "argv",
                ["mark2.run", "qualify-experiment", *(str(path) for path in artifacts), "--output", str(report_path)],
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report, json.loads(report_path.read_text(encoding="utf-8")))
            self.assertTrue(report["eligible"])
            self.assertEqual(report["mode"], "repository-measured-controlled-experiment-qualification")
            self.assertEqual(set(report["pair_sources"]), {"baseline", "variant"})
            self.assertTrue(
                all({"name", "expected", "actual", "passed", "reason"} == set(check) for check in report["checks"])
            )
            self.assertNotIn("p_value", report)
            self.assertNotIn("supported", report)

    def test_experiment_qualification_rejects_contract_tampering_and_mismatch(self):
        cases = ("copy_tamper", "different_contract", "copy_symlink")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                artifacts = self.make_artifacts(root)
                target = artifacts[3]
                contract_path = target / "experiment_contract.json"
                if case == "copy_tamper":
                    contract = json.loads(contract_path.read_text(encoding="utf-8"))
                    contract["hypothesis_id"] = "tampered"
                    run.write_json(contract_path, contract)
                elif case == "different_contract":
                    contract = json.loads(contract_path.read_text(encoding="utf-8"))
                    contract["experiment_id"] = "different-experiment"
                    attach_experiment_contract(target, contract)
                else:
                    outside = root / "outside.json"
                    contract_path.rename(outside)
                    contract_path.symlink_to(outside)
                result = run.qualify_experiment_artifacts(*artifacts)
                self.assertFalse(result["eligible"])
                failed = {check["name"] for check in result["checks"] if not check["passed"]}
                self.assertTrue(
                    {"run4.experiment_contract_integrity", "experiment.same_experiment_contract"} & failed
                )

    def test_experiment_qualification_rejects_duplicate_run_sample_target_and_runtime(self):
        cases = ("duplicate_run", "sample_target", "runtime")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                artifacts = self.make_artifacts(root)
                target = artifacts[3]
                manifest_path = target / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if case == "duplicate_run":
                    manifest["run_id"] = "baseline-1"
                elif case == "sample_target":
                    rows = run._predictions(target / "predictions.jsonl")
                    rows[0].update(target="B", prediction="B", correct=True, output_text="Answer: B")
                    manifest["metrics"] = run.aggregate(rows)
                    with (target / "predictions.jsonl").open("w", encoding="utf-8") as handle:
                        for row in rows:
                            handle.write(json.dumps(row) + "\n")
                else:
                    manifest["runtime"]["cuda"] = "12.9"
                run.write_json(manifest_path, manifest)
                result = run.qualify_experiment_artifacts(*artifacts)
                self.assertFalse(result["eligible"])
                failed = {check["name"] for check in result["checks"] if not check["passed"]}
                expected = {
                    "duplicate_run": "experiment.distinct_run_ids",
                    "sample_target": "experiment.same_question_order_and_targets",
                    "runtime": "experiment.same_runtime",
                }[case]
                self.assertIn(expected, failed)

    def test_variant_prediction_rule_controls_pair_reproducibility(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = self.make_artifacts(root)
            target = artifacts[3]
            rows = run._predictions(target / "predictions.jsonl")
            rows[0].update(prediction="B", correct=False, output_text="Answer: B")
            with (target / "predictions.jsonl").open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            manifest_path = target / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["metrics"] = run.aggregate(rows)
            run.write_json(manifest_path, manifest)

            result = run.qualify_experiment_artifacts(*artifacts)
            self.assertFalse(result["eligible"])
            failed = {check["name"] for check in result["checks"] if not check["passed"]}
            self.assertIn("variant.pair.identical_predictions", failed)

            contract = read_experiment_contract(run.DEFAULT_EXPERIMENT_CONTRACT)
            contract["decision_rule"]["require_identical_variant_predictions"] = False
            for artifact in artifacts:
                attach_experiment_contract(artifact, contract)
            result = run.qualify_experiment_artifacts(*artifacts)
            self.assertTrue(result["eligible"])


class ExperimentEvaluationTests(unittest.TestCase):
    def make_artifacts(self, root):
        artifacts = tuple(root / name for name in ("baseline-1", "baseline-2", "variant-1", "variant-2"))
        for artifact, run_id in zip(artifacts, ("baseline-1", "baseline-2", "variant-1", "variant-2")):
            make_measured_artifact(artifact, run_id)
            attach_experiment_contract(artifact)
        return artifacts

    def set_pair_results(self, artifacts, baseline_correct, variant_first_correct, variant_second_correct=None):
        if variant_second_correct is None:
            variant_second_correct = variant_first_correct
        for artifact in artifacts[:2]:
            set_artifact_correct_indices(artifact, baseline_correct)
        set_artifact_correct_indices(artifacts[2], variant_first_correct)
        set_artifact_correct_indices(artifacts[3], variant_second_correct)

    def test_exact_binomial_tail_and_paired_counts_cover_known_edges(self):
        self.assertEqual(run.exact_binomial_upper_tail(0, 0), 1.0)
        self.assertEqual(run.exact_binomial_upper_tail(5, 5), 1 / 32)
        self.assertEqual(run.exact_binomial_upper_tail(2, 4), 11 / 16)
        baseline = [{"correct": value} for value in (True, True, False, False, False)]
        variant = [{"correct": value} for value in (True, False, True, False, True)]
        result = run._paired_accuracy_comparison(baseline, variant, "baseline", "variant")
        self.assertEqual(result["sample_size"], 5)
        self.assertEqual(result["both_correct"], 1)
        self.assertEqual(result["both_incorrect"], 1)
        self.assertEqual(result["variant_only_correct"], 2)
        self.assertEqual(result["baseline_only_correct"], 1)
        self.assertEqual(result["discordant_pairs"], 3)
        self.assertEqual(result["accuracy_difference"], 0.2)
        self.assertEqual(result["improvement_p_value"], 0.5)
        self.assertEqual(result["regression_p_value"], 0.875)

        edge_cases = {
            "zero_discordant": ([True] * 5, [True] * 5, (0, 0, 1.0, 1.0)),
            "all_improve": ([False] * 5, [True] * 5, (5, 0, 1 / 32, 1.0)),
            "all_regress": ([True] * 5, [False] * 5, (0, 5, 1.0, 1 / 32)),
            "equal_discordant": (
                [True, True, False, False],
                [False, False, True, True],
                (2, 2, 11 / 16, 11 / 16),
            ),
        }
        for name, (baseline_values, variant_values, expected) in edge_cases.items():
            with self.subTest(name=name):
                comparison = run._paired_accuracy_comparison(
                    [{"correct": value} for value in baseline_values],
                    [{"correct": value} for value in variant_values],
                    "baseline",
                    "variant",
                )
                self.assertEqual(
                    (
                        comparison["variant_only_correct"],
                        comparison["baseline_only_correct"],
                        comparison["improvement_p_value"],
                        comparison["regression_p_value"],
                    ),
                    expected,
                )

    def test_three_classifications_and_boundary_thresholds(self):
        cases = {
            "supported": (range(50), range(51)),
            "regressed": (range(51), range(50)),
            "inconclusive": (range(50), range(50)),
        }
        for expected, (baseline_correct, variant_correct) in cases.items():
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as folder:
                artifacts = self.make_artifacts(Path(folder))
                contract = read_experiment_contract(run.DEFAULT_EXPERIMENT_CONTRACT)
                contract["decision_rule"].update(
                    minimum_accuracy_difference=0.01,
                    significance_level=0.5,
                )
                for artifact in artifacts:
                    attach_experiment_contract(artifact, contract)
                self.set_pair_results(artifacts, baseline_correct, variant_correct)
                report = run.evaluate_experiment_artifacts(*artifacts)
                self.assertTrue(report["eligible"])
                self.assertEqual(report["classification"]["result"], expected)
                if expected != "inconclusive":
                    comparison = report["comparisons"][0]
                    self.assertEqual(abs(comparison["accuracy_difference"]), 0.01)
                    expected_p = (
                        comparison["improvement_p_value"]
                        if expected == "supported"
                        else comparison["regression_p_value"]
                    )
                    self.assertEqual(expected_p, 0.5)

    def test_nonidentical_variant_runs_are_not_pooled(self):
        with tempfile.TemporaryDirectory() as folder:
            artifacts = self.make_artifacts(Path(folder))
            contract = read_experiment_contract(run.DEFAULT_EXPERIMENT_CONTRACT)
            contract["decision_rule"]["require_identical_variant_predictions"] = False
            contract["decision_rule"]["significance_level"] = 0.05
            for artifact in artifacts:
                attach_experiment_contract(artifact, contract)
            self.set_pair_results(artifacts, range(50), range(70), range(50))
            report = run.evaluate_experiment_artifacts(*artifacts)
            self.assertTrue(report["eligible"])
            self.assertEqual(len(report["comparisons"]), 2)
            self.assertEqual(report["classification"]["result"], "inconclusive")
            self.assertEqual(report["classification"]["comparison_supports"], [True, False])

    def test_cli_writes_traceable_report_and_only_ineligible_input_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifacts = self.make_artifacts(root)
            self.set_pair_results(artifacts, range(50), range(70))
            report_path = root / "evaluation.json"
            stdout = io.StringIO()
            with patch.object(
                sys,
                "argv",
                ["mark2.run", "evaluate-experiment", *(str(path) for path in artifacts), "--output", str(report_path)],
            ), patch.object(sys, "stdout", stdout):
                self.assertEqual(run.main(), 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report, json.loads(report_path.read_text(encoding="utf-8")))
            self.assertEqual(report["classification"]["result"], "supported")
            self.assertEqual(report["experiment_id"], "example-controlled-experiment-v1")
            self.assertEqual(report["hypothesis_id"], "example-hypothesis-not-evaluated")
            self.assertEqual(report["run_ids"], ["baseline-1", "baseline-2", "variant-1", "variant-2"])
            self.assertEqual(set(report["pair_sources"]), {"baseline", "variant"})
            self.assertEqual(len(report["experiment_contract_sha256"]), 64)

            manifest_path = artifacts[3] / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["runtime"]["cuda"] = "12.9"
            run.write_json(manifest_path, manifest)
            ineligible = run.evaluate_experiment_artifacts(*artifacts)
            self.assertFalse(ineligible["eligible"])
            self.assertIn("qualification", ineligible)
            self.assertNotIn("comparisons", ineligible)
            self.assertNotIn("classification", ineligible)
            with patch.object(
                sys,
                "argv",
                ["mark2.run", "evaluate-experiment", *(str(path) for path in artifacts)],
            ), patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(run.main(), 1)


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
