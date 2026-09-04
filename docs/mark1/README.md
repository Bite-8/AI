# Mark1 (NumPy Transformer)

Mark1 は、NumPy で実装した最小構成の Decoder-only Transformer 言語モデルです。

> **ステータス**: Day1〜5相当 + 完了レポート作成まで完了。Day6の定量評価は暫定的にスコープ外とした。詳細は [`MARK1_COMPLETION_REPORT.md`](./MARK1_COMPLETION_REPORT.md) を参照。恒久的な放棄ではなく、必要になれば再開可能。改善点は [`docs/memo/backlog.md`](../memo/backlog.md) で継続管理する。

## プロジェクトの位置づけ

このリポジトリは、公開AIモデルをベースラインとして理解し、脳科学・計算論的神経科学から得た計算原理を最小単位で検証する研究プロジェクトです。現在の目的と成功条件は [`docs/mark2/README.md`](../mark2/README.md) を参照してください。

## Mark1の位置づけ

Mark1はその出発点として、Transformerの内部構造をブラックボックスにせず、Tokenizer、Embedding、Self-Attention、Multi-Head Attention、FFN、LayerNorm、デコード処理を自分で追えるようにすることを目的とした最初の実験機です。NumPy中心の小さな実装から始め、AIの仕組みを理解した上で、Mark2の比較研究へつなげます。

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

リポジトリルートで `mark1` パッケージを実行すると、プロンプトを入力にしてモデルの forward と簡易生成を行います。

### 最小実行例

```bash
python -m mark1 --prompt "こんにちは、Mark1"
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
python -m mark1 \
  --prompt "transformerの挙動を確認したい" \
  --max-new-tokens 16 \
  --temperature 0.7 \
  --seed 123
```

## 学習デモの実行方法

最小の学習デモ（LM headバイアス更新のみ）は次で実行できます。

```bash
python -m mark1.train_min
```

## ドキュメント一覧

- `MARK1_TRANSFORMER_PLAN.md` : Mark1全体計画（7日版/14日版）
- `MARK1_DAY1_DETAILED_PLAN.md` : Day1（環境準備 + I/O設計）の詳細実行プラン
- `MARK1_IMPLEMENTATION.md` : NumPy Transformer実装メモ（shape遷移/第一次情報リンク）
- `MARK1_DATAFLOW_EXPLANATION.md` : Mark1の実行結果をもとにしたデータフロー解説
- `MARK1_COMPLETION_REPORT.md` : Mark1完了レポート（実施内容・制約・次アクション）
