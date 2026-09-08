# AI architecture research

このリポジトリは、公開AIモデルをベースラインとして理解し、脳科学・計算論的神経科学から得た計算原理を最小単位で検証する研究プロジェクトです。

## 現在のフェーズ

- **Mark1（完了）**: NumPy製の最小Transformerを使い、基本構造とデータフローを確認しました。実装は [`mark1/`](./mark1/)、記録は [`docs/mark1/`](./docs/mark1/) に保存しています。
- **Mark2（準備開始）**: 現代の公開モデルを再現可能なbaselineとして選定し、脳の計算原理から導いた仮説を一つずつ比較実験します。目的、進め方、完了条件は [`docs/mark2/README.md`](./docs/mark2/README.md) を参照してください。

Mark2では「脳に近いこと」ではなく、**AIとして測定可能な改善があること**を成功条件にします。SNNそのものの構築や、脳全体の一括模倣は目的に含みません。

## ディレクトリ

```text
mark1/              # 完了済みの教育用NumPy Transformer
mark2/              # 環境確認と固定版Qwen3.5の推論・記録コマンド
docs/mark1/         # Mark1の計画・実装記録・完了報告
docs/mark2/         # Mark2の研究計画・比較表・実験テンプレート
docs/memo/          # 未整理のアイデアとバックログ
logs/               # 実行時に生成されるローカルログ（原則git管理外）
```

## Mark1を再実行する

Python 3.10以上とNumPyが必要です。

```bash
python -m mark1 --prompt "こんにちは、Mark1"
python -m mark1.train_min
```

詳細は [`docs/mark1/README.md`](./docs/mark1/README.md) を参照してください。

## Mark2を開始する

設定確認は `python3 -m mark2.run --check-config` で実行できます。GPU環境での導入・推論・記録の手順と検証状況は [`docs/mark2/RUNNING.md`](./docs/mark2/RUNNING.md) を参照してください。
