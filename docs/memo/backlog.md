# backlog

特定の研究フェーズに縛られない、随時追記していく改善点・気づきのメモ。

`docs/README.md`の方針通り、ここは整理前の置き場であり、正式なGoal、仕様、進捗、優先順位を表さない。着手時は [`GOAL.md`](../../GOAL.md) と現状の差分から作業範囲と検証条件を定め、変更をPRでレビューする。研究内容は対応する`docs/research/`、`docs/experiments/`、`docs/decisions/`へ反映する。

## Open

以下はMark1由来のNumPy Transformerプロトタイプに関するアイデアであり、Mark2のGoalや完了条件には含めない。

- [ ] 重みの永続化と再学習可能化: vocabを固定し、モデル重みをファイルに保存/読み込みできるようにする
- [ ] 全パラメータの学習（本物のbackprop）: `prototypes/numpy_transformer/train_min.py`をAttention/FFNまで含めた勾配計算に拡張し、実際に損失が下がることを確認する
- [ ] tokenizerの改善: 文字単位からBPE風のサブワード分割へ移行し、語彙効率と汎化を改善する

## Done
