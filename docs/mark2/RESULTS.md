# Baseline results

## Provider-reported

Qwen3.8-27Bの公式model cardには複数benchmarkの公表値がある。ただし評価harness、prompt、sample、推論条件がこのrepositoryのpilot contractと同一とは確認していないため、ここでは数値を転記せず一次資料への参照に留める。

- [Pinned Qwen3.8-27B model card](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/README.md)

## Repository-measured

未実行。Issue #30でGPU構成・時間・費用・停止条件のHuman確認後、独立した2 runを行う。

## Mock-only

自動テストと`--backend mock`はaccuracy集計・失敗記録・出力分離・再現比較の検証用であり、Qwen3.8-27BまたはMMLUの測定結果ではない。mock manifestは`result_classification: mock-only`と記録する。

## Unverified

- 実機上で固定revisionが完全にloadできること
- 80GB級GPU 1基でOOMせず完走できること
- 100問の所要時間とpeak memory
- 独立2 runで予測が完全一致すること
