# NumPy Transformer prototype (Mark1)

NumPy で実装した最小構成の Decoder-only Transformer 言語モデルです。「Mark1」として一人開発フェーズで完成させたプロトタイプで、現在はこの `prototypes/numpy_transformer/` に教材として保存しています。

> **ステータス**: Day1〜5相当 + 完了レポート作成まで完了。Day6の定量評価は暫定的にスコープ外とした。恒久的な放棄ではなく、必要になれば再開可能。完了時点の計画・進捗・完了レポートはgit tag `mark1` とそのGitHub Releaseで参照できる（本リポジトリのmainには保持しない）。


## Mark1の位置づけ

Mark1は最終形そのものではなく、そのための最初の実験機です。

まずはTransformerの内部構造をブラックボックスにせず、Tokenizer、Embedding、Self-Attention、Multi-Head Attention、FFN、LayerNorm、デコード処理を自分で追えるようにすることを目的とします。NumPy中心の小さな実装から始め、AIの仕組みを理解しながら、Mark2以降のより高度なAIへ発展させます。

## 前提環境

- Python 3.10+
- NumPy

インストール例:

```bash
python -m venv .venv
source .venv/bin/activate
pip install numpy
```

## model の実行方法

リポジトリルートで `prototypes.numpy_transformer` パッケージを実行すると、プロンプトを入力にしてモデルの forward と簡易生成を行います。

### 最小実行例

```bash
python -m prototypes.numpy_transformer --prompt "こんにちは、Mark1"
```

### 主なオプション

- `--max-new-tokens` : 生成する最大トークン数（デフォルト: `12`）
- `--temperature` : 生成温度（`0.0` で greedy、デフォルト: `0.0`）
- `--seed` : 乱数シード（デフォルト: `42`）
- `--d-model` : 埋め込み次元（デフォルト: `64`）
- `--n-heads` : ヘッド数（デフォルト: `4`）
- `--n-layers` : 層数（デフォルト: `2`）
- `--d-ff` : FFNの中間次元（デフォルト: `128`）
- `--max-seq-len` : 最大シーケンス長（デフォルト: `128`）
- `--log-dir` : 実行ログ(JSONL)の保存先（デフォルト: `logs`）
- `--run-id` : 任意の実行ID

例:

```bash
python -m prototypes.numpy_transformer \
  --prompt "transformerの挙動を確認したい" \
  --max-new-tokens 16 \
  --temperature 0.7 \
  --seed 123
```

## 学習デモの実行方法

最小の学習デモ（LM headバイアス更新のみ）は次で実行できます。

```bash
python -m prototypes.numpy_transformer.train_min
```

## 関連ドキュメント

- [`docs/reference/numpy-transformer-implementation.md`](../../docs/reference/numpy-transformer-implementation.md) : 実装メモ（shape遷移/第一次情報リンク）
- [`docs/reference/numpy-transformer-dataflow.md`](../../docs/reference/numpy-transformer-dataflow.md) : 実行結果をもとにしたデータフロー解説
- Mark1完了時点の全体計画・Day1詳細プラン・完了レポートはgit tag `mark1` / GitHub Releaseを参照
