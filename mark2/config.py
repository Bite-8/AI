"""Load and validate the immutable Mark2 evaluation contract."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} must contain exactly: {', '.join(sorted(expected))}")
    return value


def _full_sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not FULL_SHA.fullmatch(value):
        raise ValueError(f"{label} must be a full 40-character lowercase commit SHA")


def validate_config(config: Any) -> dict[str, Any]:
    config = _exact_keys(
        config,
        {"schema_version", "model", "dataset", "prompt", "generation", "metric"},
        "config",
    )
    if config["schema_version"] != 1:
        raise ValueError("schema_version must be 1")

    model = _exact_keys(
        config["model"],
        {"id", "revision", "license", "dtype", "quantization", "trust_remote_code", "class"},
        "model",
    )
    if model["id"] != "Qwen/Qwen3.8-27B":
        raise ValueError("this contract supports Qwen/Qwen3.8-27B only")
    _full_sha(model["revision"], "model.revision")
    if model["license"] != "Apache-2.0":
        raise ValueError("model.license must be Apache-2.0")
    if model["dtype"] != "bfloat16" or model["quantization"] is not None:
        raise ValueError("the primary contract requires unquantized bfloat16")
    if model["trust_remote_code"] is not False:
        raise ValueError("model.trust_remote_code must be false")
    if model["class"] != "AutoModelForMultimodalLM":
        raise ValueError("model.class must be AutoModelForMultimodalLM")

    dataset = _exact_keys(
        config["dataset"],
        {"id", "revision", "config", "split", "sample_size", "selection"},
        "dataset",
    )
    if dataset["id"] != "cais/mmlu" or dataset["config"] != "all" or dataset["split"] != "test":
        raise ValueError("dataset must be the all/test split of cais/mmlu")
    _full_sha(dataset["revision"], "dataset.revision")
    if type(dataset["sample_size"]) is not int or not 1 <= dataset["sample_size"] <= 1000:
        raise ValueError("dataset.sample_size must be an integer from 1 to 1000")
    if dataset["selection"] != "sha256-question-order-v1":
        raise ValueError("unsupported dataset.selection")

    prompt = _exact_keys(config["prompt"], {"template", "chat_template", "enable_thinking"}, "prompt")
    if not isinstance(prompt["template"], str) or {"{question}", "{choices}"} - set(
        re.findall(r"\{[^}]+\}", prompt["template"])
    ):
        raise ValueError("prompt.template must contain {question} and {choices}")
    if prompt["chat_template"] is not True or prompt["enable_thinking"] is not False:
        raise ValueError("the contract requires chat_template=true and enable_thinking=false")

    generation = _exact_keys(
        config["generation"],
        {"max_input_tokens", "max_new_tokens", "do_sample", "num_beams", "seed"},
        "generation",
    )
    if type(generation["max_input_tokens"]) is not int or not 1 <= generation["max_input_tokens"] <= 8192:
        raise ValueError("generation.max_input_tokens must be an integer from 1 to 8192")
    if type(generation["max_new_tokens"]) is not int or not 1 <= generation["max_new_tokens"] <= 16:
        raise ValueError("generation.max_new_tokens must be an integer from 1 to 16")
    if generation["do_sample"] is not False or generation["num_beams"] != 1:
        raise ValueError("the contract requires greedy generation")
    if type(generation["seed"]) is not int or not 0 <= generation["seed"] < 2**32:
        raise ValueError("generation.seed must be an unsigned 32-bit integer")

    metric = _exact_keys(
        config["metric"], {"name", "parser", "unparseable", "reproducibility"}, "metric"
    )
    if metric["name"] != "exact_match_accuracy" or metric["parser"] != "first_standalone_A_D":
        raise ValueError("unsupported metric or parser")
    if metric["unparseable"] != "incorrect":
        raise ValueError("metric.unparseable must be incorrect")
    repro = _exact_keys(
        metric["reproducibility"], {"max_accuracy_delta", "require_identical_predictions"}, "reproducibility"
    )
    if type(repro["max_accuracy_delta"]) not in (int, float) or not 0 <= repro["max_accuracy_delta"] <= 1:
        raise ValueError("max_accuracy_delta must be between 0 and 1")
    if not isinstance(repro["require_identical_predictions"], bool):
        raise ValueError("require_identical_predictions must be boolean")
    return config


def read_config(path: Path) -> dict[str, Any]:
    return validate_config(json.loads(path.read_text(encoding="utf-8")))


def validate_run_id(value: str) -> str:
    if not RUN_ID.fullmatch(value):
        raise ValueError("run ID must use 1-80 letters, digits, dot, underscore, or hyphen")
    return value
