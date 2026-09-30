"""Validate, run, and compare the pinned Mark2 baseline contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .config import read_config, sha256_json, validate_config, validate_run_id
from .environment import SystemProbe, collect, command, evaluate_preflight, read_profile


PACKAGE_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_DIR.parent
DEFAULT_CONFIG = PACKAGE_DIR / "configs" / "qwen35_9b_mmlu.json"
DEFAULT_PROFILE = PACKAGE_DIR / "configs" / "qwen35_9b_l4_profile.json"
ANSWER = re.compile(r"(?<![A-Za-z])([A-D])(?![A-Za-z])", re.IGNORECASE)


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def question_hash(row: dict[str, Any]) -> str:
    stable = {"question": row["question"], "choices": list(row["choices"]), "answer": int(row["answer"])}
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def select_rows(rows: Iterable[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    keyed = [(question_hash(row), row) for row in rows]
    keyed.sort(key=lambda item: item[0])
    if len(keyed) < limit:
        raise ValueError(f"dataset contains {len(keyed)} rows, fewer than sample_size={limit}")
    return [row for _, row in keyed[:limit]]


def render_prompt(row: dict[str, Any], template: str) -> str:
    choices = "\n".join(f"{letter}. {choice}" for letter, choice in zip("ABCD", row["choices"]))
    return template.format(question=row["question"], choices=choices)


def tokenize_prompt(tokenizer: Any, prompt: str) -> Any:
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
        enable_thinking=False,
    )


def parse_answer(text: str) -> str | None:
    match = ANSWER.search(text)
    return match.group(1).upper() if match else None


def aggregate(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(predictions)
    correct = sum(bool(row["correct"]) for row in predictions)
    parsed = sum(row["prediction"] is not None for row in predictions)
    return {
        "metric": "exact_match_accuracy",
        "accuracy": correct / total if total else None,
        "correct": correct,
        "total": total,
        "parsed": parsed,
        "unparseable": total - parsed,
    }


class MockBackend:
    name = "mock"

    _ROWS = [
        {"question": "What is 2 + 2?", "choices": ["3", "4", "5", "6"], "answer": 1, "subject": "mock_math"},
        {"question": "Which letter follows A?", "choices": ["B", "C", "D", "E"], "answer": 0, "subject": "mock_logic"},
        {"question": "Water freezes at 0 degrees on which scale?", "choices": ["Kelvin", "Celsius", "Fahrenheit", "Rankine"], "answer": 1, "subject": "mock_science"},
        {"question": "Which is a mammal?", "choices": ["Trout", "Frog", "Whale", "Lizard"], "answer": 2, "subject": "mock_biology"},
    ]

    def run(self, config: dict[str, Any], manifest: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
        manifest["runtime"] = {"backend": self.name, "scope": "offline bookkeeping test; not a baseline result"}
        predictions = []
        for row in self._ROWS:
            target = "ABCD"[row["answer"]]
            output = f"Answer: {target}"
            predictions.append(make_prediction(row, output, 0.0))
        return predictions


class TransformersBackend:
    name = "transformers"

    def run(self, config: dict[str, Any], manifest: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
        try:
            import torch
            from datasets import load_dataset
            from transformers import AutoModelForMultimodalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("install the exact versions in mark2/requirements.txt") from exc
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required; refusing to download 19.3 GB of weights on a CPU-only host")
        if not torch.cuda.is_bf16_supported():
            raise RuntimeError("the baseline contract requires a BF16-capable CUDA GPU")
        if torch.cuda.device_count() != 1:
            raise RuntimeError("the primary contract requires exactly one CUDA GPU")

        model_cfg = config["model"]
        data_cfg = config["dataset"]
        generation = config["generation"]
        torch.manual_seed(generation["seed"])
        torch.cuda.manual_seed_all(generation["seed"])
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        manifest["runtime"] = {
            "backend": self.name,
            "dtype": "bfloat16",
            "quantization": None,
            "tf32": False,
            "cuda": torch.version.cuda,
            "gpu_count": torch.cuda.device_count(),
            "gpu_names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        }

        dataset = load_dataset(
            data_cfg["id"], data_cfg["config"], split=data_cfg["split"], revision=data_cfg["revision"]
        )
        rows = select_rows((dict(row) for row in dataset), data_cfg["sample_size"])
        hashes = [question_hash(row) for row in rows]
        manifest["dataset_selection"] = {
            "count": len(rows),
            "question_hashes": hashes,
            "sha256": hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest(),
        }

        kwargs = {
            "revision": model_cfg["revision"],
            "trust_remote_code": model_cfg["trust_remote_code"],
        }
        # MMLU is text-only. Loading the tokenizer directly keeps this runner
        # independent of torchvision/Pillow, which AutoProcessor would require
        # for the model's unused vision path.
        tokenizer = AutoTokenizer.from_pretrained(model_cfg["id"], **kwargs)
        chat_template = tokenizer.get_chat_template()
        (run_dir / "chat_template.txt").write_text(chat_template, encoding="utf-8")
        manifest["chat_template_sha256"] = hashlib.sha256(chat_template.encode("utf-8")).hexdigest()
        for index in range(torch.cuda.device_count()):
            torch.cuda.reset_peak_memory_stats(index)
        started = time.perf_counter()
        model = AutoModelForMultimodalLM.from_pretrained(
            model_cfg["id"], **kwargs, dtype=torch.bfloat16, device_map={"": 0}
        )
        model.eval()
        resolved_model_config = model.config.to_dict()
        write_json(run_dir / "model_config.json", resolved_model_config)
        manifest["model_config_sha256"] = sha256_json(resolved_model_config)
        manifest["model_load_seconds"] = time.perf_counter() - started

        predictions = []
        for index, row in enumerate(rows):
            prompt = render_prompt(row, config["prompt"]["template"])
            inputs = tokenize_prompt(tokenizer, prompt)
            input_length = inputs["input_ids"].shape[-1]
            if input_length > generation["max_input_tokens"]:
                raise ValueError(
                    f"formatted input has {input_length} tokens, exceeding max_input_tokens="
                    f"{generation['max_input_tokens']}; truncation is forbidden"
                )
            inputs = inputs.to(model.device)
            torch.cuda.synchronize()
            started = time.perf_counter()
            with torch.inference_mode():
                output = model.generate(
                    **inputs,
                    do_sample=False,
                    num_beams=1,
                    max_new_tokens=generation["max_new_tokens"],
                    use_cache=True,
                )
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - started
            output_ids = output[0, input_length:]
            output_text = tokenizer.decode(output_ids, skip_special_tokens=True)
            prediction = make_prediction(row, output_text, elapsed)
            prediction["index"] = index
            prediction["input_tokens"] = int(input_length)
            prediction["output_tokens"] = int(output_ids.numel())
            predictions.append(prediction)
            del inputs, output, output_ids

        manifest["gpu_peak_allocated_bytes"] = [
            torch.cuda.max_memory_allocated(index) for index in range(torch.cuda.device_count())
        ]
        manifest["gpu_peak_reserved_bytes"] = [
            torch.cuda.max_memory_reserved(index) for index in range(torch.cuda.device_count())
        ]
        return predictions


def make_prediction(row: dict[str, Any], output_text: str, elapsed: float) -> dict[str, Any]:
    target = "ABCD"[int(row["answer"])]
    predicted = parse_answer(output_text)
    return {
        "question_sha256": question_hash(row),
        "subject": row.get("subject"),
        "target": target,
        "prediction": predicted,
        "correct": predicted == target,
        "output_text": output_text,
        "generation_seconds": elapsed,
    }


def _snapshot_sources(profile_path: Path = DEFAULT_PROFILE) -> tuple[Path, ...]:
    return (
        PACKAGE_DIR / "config.py",
        PACKAGE_DIR / "environment.py",
        PACKAGE_DIR / "run.py",
        PACKAGE_DIR / "requirements.txt",
        profile_path,
    )


def _snapshot(run_dir: Path, profile_path: Path = DEFAULT_PROFILE) -> dict[str, str]:
    source_dir = run_dir / "source"
    source_dir.mkdir()
    hashes = {}
    for source in _snapshot_sources(profile_path):
        target = source_dir / source.name
        shutil.copyfile(source, target)
        hashes[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    return hashes


def _committed_source_hashes(commit: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Read snapshot sources from the recorded repository commit."""
    hashes: dict[str, str] = {}
    errors: list[dict[str, Any]] = []
    for source in _snapshot_sources():
        try:
            repository_path = source.relative_to(REPOSITORY_ROOT).as_posix()
            result = subprocess.run(
                ["git", "-C", str(REPOSITORY_ROOT), "show", f"{commit}:{repository_path}"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            errors.append({"filename": source.name, "error": type(exc).__name__})
            continue
        if result.returncode:
            errors.append({"filename": source.name, "error": "not present at recorded commit"})
            continue
        hashes[source.name] = hashlib.sha256(result.stdout).hexdigest()
    return hashes, errors


def _command_evidence(args: list[str]) -> Any:
    """Store successful command output as text and preserve failures for rejection."""
    result = command(args)
    return result.get("output") if result.get("status") == "ok" else result


def execute_run(
    config: dict[str, Any],
    config_path: Path,
    output_root: Path,
    run_id: str,
    backend: Any,
    *,
    expected_commit: str | None = None,
    profile_path: Path = DEFAULT_PROFILE,
    preflight_probe: SystemProbe | None = None,
) -> Path:
    validate_run_id(run_id)
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(config_path, run_dir / "contract.json")
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "backend": backend.name,
        "contract_sha256": sha256_json(config),
        "contract": config,
        "git_commit": _command_evidence(["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"]),
        "git_status": _command_evidence(
            ["git", "-C", str(REPOSITORY_ROOT), "status", "--porcelain", "--untracked-files=no"]
        ),
        "environment": collect(run_dir),
        "source_sha256": _snapshot(run_dir, profile_path),
        "result_classification": "unverified" if backend.name == "transformers" else "mock-only",
    }
    write_json(run_dir / "manifest.json", manifest)
    started = time.perf_counter()
    try:
        if backend.name == "transformers":
            if expected_commit is None:
                raise ValueError("--expected-commit is required for transformers runs")
            profile = read_profile(profile_path)
            probe = preflight_probe or SystemProbe(REPOSITORY_ROOT, run_dir)
            preflight = evaluate_preflight(profile, expected_commit, probe)
            write_json(run_dir / "preflight.json", preflight)
            manifest["preflight"] = {
                "passed": preflight["passed"],
                "report": "preflight.json",
                "profile": str(profile_path),
            }
            if not preflight["passed"]:
                failed = [item["name"] for item in preflight["checks"] if not item["passed"]]
                raise RuntimeError(f"host preflight failed: {', '.join(failed)}")
        predictions = backend.run(config, manifest, run_dir)
        with (run_dir / "predictions.jsonl").open("x", encoding="utf-8") as handle:
            for row in predictions:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        manifest["metrics"] = aggregate(predictions)
        manifest["status"] = "completed"
        if backend.name == "transformers":
            manifest["result_classification"] = "repository-measured"
    except BaseException as exc:
        manifest["status"] = "failed"
        manifest["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        manifest["elapsed_seconds"] = time.perf_counter() - started
        manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(run_dir / "manifest.json", manifest)
    return run_dir


def execute_preflight(
    profile_path: Path,
    expected_commit: str,
    output_root: Path,
    run_id: str,
    probe: SystemProbe | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Create a unique preflight artifact even when validation fails."""
    validate_run_id(run_id)
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    profile = read_profile(profile_path)
    report = evaluate_preflight(profile, expected_commit, probe or SystemProbe(REPOSITORY_ROOT, run_dir))
    report_path = run_dir / "preflight.json"
    write_json(report_path, report)
    return report_path, report


def _predictions(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _qualification_check(
    checks: list[dict[str, Any]], name: str, expected: Any, actual: Any, passed: bool, reason: str
) -> None:
    checks.append({"name": name, "expected": expected, "actual": actual, "passed": passed, "reason": reason})


def _read_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(value, dict):
        return None, "top-level value must be an object"
    return value, None


def _read_prediction_rows(path: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not all(isinstance(value, dict) for value in values):
        return None, "every JSONL value must be an object"
    return values, None


def _required_fields(value: dict[str, Any] | None, schema: dict[str, Any]) -> list[str]:
    if value is None:
        return list(schema)
    invalid = []
    for name, expected_type in schema.items():
        item = value.get(name)
        if not isinstance(item, expected_type) or (expected_type is int and isinstance(item, bool)):
            invalid.append(name)
    return invalid


class _SavedProbe:
    def __init__(self, observed: dict[str, Any]):
        self.observed = observed

    def snapshot(self) -> dict[str, Any]:
        return self.observed


def qualify_baseline_runs(first: Path, second: Path) -> dict[str, Any]:
    """Validate whether two artifacts are admissible repository-measured baselines."""
    fixed_contract = read_config(DEFAULT_CONFIG)
    fixed_profile = read_profile(DEFAULT_PROFILE)
    fixed_contract_hash = sha256_json(fixed_contract)
    fixed_profile_hash = sha256_json(fixed_profile)
    paths = (first, second)
    checks: list[dict[str, Any]] = []
    manifests: list[dict[str, Any] | None] = []
    preflights: list[dict[str, Any] | None] = []
    predictions: list[list[dict[str, Any]] | None] = []

    manifest_schema = {
        "schema_version": int,
        "run_id": str,
        "status": str,
        "backend": str,
        "result_classification": str,
        "contract_sha256": str,
        "contract": dict,
        "git_commit": str,
        "git_status": str,
        "environment": dict,
        "source_sha256": dict,
        "dataset_selection": dict,
        "chat_template_sha256": str,
        "model_config_sha256": str,
        "runtime": dict,
        "metrics": dict,
        "preflight": dict,
    }
    prediction_schema = {
        "question_sha256": str,
        "subject": str,
        "target": str,
        "prediction": (str, type(None)),
        "correct": bool,
        "output_text": str,
        "generation_seconds": (int, float),
        "index": int,
        "input_tokens": int,
        "output_tokens": int,
    }

    for index, path in enumerate(paths, 1):
        prefix = f"run{index}"
        manifest, manifest_error = _read_json_object(path / "manifest.json")
        contract, contract_error = _read_json_object(path / "contract.json")
        preflight, preflight_error = _read_json_object(path / "preflight.json")
        rows, predictions_error = _read_prediction_rows(path / "predictions.jsonl")
        manifests.append(manifest)
        preflights.append(preflight)
        predictions.append(rows)

        for kind, error in (
            ("manifest", manifest_error),
            ("contract", contract_error),
            ("preflight", preflight_error),
            ("predictions", predictions_error),
        ):
            _qualification_check(
                checks, f"{prefix}.{kind}_readable", "valid data", error, error is None, f"{kind} artifact must be readable"
            )

        missing = _required_fields(manifest, manifest_schema)
        _qualification_check(
            checks, f"{prefix}.manifest_schema", [], missing, not missing, "manifest must contain every required field with the expected type"
        )
        if manifest is None:
            continue

        manifest_values_valid = (
            manifest.get("schema_version") == 1
            and isinstance(manifest.get("run_id"), str)
            and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", manifest["run_id"]))
            and isinstance(manifest.get("git_commit"), str)
            and bool(re.fullmatch(r"[0-9a-f]{40}", manifest["git_commit"]))
            and isinstance(manifest.get("contract_sha256"), str)
            and bool(re.fullmatch(r"[0-9a-f]{64}", manifest["contract_sha256"]))
            and isinstance(manifest.get("runtime"), dict)
            and manifest["runtime"].get("backend") == "transformers"
        )
        _qualification_check(
            checks,
            f"{prefix}.manifest_values",
            "valid schema version, IDs, hashes, and runtime backend",
            None if manifest_values_valid else "one or more values are invalid",
            manifest_values_valid,
            "manifest identifiers, hashes, and runtime must use the emitted formats",
        )

        for name, expected in (
            ("status", "completed"),
            ("backend", "transformers"),
            ("result_classification", "repository-measured"),
        ):
            _qualification_check(
                checks, f"{prefix}.{name}", expected, manifest.get(name), manifest.get(name) == expected, f"{name} must identify a completed measured run"
            )
        preflight_reference = manifest.get("preflight")
        preflight_checks = preflight.get("checks") if isinstance(preflight, dict) else None
        saved_profile = preflight.get("profile") if isinstance(preflight, dict) else None
        expected_commit = preflight.get("expected_commit") if isinstance(preflight, dict) else None
        observed = preflight.get("observed") if isinstance(preflight, dict) else None
        reevaluated_checks = None
        try:
            if isinstance(saved_profile, dict) and isinstance(expected_commit, str) and isinstance(observed, dict):
                reevaluated_checks = evaluate_preflight(
                    saved_profile, expected_commit, _SavedProbe(observed)
                )["checks"]
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            pass
        reference_valid = (
            isinstance(preflight_reference, dict)
            and preflight_reference.get("passed") is True
            and preflight_reference.get("report") == "preflight.json"
            and isinstance(preflight, dict)
            and preflight.get("passed") is True
            and isinstance(preflight_checks, list)
            and bool(preflight_checks)
            and all(
                isinstance(item, dict)
                and set(item) == {"name", "expected", "actual", "passed", "reason"}
                and item.get("passed") is True
                for item in preflight_checks
            )
            and preflight_checks == reevaluated_checks
        )
        _qualification_check(
            checks, f"{prefix}.preflight_passed", True, preflight_reference, reference_valid, "manifest and saved preflight must show every host check passed"
        )

        runtime = manifest.get("runtime")
        accelerator = observed.get("accelerator") if isinstance(observed, dict) else None
        observed_gpus = accelerator.get("gpus") if isinstance(accelerator, dict) else None
        observed_gpu_names = (
            [gpu.get("name") for gpu in observed_gpus]
            if isinstance(observed_gpus, list)
            and all(isinstance(gpu, dict) and isinstance(gpu.get("name"), str) for gpu in observed_gpus)
            else None
        )
        runtime_fields = {"backend", "dtype", "quantization", "tf32", "cuda", "gpu_count", "gpu_names"}
        runtime_valid = (
            isinstance(runtime, dict)
            and set(runtime) == runtime_fields
            and runtime.get("backend") == "transformers"
            and runtime.get("dtype") == "bfloat16"
            and runtime.get("quantization") is None
            and runtime.get("tf32") is False
            and isinstance(runtime.get("cuda"), str)
            and bool(re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", runtime["cuda"]))
            and isinstance(runtime.get("gpu_count"), int)
            and not isinstance(runtime.get("gpu_count"), bool)
            and isinstance(runtime.get("gpu_names"), list)
            and all(isinstance(name, str) for name in runtime["gpu_names"])
            and isinstance(accelerator, dict)
            and runtime.get("gpu_count") == accelerator.get("gpu_count")
            and runtime.get("gpu_count") == len(runtime["gpu_names"])
            and runtime.get("gpu_names") == observed_gpu_names
        )
        _qualification_check(
            checks,
            f"{prefix}.runtime_consistency",
            {
                "fields": sorted(runtime_fields),
                "backend": "transformers",
                "dtype": "bfloat16",
                "quantization": None,
                "tf32": False,
                "cuda": "non-empty CUDA version",
                "gpu_count": accelerator.get("gpu_count") if isinstance(accelerator, dict) else None,
                "gpu_names": observed_gpu_names,
            },
            runtime,
            runtime_valid,
            "runtime precision and accelerator evidence must match the runner contract and saved preflight",
        )

        contract_valid = contract is not None
        contract_reason = None
        if contract_valid:
            try:
                validate_config(contract)
            except (KeyError, TypeError, ValueError) as exc:
                contract_valid, contract_reason = False, str(exc)
        _qualification_check(
            checks, f"{prefix}.contract_schema", "valid Mark2 contract", contract_reason, contract_valid, "saved contract must satisfy the pinned contract schema"
        )
        hashes_match = contract is not None and manifest.get("contract") == contract and manifest.get("contract_sha256") == sha256_json(contract)
        _qualification_check(
            checks, f"{prefix}.contract_integrity", True, hashes_match, hashes_match, "contract file, embedded contract, and declared hash must agree"
        )
        contract_fixed = contract == fixed_contract and manifest.get("contract_sha256") == fixed_contract_hash
        _qualification_check(
            checks,
            f"{prefix}.fixed_contract",
            fixed_contract_hash,
            sha256_json(contract) if contract is not None else None,
            contract_fixed,
            "saved contract must exactly match the repository's preregistered contract",
        )

        profile_fixed = saved_profile == fixed_profile
        _qualification_check(
            checks,
            f"{prefix}.fixed_profile",
            fixed_profile_hash,
            sha256_json(saved_profile) if isinstance(saved_profile, dict) else None,
            profile_fixed,
            "saved execution profile must exactly match the repository's approved profile",
        )

        source_hashes = manifest.get("source_sha256")
        expected_sources = {source.name for source in _snapshot_sources()}
        committed_hashes, committed_source_errors = _committed_source_hashes(manifest.get("git_commit", ""))
        declared_sources = set(source_hashes) if isinstance(source_hashes, dict) else set()
        source_dir = path / "source"
        try:
            actual_sources = {entry.name for entry in source_dir.iterdir()} if source_dir.is_dir() else set()
        except OSError:
            actual_sources = set()
        invalid_sources = []
        if declared_sources != expected_sources:
            invalid_sources.append(
                {
                    "manifest_filenames": sorted(declared_sources),
                    "required_filenames": sorted(expected_sources),
                }
            )
        if actual_sources != expected_sources:
            invalid_sources.append(
                {
                    "artifact_filenames": sorted(actual_sources),
                    "required_filenames": sorted(expected_sources),
                }
            )
        if isinstance(source_hashes, dict) and source_hashes:
            for filename, expected_hash in source_hashes.items():
                source_path = path / "source" / filename
                if (
                    not isinstance(filename, str)
                    or Path(filename).name != filename
                    or not isinstance(expected_hash, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
                    or not source_path.is_file()
                    or source_path.is_symlink()
                ):
                    invalid_sources.append(filename)
                elif hashlib.sha256(source_path.read_bytes()).hexdigest() != expected_hash:
                    invalid_sources.append(filename)
        else:
            invalid_sources.append("source_sha256")
        if committed_source_errors:
            invalid_sources.extend(committed_source_errors)
        if committed_hashes != source_hashes:
            invalid_sources.append(
                {
                    "recorded_commit_hashes": committed_hashes,
                    "manifest_hashes": source_hashes,
                }
            )
        _qualification_check(
            checks,
            f"{prefix}.source_integrity",
            [],
            invalid_sources,
            not invalid_sources,
            "source snapshot files must match the manifest and the repository files at the recorded commit",
        )

        row_errors = []
        hashes: list[str] = []
        if rows is not None:
            for row_index, row in enumerate(rows):
                invalid = _required_fields(row, prediction_schema)
                target, prediction, correct = row.get("target"), row.get("prediction"), row.get("correct")
                answer_choices = {"A", "B", "C", "D"}
                if not isinstance(target, str) or target not in answer_choices or (
                    prediction is not None and (not isinstance(prediction, str) or prediction not in answer_choices)
                ):
                    invalid.append("answer_value")
                if isinstance(correct, bool) and correct != (prediction == target):
                    invalid.append("correct_consistency")
                for integer_field in ("index", "input_tokens", "output_tokens"):
                    if isinstance(row.get(integer_field), int) and row[integer_field] < 0:
                        invalid.append(integer_field)
                if row.get("index") != row_index:
                    invalid.append("index_sequence")
                elapsed = row.get("generation_seconds")
                if isinstance(elapsed, bool) or (isinstance(elapsed, (int, float)) and elapsed < 0):
                    invalid.append("generation_seconds")
                if invalid:
                    row_errors.append({"row": row_index, "fields": sorted(set(invalid))})
                if isinstance(row.get("question_sha256"), str):
                    hashes.append(row["question_sha256"])
        _qualification_check(
            checks, f"{prefix}.prediction_schema", [], row_errors, rows is not None and not row_errors, "predictions must contain typed and internally consistent fields"
        )

        selection = manifest.get("dataset_selection")
        contract_dataset = contract.get("dataset") if isinstance(contract, dict) else None
        sample_size = contract_dataset.get("sample_size") if isinstance(contract_dataset, dict) else None
        hashes_are_valid = all(re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes)
        expected_selection_hash = hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest() if hashes and hashes_are_valid else None
        selection_valid = (
            isinstance(selection, dict)
            and rows is not None
            and len(rows) == sample_size
            and selection.get("count") == len(rows)
            and selection.get("question_hashes") == hashes
            and selection.get("sha256") == expected_selection_hash
            and len(set(hashes)) == len(hashes)
            and hashes_are_valid
        )
        _qualification_check(
            checks, f"{prefix}.dataset_selection_integrity", {"count": sample_size, "unique": True}, selection, selection_valid, "prediction count and unique question hashes must match the contract and selection manifest"
        )

        metrics = manifest.get("metrics")
        contract_metric = contract.get("metric") if isinstance(contract, dict) else None
        expected_metric_name = contract_metric.get("name") if isinstance(contract_metric, dict) else None
        metric_keys = {"metric", "accuracy", "correct", "total", "parsed", "unparseable"}
        count_fields = ("correct", "total", "parsed", "unparseable")
        metrics_schema_valid = (
            isinstance(metrics, dict)
            and set(metrics) == metric_keys
            and metrics.get("metric") == expected_metric_name
            and isinstance(metrics.get("accuracy"), (int, float))
            and not isinstance(metrics.get("accuracy"), bool)
            and math.isfinite(metrics["accuracy"])
            and 0 <= metrics["accuracy"] <= 1
            and all(isinstance(metrics.get(field), int) and not isinstance(metrics.get(field), bool) and metrics[field] >= 0 for field in count_fields)
        )
        recalculated = aggregate(rows) if rows is not None and not row_errors else None
        _qualification_check(
            checks,
            f"{prefix}.metric_integrity",
            recalculated,
            metrics,
            metrics_schema_valid and metrics == recalculated and recalculated is not None,
            "manifest metrics must have the exact typed schema and equal metrics recalculated from predictions",
        )

        chat_path, model_path = path / "chat_template.txt", path / "model_config.json"
        chat_hash = hashlib.sha256(chat_path.read_bytes()).hexdigest() if chat_path.is_file() else None
        model_config, _ = _read_json_object(model_path)
        model_hash = sha256_json(model_config) if model_config is not None else None
        content_hashes_valid = chat_hash == manifest.get("chat_template_sha256") and model_hash == manifest.get("model_config_sha256")
        _qualification_check(
            checks, f"{prefix}.model_artifact_integrity", True, {"chat_template_sha256": chat_hash, "model_config_sha256": model_hash}, content_hashes_valid, "chat template and model config files must match their manifest hashes"
        )
        preflight_commit = preflight.get("expected_commit") if isinstance(preflight, dict) else None
        observed = preflight.get("observed") if isinstance(preflight, dict) else None
        observed_commit = observed.get("git_commit") if isinstance(observed, dict) else None
        commit_consistent = manifest.get("git_commit") == preflight_commit == observed_commit
        _qualification_check(
            checks,
            f"{prefix}.commit_preflight_consistency",
            manifest.get("git_commit"),
            {"expected_commit": preflight_commit, "observed_git_commit": observed_commit},
            commit_consistent,
            "manifest commit must equal the approved and observed preflight commit",
        )

    resolved = [str(path.resolve()) for path in paths]
    run_ids = [item.get("run_id") if item else None for item in manifests]
    _qualification_check(checks, "pair.distinct_artifact_directories", True, resolved, resolved[0] != resolved[1], "runs must use different artifact directories")
    _qualification_check(checks, "pair.distinct_run_ids", "different values", run_ids, None not in run_ids and run_ids[0] != run_ids[1], "runs must have independent run IDs")

    pair_fields = (
        "contract_sha256",
        "git_commit",
        "source_sha256",
        "dataset_selection",
        "chat_template_sha256",
        "model_config_sha256",
        "runtime",
    )
    for field in pair_fields:
        actual = [item.get(field) if item else None for item in manifests]
        _qualification_check(checks, f"pair.same_{field}", "identical", actual, actual[0] is not None and actual[0] == actual[1], f"both runs must use the same {field}")
    statuses = [item.get("git_status") if item else None for item in manifests]
    _qualification_check(checks, "pair.clean_tracked_tree", ["", ""], statuses, statuses == ["", ""], "both runs must record a clean tracked worktree")

    fixed_host = []
    for preflight in preflights:
        observed = preflight.get("observed") if isinstance(preflight, dict) else None
        fixed_host.append({
            "profile": preflight.get("profile") if isinstance(preflight, dict) else None,
            "python_version": observed.get("python_version") if isinstance(observed, dict) else None,
            "packages": observed.get("packages") if isinstance(observed, dict) else None,
            "accelerator": observed.get("accelerator") if isinstance(observed, dict) else None,
        })
    _qualification_check(checks, "pair.same_fixed_environment", "identical", fixed_host, fixed_host[0] == fixed_host[1] and fixed_host[0]["profile"] is not None, "dependency, Python, GPU, and execution profile conditions must match")

    signatures = []
    for rows in predictions:
        signatures.append([(row.get("question_sha256"), row.get("prediction")) for row in rows] if rows else None)
    identical = signatures[0] is not None and signatures[0] == signatures[1]
    first_contract = manifests[0].get("contract") if isinstance(manifests[0], dict) else None
    metric = first_contract.get("metric") if isinstance(first_contract, dict) else None
    tolerance = metric.get("reproducibility") if isinstance(metric, dict) else None
    if not isinstance(tolerance, dict):
        tolerance = {}
    accuracies = [item.get("metrics", {}).get("accuracy") if item and isinstance(item.get("metrics"), dict) else None for item in manifests]
    accuracy_delta = abs(accuracies[0] - accuracies[1]) if all(isinstance(value, (int, float)) for value in accuracies) else None
    max_delta = tolerance.get("max_accuracy_delta")
    accuracy_passed = isinstance(accuracy_delta, (int, float)) and isinstance(max_delta, (int, float)) and accuracy_delta <= max_delta
    _qualification_check(checks, "pair.identical_predictions", tolerance.get("require_identical_predictions"), identical, identical or tolerance.get("require_identical_predictions") is False, "prediction signatures must satisfy the preregistered condition")
    _qualification_check(checks, "pair.accuracy_delta", {"maximum": max_delta}, accuracy_delta, accuracy_passed, "accuracy difference must satisfy the preregistered tolerance")

    return {
        "schema_version": 1,
        "mode": "repository-measured-baseline-qualification",
        "run_ids": run_ids,
        "eligible": all(item["passed"] for item in checks),
        "checks": checks,
    }


def compare_runs(first: Path, second: Path) -> dict[str, Any]:
    manifests = [json.loads((path / "manifest.json").read_text(encoding="utf-8")) for path in (first, second)]
    if any(item.get("status") != "completed" for item in manifests):
        raise ValueError("both runs must be completed")
    same_contract = manifests[0]["contract_sha256"] == manifests[1]["contract_sha256"]
    first_rows, second_rows = _predictions(first / "predictions.jsonl"), _predictions(second / "predictions.jsonl")
    first_signature = [(row["question_sha256"], row["prediction"]) for row in first_rows]
    second_signature = [(row["question_sha256"], row["prediction"]) for row in second_rows]
    identical = first_signature == second_signature
    accuracy_delta = abs(manifests[0]["metrics"]["accuracy"] - manifests[1]["metrics"]["accuracy"])
    tolerance = manifests[0]["contract"]["metric"]["reproducibility"]
    passed = same_contract and accuracy_delta <= tolerance["max_accuracy_delta"]
    if tolerance["require_identical_predictions"]:
        passed = passed and identical
    return {
        "schema_version": 1,
        "run_ids": [manifests[0]["run_id"], manifests[1]["run_id"]],
        "same_contract": same_contract,
        "accuracy_delta": accuracy_delta,
        "identical_predictions": identical,
        "tolerance": tolerance,
        "reproducible": passed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-config", help="validate the contract without ML imports or downloads")
    check.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    preflight = commands.add_parser("preflight", help="validate the host without model or dataset downloads")
    preflight.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    preflight.add_argument("--expected-commit", required=True)
    preflight.add_argument("--output-root", type=Path, default=Path("artifacts/mark2"))
    preflight.add_argument("--run-id", help="unique artifact directory name")
    run = commands.add_parser("run", help="run evaluation and always preserve a manifest")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run.add_argument("--backend", choices=("mock", "transformers"), default="transformers")
    run.add_argument("--output-root", type=Path, default=Path("artifacts/mark2"))
    run.add_argument("--run-id", help="unique artifact directory name")
    run.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    run.add_argument("--expected-commit", help="approved repository commit; required by transformers backend")
    compare = commands.add_parser("compare", help="apply the configured reproducibility tolerance to two runs")
    compare.add_argument("first", type=Path)
    compare.add_argument("second", type=Path)
    compare.add_argument("--output", type=Path)
    qualify = commands.add_parser("qualify", help="validate two repository-measured baseline artifacts")
    qualify.add_argument("first", type=Path)
    qualify.add_argument("second", type=Path)
    qualify.add_argument("--output", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "check-config":
            config = read_config(args.config)
            print(json.dumps({"valid": True, "contract_sha256": sha256_json(config)}, indent=2))
            return 0
        if args.command == "compare":
            result = compare_runs(args.first, args.second)
            payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("x", encoding="utf-8") as handle:
                    handle.write(payload)
            print(payload, end="")
            return 0 if result["reproducible"] else 1
        if args.command == "qualify":
            result = qualify_baseline_runs(args.first, args.second)
            payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("x", encoding="utf-8") as handle:
                    handle.write(payload)
            print(payload, end="")
            return 0 if result["eligible"] else 1

        if args.command == "preflight":
            run_id = args.run_id or datetime.now(timezone.utc).strftime("preflight-%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
            report_path, report = execute_preflight(
                args.profile, args.expected_commit, args.output_root, run_id
            )
            print(report_path)
            return 0 if report["passed"] else 1

        config = read_config(args.config)
        run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
        backend = MockBackend() if args.backend == "mock" else TransformersBackend()
        run_dir = execute_run(
            config,
            args.config,
            args.output_root,
            run_id,
            backend,
            expected_commit=args.expected_commit,
            profile_path=args.profile,
        )
        print(run_dir)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
