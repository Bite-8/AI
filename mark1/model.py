from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np


@dataclass
class TransformerConfig:
    vocab_size: int
    d_model: int = 64
    n_heads: int = 4
    n_layers: int = 2
    d_ff: int = 128
    max_seq_len: int = 128
    eps: float = 1e-5

    def __post_init__(self) -> None:
        if self.d_model % self.n_heads != 0:
            raise ValueError("d_model must be divisible by n_heads")


class NumpyTransformerLM:
    """Minimal decoder-only Transformer LM implemented with NumPy."""

    def __init__(self, config: TransformerConfig, seed: int = 42) -> None:
        self.cfg = config
        self.rng = np.random.default_rng(seed)
        c = config

        scale = 1.0 / np.sqrt(c.d_model)
        self.token_embedding = self.rng.normal(0.0, scale, size=(c.vocab_size, c.d_model))
        self.pos_embedding = self._build_sinusoidal_positional_encoding(c.max_seq_len, c.d_model)

        self.layers: List[Dict[str, np.ndarray]] = []
        for _ in range(c.n_layers):
            layer = {
                "Wq": self.rng.normal(0.0, scale, size=(c.d_model, c.d_model)),
                "bq": np.zeros((c.d_model,)),
                "Wk": self.rng.normal(0.0, scale, size=(c.d_model, c.d_model)),
                "bk": np.zeros((c.d_model,)),
                "Wv": self.rng.normal(0.0, scale, size=(c.d_model, c.d_model)),
                "bv": np.zeros((c.d_model,)),
                "Wo": self.rng.normal(0.0, scale, size=(c.d_model, c.d_model)),
                "bo": np.zeros((c.d_model,)),
                "W1": self.rng.normal(0.0, scale, size=(c.d_model, c.d_ff)),
                "b1": np.zeros((c.d_ff,)),
                "W2": self.rng.normal(0.0, scale, size=(c.d_ff, c.d_model)),
                "b2": np.zeros((c.d_model,)),
            }
            self.layers.append(layer)

        self.W_vocab = self.rng.normal(0.0, scale, size=(c.d_model, c.vocab_size))
        self.b_vocab = np.zeros((c.vocab_size,))

    @staticmethod
    def _build_sinusoidal_positional_encoding(max_seq_len: int, d_model: int) -> np.ndarray:
        pe = np.zeros((max_seq_len, d_model), dtype=np.float64)
        positions = np.arange(max_seq_len)[:, None]
        div = np.exp(np.arange(0, d_model, 2) * -(np.log(10000.0) / d_model))
        pe[:, 0::2] = np.sin(positions * div)
        pe[:, 1::2] = np.cos(positions * div)
        return pe

    @staticmethod
    def _layer_norm(x: np.ndarray, eps: float) -> np.ndarray:
        mean = x.mean(axis=-1, keepdims=True)
        var = x.var(axis=-1, keepdims=True)
        return (x - mean) / np.sqrt(var + eps)

    @staticmethod
    def _softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
        x_shifted = x - np.max(x, axis=axis, keepdims=True)
        exp = np.exp(x_shifted)
        return exp / np.sum(exp, axis=axis, keepdims=True)

    @staticmethod
    def _gelu(x: np.ndarray) -> np.ndarray:
        return 0.5 * x * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x**3)))

    def _causal_mask(self, seq_len: int) -> np.ndarray:
        mask = np.triu(np.ones((seq_len, seq_len), dtype=np.float64), k=1)
        return np.where(mask == 1.0, -1e9, 0.0)

    def forward(self, input_ids: np.ndarray, return_trace: bool = True) -> Tuple[np.ndarray, List[Dict[str, object]]]:
        """
        input_ids shape: [batch, seq_len]
        returns logits shape: [batch, seq_len, vocab_size]
        """
        if input_ids.ndim != 2:
            raise ValueError("input_ids must have shape [batch, seq_len]")

        batch, seq_len = input_ids.shape
        if seq_len > self.cfg.max_seq_len:
            raise ValueError(f"seq_len ({seq_len}) exceeds max_seq_len ({self.cfg.max_seq_len})")

        trace: List[Dict[str, object]] = []

        tok = self.token_embedding[input_ids]  # [B, T, D]
        pos = self.pos_embedding[:seq_len][None, :, :]  # [1, T, D]
        x = tok + pos

        if return_trace:
            trace.append({"stage": "embedding", "shape": list(x.shape)})

        d_head = self.cfg.d_model // self.cfg.n_heads
        causal_mask = self._causal_mask(seq_len)[None, None, :, :]  # [1,1,T,T]

        for i, layer in enumerate(self.layers):
            x_ln = self._layer_norm(x, self.cfg.eps)

            q = x_ln @ layer["Wq"] + layer["bq"]
            k = x_ln @ layer["Wk"] + layer["bk"]
            v = x_ln @ layer["Wv"] + layer["bv"]

            q = q.reshape(batch, seq_len, self.cfg.n_heads, d_head).transpose(0, 2, 1, 3)
            k = k.reshape(batch, seq_len, self.cfg.n_heads, d_head).transpose(0, 2, 1, 3)
            v = v.reshape(batch, seq_len, self.cfg.n_heads, d_head).transpose(0, 2, 1, 3)

            scores = (q @ k.transpose(0, 1, 3, 2)) / np.sqrt(d_head)  # [B, H, T, T]
            scores = scores + causal_mask
            attn = self._softmax(scores, axis=-1)
            ctx = attn @ v  # [B, H, T, Dh]

            ctx = ctx.transpose(0, 2, 1, 3).reshape(batch, seq_len, self.cfg.d_model)
            attn_out = ctx @ layer["Wo"] + layer["bo"]
            x = x + attn_out

            y = self._layer_norm(x, self.cfg.eps)
            ffn = self._gelu(y @ layer["W1"] + layer["b1"])
            ffn_out = ffn @ layer["W2"] + layer["b2"]
            x = x + ffn_out

            if return_trace:
                trace.append(
                    {
                        "stage": f"layer_{i}",
                        "q_shape": list(q.shape),
                        "k_shape": list(k.shape),
                        "v_shape": list(v.shape),
                        "score_shape": list(scores.shape),
                        "attn_shape": list(attn.shape),
                        "ctx_shape": list(ctx.shape),
                        "output_shape": list(x.shape),
                    }
                )

        x = self._layer_norm(x, self.cfg.eps)
        logits = x @ self.W_vocab + self.b_vocab

        if return_trace:
            trace.append({"stage": "lm_head", "shape": list(logits.shape)})

        return logits, trace
