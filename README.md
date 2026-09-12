# AI architecture research

このリポジトリは、公開AIモデルをベースラインとして理解し、脳科学・計算論的神経科学から得た計算原理を最小単位で検証する研究プロジェクトです。

## ディレクトリ構成

```text
ai_research/          # 現在の研究基盤（公開モデルの推論・記録コマンド）
configs/              # 実験設定ファイル
prototypes/           # 過去に作った独立した参照価値のあるプロトタイプ
tests/                # ユニットテスト
docs/research/        # 現在の研究計画・進行状況・実行手順
docs/experiments/     # 実験テンプレート・個別実験の計画と証跡
docs/decisions/       # baseline選定など、根拠付きの意思決定記録
docs/reference/       # 特定の研究フェーズに紐付かない技術解説
docs/memo/            # 未整理のアイデアとバックログ
logs/                 # 実行時に生成されるローカルログ（原則git管理外）
```

過去世代（`mark{n}`）をmainにディレクトリとして残さずtag/Releaseで管理する方針は[`docs/decisions/generation-snapshots.md`](./docs/decisions/generation-snapshots.md)を参照してください。

## 現在のフェーズ

- **Mark1（完了）**: NumPy製の最小Transformerで基本構造とデータフローを確認しました。当時の計画・進捗・完了レポートはgit tag `mark1` とそのGitHub Releaseを参照してください。今も参照価値のある実装は [`prototypes/numpy_transformer/`](./prototypes/numpy_transformer/)、Transformer解説は [`docs/reference/`](./docs/reference/) に残しています。
- **Mark2（研究基盤構築中）**: 現代の公開モデルを再現可能なbaselineとして選定し、脳の計算原理から導いた仮説を一つずつ比較実験します。目的、進め方、完了条件は [`docs/research/README.md`](./docs/research/README.md) を参照してください。

Mark2では「脳に近いこと」ではなく、**AIとして測定可能な改善があること**を成功条件にします。SNNそのものの構築や、脳全体の一括模倣は目的に含みません。

## NumPy Transformerプロトタイプを再実行する

Python 3.10以上とNumPyが必要です。

```bash
python -m prototypes.numpy_transformer --prompt "こんにちは、Mark1"
python -m prototypes.numpy_transformer.train_min
```

詳細は [`prototypes/numpy_transformer/README.md`](./prototypes/numpy_transformer/README.md) を参照してください。

## 現在の研究コードを実行する

設定確認は `python3 -m ai_research.run --check-config` で実行できます。GPU環境での導入・推論・記録の手順と検証状況は [`docs/research/RUNNING.md`](./docs/research/RUNNING.md) を参照してください。

```bash
python3 -m unittest discover -s tests -v
```
