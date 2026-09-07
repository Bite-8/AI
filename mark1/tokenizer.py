from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


SPECIAL_TOKENS = ["<PAD>", "<UNK>", "<BOS>", "<EOS>"]


@dataclass
class CharTokenizer:
    id_to_token: List[str]

    def __post_init__(self) -> None:
        self.token_to_id = {token: idx for idx, token in enumerate(self.id_to_token)}
        self.pad_id = self.token_to_id["<PAD>"]
        self.unk_id = self.token_to_id["<UNK>"]
        self.bos_id = self.token_to_id["<BOS>"]
        self.eos_id = self.token_to_id["<EOS>"]

    @classmethod
    def build_vocab(cls, texts: Iterable[str]) -> "CharTokenizer":
        vocab = sorted({ch for text in texts for ch in text})
        id_to_token = [*SPECIAL_TOKENS, *vocab]
        return cls(id_to_token=id_to_token)

    def encode(self, text: str, add_bos_eos: bool = True) -> List[int]:
        token_ids: List[int] = []
        if add_bos_eos:
            token_ids.append(self.bos_id)

        for ch in text:
            token_ids.append(self.token_to_id.get(ch, self.unk_id))

        if add_bos_eos:
            token_ids.append(self.eos_id)

        return token_ids

    def decode(self, token_ids: Iterable[int], skip_special_tokens: bool = True) -> str:
        chars: List[str] = []
        for token_id in token_ids:
            if token_id < 0 or token_id >= len(self.id_to_token):
                chars.append("?")
                continue

            token = self.id_to_token[token_id]
            if skip_special_tokens and token in SPECIAL_TOKENS:
                continue

            chars.append(token)

        return "".join(chars)
