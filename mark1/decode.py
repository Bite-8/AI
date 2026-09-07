from __future__ import annotations

from typing import List, Sequence

import numpy as np

from .model import NumpyTransformerLM


def _sample_from_logits(logits: np.ndarray, temperature: float, rng: np.random.Generator) -> int:
    if temperature <= 0.0:
        return int(np.argmax(logits))

    scaled = logits / temperature
    shifted = scaled - np.max(scaled)
    probs = np.exp(shifted)
    probs /= probs.sum()
    return int(rng.choice(len(probs), p=probs))


def generate(
    model: NumpyTransformerLM,
    prompt_ids: Sequence[int],
    max_new_tokens: int,
    eos_id: int,
    temperature: float = 0.0,
    seed: int = 42,
) -> List[int]:
    token_ids = list(prompt_ids)
    rng = np.random.default_rng(seed)

    for _ in range(max_new_tokens):
        input_ids = np.array([token_ids], dtype=np.int64)
        logits, _ = model.forward(input_ids, return_trace=False)
        next_logits = logits[0, -1]
        next_id = _sample_from_logits(next_logits, temperature=temperature, rng=rng)
        token_ids.append(next_id)
        if next_id == eos_id:
            break

    return token_ids
