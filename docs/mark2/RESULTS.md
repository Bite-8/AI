# Baseline results

## Provider-reported

Qwen3.5-9Bの公式model cardには複数benchmarkの公表値がある。ただし評価harness、prompt、sample、推論条件がこのrepositoryのpilot contractと同一とは確認していないため、ここでは数値を転記せず一次資料への参照に留める。

- [Pinned Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)

## Repository-measured

未実行。Qwen3.5-9Bのprimary採用確認と、その後のAWS On-Demand構成・時間・費用・停止条件のHuman実行承認を得てから、独立した2 runを行う。

## Mock-only

自動テストと`--backend mock`はaccuracy集計・失敗記録・出力分離・再現比較の検証用であり、Qwen3.5-9BまたはMMLUの測定結果ではない。mock manifestは`result_classification: mock-only`と記録する。

## Unverified

- 実機上で固定revisionが完全にloadできること
- AWS `g6.2xlarge`のL4 24 GB 1基でCPU/disk offloadなしに完走できること
- 100問の所要時間とpeak memory
- 独立2 runで予測が完全一致すること
