from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np

from .decode import generate
from .model import NumpyTransformerLM, TransformerConfig
from .tokenizer import CharTokenizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mark1: NumPy Transformer forward + decode")
    parser.add_argument("--prompt", type=str, help="Input text (UTF-8)")
    parser.add_argument("--max-new-tokens", type=int, default=12)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--d-model", type=int, default=64)
    parser.add_argument("--n-heads", type=int, default=4)
    parser.add_argument("--n-layers", type=int, default=2)
    parser.add_argument("--d-ff", type=int, default=128)
    parser.add_argument("--max-seq-len", type=int, default=128)
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("logs"),
        help="Directory to store JSONL logs (default: logs)",
    )
    parser.add_argument("--run-id", type=str, default=None, help="Optional run id")
    return parser


def append_jsonl(log_dir: Path, payload: dict) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{datetime.now(timezone.utc):%Y%m%d}.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return log_path


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.prompt:
        parser.print_help()
        return 0

    run_id = args.run_id or f"mark1_{uuid4().hex[:8]}"

    base_corpus = [
        args.prompt,
        "transformer attention residual layernorm",
        "mark1 numpy implementation",
        "shape tracing is important",
    ]
    tokenizer = CharTokenizer.build_vocab(base_corpus)

    prompt_ids = tokenizer.encode(args.prompt, add_bos_eos=True)
    seq_len = len(prompt_ids)

    cfg = TransformerConfig(
        vocab_size=len(tokenizer.id_to_token),
        d_model=args.d_model,
        n_heads=args.n_heads,
        n_layers=args.n_layers,
        d_ff=args.d_ff,
        max_seq_len=args.max_seq_len,
    )
    model = NumpyTransformerLM(cfg, seed=args.seed)

    input_ids = np.array([prompt_ids], dtype=np.int64)
    logits, trace = model.forward(input_ids, return_trace=True)

    generated_ids = generate(
        model=model,
        prompt_ids=prompt_ids,
        max_new_tokens=args.max_new_tokens,
        eos_id=tokenizer.eos_id,
        temperature=args.temperature,
        seed=args.seed,
    )

    decoded_prompt = tokenizer.decode(prompt_ids, skip_special_tokens=True)
    decoded_generated = tokenizer.decode(generated_ids, skip_special_tokens=True)

    print("=== Mark1 Transformer Run ===")
    print(f"input_text        : {args.prompt}")
    print(f"prompt_token_ids  : {prompt_ids}")
    print(f"prompt_seq_len    : {seq_len}")
    print(f"forward_logits    : {list(logits.shape)}")
    print("\n--- Shape Trace ---")
    for row in trace:
        print(row)

    print("\n--- Generation ---")
    print(f"decoded_prompt    : {decoded_prompt}")
    print(f"generated_ids     : {generated_ids}")
    print(f"generated_text    : {decoded_generated}")

    log_row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "stage": "transformer_run",
        "input_text": args.prompt,
        "prompt_token_ids": prompt_ids,
        "seq_len": seq_len,
        "forward_logits_shape": list(logits.shape),
        "trace": trace,
        "generated_ids": generated_ids,
        "generated_text": decoded_generated,
        "notes": "numpy decoder-only transformer with causal self-attention",
    }
    log_path = append_jsonl(args.log_dir, log_row)
    print(f"\nlog_file          : {log_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
