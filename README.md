# AI architecture research

このリポジトリは、脳科学・計算論的神経科学の計算原理をLLMへ導入し、固定した高性能baselineとのcontrolled experimentで改善を検証する研究プロジェクトです。正式な目的とGoalは [`GOAL.md`](GOAL.md) を参照してください。

## 現在の構成

- [`mark2/`](mark2/): 個人研究向けprimary baseline Qwen3.5-9Bを固定条件で検証する評価ハーネス
- [`docs/mark2/README.md`](docs/mark2/README.md): Mark2の選定記録、費用、評価条件、実行手順、結果
- [`prototypes/numpy_transformer/`](prototypes/numpy_transformer/): 完了済みMark1の教材用NumPy Transformer

## Mark2 baseline

設定だけの検査はモデルやdatasetをdownloadせずに実行できます。

```bash
python3 -m mark2.run check-config
python3 -m unittest discover -s tests -v
```

offlineのartifact生成と再現比較:

```bash
python3 -m mark2.run run --backend mock --run-id mock-1
python3 -m mark2.run run --backend mock --run-id mock-2
python3 -m mark2.run compare artifacts/mark2/mock-1 artifacts/mark2/mock-2
```

モデル選定は承認済みです。有料実行前の確認事項と実機baselineの手順は [`docs/mark2/README.md`](docs/mark2/README.md) に集約しています。

## Copyright

Copyright © 2026 Bite-8. All rights reserved.

No license is granted for this source code.
