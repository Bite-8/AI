# backlog

フェーズ（mark{number}）に縛られない、随時追記していく改善点・気づきのメモ。

`docs/README.md`の方針通り、ここは整理前の置き場。着手することが確定した項目は、該当する`mark{number}/`配下のドキュメントへ反映する。

GitHubのIssueは使わない（ベンダーロックイン回避のため）。完了した項目はチェックを付けるか削除し、git履歴で経緯を追える状態にする。

## Open

- [ ] 重みの永続化と再学習可能化: vocabを固定し、モデル重みをファイルに保存/読み込みできるようにする
- [ ] 全パラメータの学習（本物のbackprop）: `prototypes/numpy_transformer/train_min.py`をAttention/FFNまで含めた勾配計算に拡張し、実際に損失が下がることを確認する
- [ ] tokenizerの改善: 文字単位からBPE風のサブワード分割へ移行し、語彙効率と汎化を改善する

## Done
