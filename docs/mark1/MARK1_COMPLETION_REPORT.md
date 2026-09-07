# Mark1 完了レポート

## 概要

Mark1は「Transformerの内部構造をブラックボックスにせず、Tokenizer / Embedding / Self-Attention / Multi-Head Attention / FFN / LayerNorm / デコード処理を自分で追える」ことを目的とした最小実装である（`docs/mark1/README.md`参照）。

`MARK1_TRANSFORMER_PLAN.md`の7日プランに対し、Day1〜5相当（環境準備〜最小学習ループ）を完了し、Day6（定量評価）は暫定的にスコープから外してMark1を完了とする。恒久的な放棄ではなく、必要になれば再開可能な判断である。

## 実施した内容

| 対象 | ファイル | 内容 |
|---|---|---|
| 環境・I/O設計 | `mark1/main.py`, `mark1/tokenizer.py` | CLI入口、文字単位tokenizer（encode/decode、特殊トークン） |
| Attention / Transformer本体 | `mark1/model.py` | Embedding + causal self-attention + multi-head + FFN + LayerNorm + LM Head、shape trace付き |
| デコード | `mark1/decode.py` | greedy / temperature sampling |
| 最小学習ループ | `mark1/train_min.py` | LM head biasのみを更新するSGDデモ |
| データフロー解説 | `MARK1_DATAFLOW_EXPLANATION.md` | 実行結果に基づくshape遷移の通し解説 |

達成状況（`MARK1_TRANSFORMER_PLAN.md` 1節の完了条件との対比）:

1. 最小Transformerの前向き計算を自作コードで追える → 達成（`mark1/model.py`のtrace出力）
2. 最低1つのユースケースに回答できる → 未達成（重みが学習されていないため実用的な応答はできない）
3. モデルの仕組みを説明できる → 達成（`MARK1_DATAFLOW_EXPLANATION.md`）
4. 改善ポイントを次ステップに言語化できる → 達成（本レポート + `docs/memo/backlog.md`）

## 実施しなかったこと（暫定スコープカット）

- Day6: 1ユースケースに対する20〜50問の定量評価、評価シート作成

理由: Mark1の主目的（Transformer内部構造の理解）は実装とデータフロー解説の時点で既に達成できており、乱数初期化のまま定量評価を行っても得られる知見が限定的なため、評価工数より次段階（Mark2）の判断を優先した。

## 分かっている制約・弱点

- `mark1/train_min.py`はAttention/FFNの重みを更新しない（LM head biasのみ）。実質的な学習とは言えない。
- 語彙(vocab)が実行のたびにプロンプト＋固定コーパスから再構築されるため、モデル重みを保存・再利用する仕組みがない。
- 文字単位tokenizerのため、実用的な言語理解には遠い。
- 上記の通り評価が未実施のため、生成品質について定量的な裏付けがない。

## 次アクション

具体的な改善項目（Mark2候補）は、フェーズに縛られない継続的なバックログとして `docs/memo/backlog.md` に記録した。着手が決まった項目は、その時点で該当するmark配下のドキュメントに反映する。

## Definition of Done（最終状態）

- [x] 一人でセットアップ〜推論まで再現できる
- [x] Attentionとshape変化をログで追跡できる
- [ ] 最小評価結果がある（20〜50問）— 暫定スコープカットにより未実施
- [x] 次の改善3項目が決まっている（`docs/memo/backlog.md`参照）
