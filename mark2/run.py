"""Run the pinned Qwen3.5 text backbone and save smoke-test artifacts."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .environment import collect, run_command

DEFAULT_CONFIG = Path(__file__).parent / "configs" / "qwen35_smoke.json"


def read_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    required = {"model_id", "revision", "seed", "max_input_tokens", "max_new_tokens", "repeats", "prompts"}
    if not isinstance(cfg, dict) or set(cfg) != required:
        raise ValueError("Config must contain exactly: " + ", ".join(sorted(required)))
    if cfg["model_id"] != "Qwen/Qwen3.5-0.8B":
        raise ValueError("This runner supports Qwen/Qwen3.5-0.8B only")
    if not isinstance(cfg["revision"], str) or not re.fullmatch(r"[0-9a-f]{40}", cfg["revision"]):
        raise ValueError("revision must be a full immutable commit SHA")
    for key, minimum, maximum in [("seed", 0, 2**32 - 1), ("max_input_tokens", 1, 512),
                                  ("max_new_tokens", 1, 128), ("repeats", 1, 3)]:
        if type(cfg[key]) is not int or not minimum <= cfg[key] <= maximum:
            raise ValueError(f"{key} must be an integer between {minimum} and {maximum}")
    prompts = cfg["prompts"]
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 10:
        raise ValueError("Provide 1 to 10 smoke-test prompts")
    seen = set()
    for item in prompts:
        if not isinstance(item, dict) or set(item) != {"id", "text"}:
            raise ValueError("Each prompt requires id and text")
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in seen:
            raise ValueError("Prompt IDs must be nonempty and unique")
        if not isinstance(item["text"], str) or not item["text"].strip():
            raise ValueError("Prompt text must be nonempty")
        seen.add(item["id"])
    return cfg


def write_json(path: Path, value: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def stop_reason(tokens: list[int], eos_ids: list[int], limit: int) -> str:
    if tokens and tokens[-1] in eos_ids:
        return "eos"
    return "max_new_tokens" if len(tokens) >= limit else "other"


def check_input_length(length: int, limit: int) -> None:
    if length > limit:
        raise ValueError(f"Chat-formatted input has {length} tokens; limit is {limit}. No truncation applied.")


def generate_rows(model, tokenizer, cfg, device, torch, generation_config):
    first_tokens = {}
    for repeat in range(cfg["repeats"]):
        for prompt in cfg["prompts"]:
            # Rebuild inputs and let generate create fresh cache for every trial.
            inputs = tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt["text"]}],
                tokenize=True, add_generation_prompt=True, enable_thinking=False,
                return_tensors="pt", return_dict=True,
            )
            length = inputs["input_ids"].shape[-1]
            check_input_length(length, cfg["max_input_tokens"])
            inputs = inputs.to(device)
            torch.manual_seed(cfg["seed"])
            torch.cuda.synchronize(device)
            torch.cuda.reset_peak_memory_stats(device)
            started = time.perf_counter()
            with torch.inference_mode():
                output = model.generate(**inputs, generation_config=generation_config)
            torch.cuda.synchronize(device)
            seconds = time.perf_counter() - started
            tokens = output[0, length:].tolist()
            reference = first_tokens.setdefault(prompt["id"], tokens)
            yield {
                "prompt_id": prompt["id"], "repeat": repeat,
                "prompt": prompt["text"], "input_tokens": length,
                "input_token_ids": inputs["input_ids"][0].tolist(),
                "output_tokens": len(tokens), "output_token_ids": tokens,
                "output_text": tokenizer.decode(tokens, skip_special_tokens=True),
                "stop_reason": stop_reason(tokens, generation_config.eos_token_id, cfg["max_new_tokens"]),
                "generation_seconds": seconds,
                "tokens_per_second": len(tokens) / seconds if seconds else None,
                "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
                "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved(device),
                "matches_first_repeat": tokens == reference if repeat else None,
            }
            del output, inputs


def execute(cfg: dict, run_dir: Path, manifest: dict) -> None:
    try:
        import torch
        from transformers import AutoTokenizer, GenerationConfig, Qwen3_5ForCausalLM
    except ImportError as exc:
        raise RuntimeError("Install mark2/requirements.txt on the GPU machine; see docs/mark2/RUNNING.md") from exc
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required. This command does not download model weights on CPU-only hosts.")
    device = torch.device("cuda:0")
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("This baseline requires BF16 support (planned GPU: L4).")
    torch.manual_seed(cfg["seed"])
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    model_kwargs = dict(revision=cfg["revision"], trust_remote_code=False)
    manifest["runtime"] = {
        "device": str(device), "gpu_name": torch.cuda.get_device_name(device),
        "cuda_runtime": torch.version.cuda, "dtype": "bfloat16",
        "attention_implementation": "eager", "tf32": False,
        "model_class": "Qwen3_5ForCausalLM", "enable_thinking": False,
        "scope": "Unmodified text backbone; vision tower not instantiated",
    }
    write_json(run_dir / "manifest.json", manifest)
    started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(cfg["model_id"], **model_kwargs)
    manifest["tokenizer_load_seconds"] = time.perf_counter() - started
    # Validate every prompt before downloading/loading the large weight files.
    for prompt in cfg["prompts"]:
        ids = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt["text"]}], tokenize=True,
            add_generation_prompt=True, enable_thinking=False,
        )
        check_input_length(len(ids), cfg["max_input_tokens"])
    torch.cuda.reset_peak_memory_stats(device)
    started = time.perf_counter()
    model, loading_info = Qwen3_5ForCausalLM.from_pretrained(
        cfg["model_id"], **model_kwargs, dtype=torch.bfloat16,
        device_map={"": str(device)}, attn_implementation="eager", output_loading_info=True,
    )
    write_json(run_dir / "loading_info.json", loading_info)
    if any(loading_info.get(key) for key in ("missing_keys", "mismatched_keys", "error_msgs")):
        raise RuntimeError("Checkpoint did not load completely; see loading_info.json")
    model.eval()
    torch.cuda.synchronize(device)
    manifest["model_load_seconds"] = time.perf_counter() - started
    manifest["model_load_peak_allocated_bytes"] = torch.cuda.max_memory_allocated(device)
    manifest["model_load_peak_reserved_bytes"] = torch.cuda.max_memory_reserved(device)
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else list(eos or [])
    if not eos:
        raise ValueError("Model has no EOS token configured")
    generation = GenerationConfig(
        do_sample=False, num_beams=1, max_new_tokens=cfg["max_new_tokens"],
        eos_token_id=eos, pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else eos[0],
        use_cache=True,
    )
    write_json(run_dir / "generation_config.json", generation.to_dict())
    write_json(run_dir / "model_config.json", model.config.to_dict())
    (run_dir / "chat_template.txt").write_text(tokenizer.get_chat_template(), encoding="utf-8")
    write_json(run_dir / "manifest.json", manifest)
    with (run_dir / "results.jsonl").open("x", encoding="utf-8") as handle:
        for row in generate_rows(model, tokenizer, cfg, device, torch, generation):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"[{row['prompt_id']} repeat={row['repeat']}] {row['output_text']}", flush=True)
    manifest["completed_trials"] = len(cfg["prompts"]) * cfg["repeats"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=Path("logs/mark2"))
    parser.add_argument("--check-config", action="store_true", help="Validate config only; no ML imports or downloads")
    args = parser.parse_args()
    try:
        cfg = read_config(args.config)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Invalid config: {exc}\n")
    if args.check_config:
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return 0
    run_dir = args.output_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "config.json", cfg)
    root = Path(__file__).resolve().parent.parent
    sources = run_dir / "source"
    sources.mkdir()
    source_hashes = {}
    for name in ("run.py", "environment.py", "requirements.txt"):
        src = Path(__file__).parent / name
        shutil.copyfile(src, sources / name)
        source_hashes[name] = hashlib.sha256(src.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1, "status": "running", "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": cfg, "source_sha256": source_hashes,
        "git_commit": run_command(["git", "-C", str(root), "rev-parse", "HEAD"]),
        "git_status": run_command(["git", "-C", str(root), "status", "--porcelain"]),
        "environment": collect(run_dir),
        "installed_packages": {d.metadata['Name']: d.version for d in importlib.metadata.distributions() if d.metadata['Name']},
        "notes": ["Smoke test, not a quality benchmark.",
                  "Generation includes prefill and decode; first trial is cold (no warmup).",
                  "GPU memory is PyTorch allocator memory, not whole-device or host RAM.",
                  "No EC2 lifecycle management. Ending this process does not stop the instance.",
                  "Greedy generation and fixed seed do not guarantee bitwise reproducibility."],
    }
    write_json(run_dir / "manifest.json", manifest)
    print(f"Artifacts: {run_dir}", flush=True)
    started = time.perf_counter()
    code = 0
    try:
        execute(cfg, run_dir, manifest)
        manifest["status"] = "completed"
    except (Exception, KeyboardInterrupt) as exc:
        manifest["status"] = "failed"
        manifest["error"] = {"type": type(exc).__name__, "message": str(exc)}
        print(f"Run failed: {exc}", file=sys.stderr)
        code = 1
    finally:
        manifest["elapsed_seconds"] = time.perf_counter() - started
        manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(run_dir / "manifest.json", manifest)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
