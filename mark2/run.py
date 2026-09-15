"""Validate, run, and compare the pinned Mark2 baseline contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .config import read_config, sha256_json, validate_run_id
from .environment import collect, command


PACKAGE_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_DIR.parent
DEFAULT_CONFIG = PACKAGE_DIR / "configs" / "qwen35_9b_mmlu.json"
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


def _snapshot(run_dir: Path) -> dict[str, str]:
    source_dir = run_dir / "source"
    source_dir.mkdir()
    hashes = {}
    for source in (PACKAGE_DIR / "config.py", PACKAGE_DIR / "environment.py", PACKAGE_DIR / "run.py", PACKAGE_DIR / "requirements.txt"):
        target = source_dir / source.name
        shutil.copyfile(source, target)
        hashes[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    return hashes


def execute_run(config: dict[str, Any], config_path: Path, output_root: Path, run_id: str, backend: Any) -> Path:
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
        "git_commit": command(["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"]),
        "git_status": command(["git", "-C", str(REPOSITORY_ROOT), "status", "--porcelain"]),
        "environment": collect(run_dir),
        "source_sha256": _snapshot(run_dir),
        "result_classification": "unverified" if backend.name == "transformers" else "mock-only",
    }
    write_json(run_dir / "manifest.json", manifest)
    started = time.perf_counter()
    try:
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


def _predictions(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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
    run = commands.add_parser("run", help="run evaluation and always preserve a manifest")
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run.add_argument("--backend", choices=("mock", "transformers"), default="transformers")
    run.add_argument("--output-root", type=Path, default=Path("artifacts/mark2"))
    run.add_argument("--run-id", help="unique artifact directory name")
    compare = commands.add_parser("compare", help="apply the configured reproducibility tolerance to two runs")
    compare.add_argument("first", type=Path)
    compare.add_argument("second", type=Path)
    compare.add_argument("--output", type=Path)
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

        config = read_config(args.config)
        run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
        backend = MockBackend() if args.backend == "mock" else TransformersBackend()
        run_dir = execute_run(config, args.config, args.output_root, run_id, backend)
        print(run_dir)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
