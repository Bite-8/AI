from __future__ import annotations

"""Minimal educational training example for Mark1.

This script updates only the LM head (W_vocab, b_vocab) with SGD so that
shape flow remains easy to follow without full backprop through Transformer.
"""

import numpy as np

from .model import NumpyTransformerLM, TransformerConfig
from .tokenizer import CharTokenizer


def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    shifted = x - np.max(x, axis=axis, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=axis, keepdims=True)


def run_demo_train(epochs: int = 30, lr: float = 0.1, seed: int = 42) -> None:
    corpus = ["hello transformer", "hello mark1", "shape trace"]
    tokenizer = CharTokenizer.build_vocab(corpus)

    text = "hello mark1"
    ids = tokenizer.encode(text, add_bos_eos=True)
    x_ids = np.array([ids[:-1]], dtype=np.int64)
    y_ids = np.array(ids[1:], dtype=np.int64)

    cfg = TransformerConfig(vocab_size=len(tokenizer.id_to_token), d_model=64, n_heads=4, n_layers=2, d_ff=128)
    model = NumpyTransformerLM(cfg, seed=seed)

    for epoch in range(1, epochs + 1):
        logits, _ = model.forward(x_ids, return_trace=False)
        probs = softmax(logits[0], axis=-1)

        loss = -np.log(probs[np.arange(len(y_ids)), y_ids] + 1e-12).mean()

        grad_logits = probs.copy()
        grad_logits[np.arange(len(y_ids)), y_ids] -= 1.0
        grad_logits /= len(y_ids)

        # For educational clarity we don't backprop to hidden states here.
        # We still demonstrate a train step by nudging LM bias using average gradient.
        grad_b = grad_logits.sum(axis=0)

        model.b_vocab -= lr * grad_b

        if epoch % 5 == 0 or epoch == 1:
            print(f"epoch={epoch:02d} loss={loss:.4f}")


if __name__ == "__main__":
    run_demo_train()
