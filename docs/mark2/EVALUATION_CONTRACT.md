# Evaluation contract

Qwen3.5-9B候補について、機械可読なsource of truthは [`mark2/configs/qwen35_9b_mmlu.json`](../../mark2/configs/qwen35_9b_mmlu.json) である。この文書はその意図を説明する。モデルのprimary採用状況は[`BASELINE_DECISION.md`](BASELINE_DECISION.md)をsource of truthとし、Humanが選定を承認するまではこのconfigの存在を採用決定とは扱わない。

## Quality evaluation

- Dataset: `cais/mmlu` revision `c30699e8356da336a370243923dbaf21066bb9fe`, config `all`, split `test`
- Selection: 各question・choices・answerのcanonical JSONをSHA-256化し、昇順の先頭100問。実行時に全question hashと選択集合hashをmanifestへ保存する
- Prompt: zero-shot multiple choice。回答は`A`〜`D`の1文字だけを要求する
- Model formatting: 固定revisionのchat template、`enable_thinking=false`
- Generation: 入力上限2,048 tokens（truncation禁止）、greedy (`do_sample=false`, `num_beams=1`), seed `20260913`, 最大4 output tokens
- Metric: 出力中の最初の独立した`A`〜`D`を回答としexact-match accuracyを集計。parse不能は不正解

100問は基盤の再現性を安価に確認するpilot contractであり、Qwen公式benchmark値との直接比較には使わない。Goal達成を主張する前に、後続Issueで統計的検出力と複数benchmarkを事前登録する。

## Reproducibility

独立run間で次をすべて満たした場合のみ再現と判定する。

- contract SHA-256が同一
- question hashと予測の列が完全一致
- accuracy差が0.0

runnerはTF32を無効化しgreedy decodingを用いる。ただしGPU・driver・kernel差で非決定性が残る可能性があるため、同一GPU型、driver、CUDA、依存versionをmanifestで比較する。

## Resource metrics and records

各runは所要時間、PyTorch peak allocated/reserved bytes、GPU名・数、driver、CUDA、Python、主要package version、git commit/status、source hash、成否を`manifest.json`へ保存する。実機runでは解決済みmodel configとchat templateも保存する。PyTorchのpeak値はGPU全体の使用量ではないため、他processを含むresource accountingとは区別する。
