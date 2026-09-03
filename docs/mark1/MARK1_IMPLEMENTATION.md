# Mark1 実装メモ（Transformer最小版）

## 参照した第一次情報
1. Vaswani et al., **Attention Is All You Need** (NIPS 2017 / arXiv:1706.03762)
   - https://arxiv.org/abs/1706.03762
2. Ba et al., **Layer Normalization** (arXiv:1607.06450)
   - https://arxiv.org/abs/1607.06450

> Mark1は上記の式・構成（自己注意、位置情報、残差接続、LayerNorm）を、NumPyのみで追える形に単純化して実装した。

## 実装の要点
- `mark1/model.py`
  - デコーダ専用の最小Transformer (`NumpyTransformerLM`)
  - 構成: Token埋め込み + 位置埋め込み + (Self-Attention + FFN)×L + LM Head
  - 因果マスク付き自己注意（未来トークン参照禁止）
  - 各段階のshapeを `trace` として返す
- `mark1/decode.py`
  - greedy (`temperature=0`) と温度付きサンプリング (`temperature>0`)
- `mark1/main.py`
  - CLIで prompt を受け取り、前向き計算と生成を実行
  - shape trace を標準出力とJSONLへ保存

## データ変形（shape）
入力を `input_ids: [B, T]` としたとき:

1. 埋め込み
   - Token embedding: `[B, T, D]`
   - Positional embedding: `[1, T, D]`
   - 和: `x = [B, T, D]`

2. Self-Attention（各層）
   - `Q,K,V`: `[B, T, D]`
   - ヘッド分割後: `[B, H, T, Dh]` (`Dh=D/H`)
   - スコア: `[B, H, T, T]`
   - 因果マスク適用 + softmax: `[B, H, T, T]`
   - 文脈ベクトル: `[B, H, T, Dh]`
   - ヘッド結合: `[B, T, D]`

3. FFN（各層）
   - `Linear(D→Dff)` → GELU → `Linear(Dff→D)`
   - 出力: `[B, T, D]`

4. 出力層
   - LM Head: `[B, T, V]`

この形の遷移は `mark1/main.py` の実行時に `trace` として確認できる。

## 実行例
```bash
python -m mark1 --prompt "Mark1のtransformer確認" --max-new-tokens 8 --temperature 0
```

ログは `logs/run_YYYYMMDD.jsonl` に追記される。
