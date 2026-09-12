# backlog

特定の研究フェーズに縛られない、随時追記していく改善点・気づきのメモ。

`docs/README.md`の方針通り、ここは整理前の置き場であり、正式なGoal、仕様、進捗、優先順位を表さない。Humanが着手を承認した項目はGitHub IssueでScopeとAcceptance Criteriaを管理し、研究内容は対応する`docs/research/`、`docs/experiments/`、`docs/decisions/`へ反映する。

GitHub Issueは承認済み作業の実行管理にのみ使い、Goalや研究記録のSingle Source of Truthにはしない。ベンダーに依存させないGoal、実験条件・結果、判断はリポジトリ内に残す。

## Open

以下はMark1由来のNumPy Transformerプロトタイプに関するアイデアであり、Mark2のGoalや完了条件には含めない。

- [ ] 重みの永続化と再学習可能化: vocabを固定し、モデル重みをファイルに保存/読み込みできるようにする
- [ ] 全パラメータの学習（本物のbackprop）: `prototypes/numpy_transformer/train_min.py`をAttention/FFNまで含めた勾配計算に拡張し、実際に損失が下がることを確認する
- [ ] tokenizerの改善: 文字単位からBPE風のサブワード分割へ移行し、語彙効率と汎化を改善する

## Done
