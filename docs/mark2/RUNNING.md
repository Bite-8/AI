# Running the Mark2 baseline

## 1. 無料で行う事前検査

```bash
python3 -m mark2.run check-config
python3 -m unittest discover -s tests -v
python3 -m mark2.run run --backend mock --run-id mock-1
python3 -m mark2.run run --backend mock --run-id mock-2
python3 -m mark2.run compare artifacts/mark2/mock-1 artifacts/mark2/mock-2
```

`check-config` とmockはML package、GPU、networkを必要としない。mock結果は品質baselineではなく、artifact・metric・比較処理の疎通確認だけを表す。

## 2. 有料GPU前の必須承認

まず[`BASELINE_DECISION.md`](BASELINE_DECISION.md)の個人研究向け候補比較についてHuman確認を得て、primary baselineを採用する。採用後、具体的なAWS構成、費用計算、phase別上限、停止・削除手順を [`PAID_GPU_PLAN.md`](PAID_GPU_PLAN.md) に固定する。実行直前のOn-Demand単価と利用可能AZをIssue #30またはPR #31へ提示し、別のHuman明示承認を得るまでinstanceを起動しない。

- GPU型・枚数・VRAM・AWS region/AZ・On-Demand単価
- 作業上限時間、概算費用上限
- disk容量と保持費用
- 停止条件（OOM、model/dataset revision不一致、依存不一致、1 runの上限時間、費用上限）
- 終了後にinstanceとEBS等の付随resourceを誰がterminate・削除するか

runnerはcloud resourceの検索・購入・作成・停止・削除を行わない。

## 3. 実機環境

Python 3.10以上の隔離環境でexact pinを導入する。CUDAに応じたPyTorch wheel指定が必要なproviderでは、`torch==2.14.0`を保った対応indexを使用する。

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r mark2/requirements.txt
python3 -m mark2.run check-config
```

## 4. 独立した2 run

同じcommit・machine・空いているGPUで、run IDを変えて実行する。

```bash
python3 -m mark2.run run --backend transformers --run-id baseline-01
python3 -m mark2.run run --backend transformers --run-id baseline-02
python3 -m mark2.run compare \
  artifacts/mark2/baseline-01 \
  artifacts/mark2/baseline-02 \
  --output artifacts/mark2/reproducibility.json
```

既存run IDは上書きされない。失敗時も`manifest.json`を残す。artifactをrepositoryへ追加する際はpromptや環境情報を確認し、secretやprivate host情報を含めない。

## 5. 結果の反映

2 runのmanifest、predictions、比較結果をreviewし、[`RESULTS.md`](RESULTS.md) の「repository measured」へ値とartifact pathを追記する。mock値や提供者公表値を実測値へ転記しない。
