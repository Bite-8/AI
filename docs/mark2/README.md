# Mark2 baseline decision and execution plan

この資料だけを確認すれば、採用したbaseline、選定理由、AWS東京リージョンでの費用、実行前の確認事項と実行方法が分かるように情報を集約している。細かな変更経緯はgitとPRの履歴を参照する。

## 採用したprimary baseline

個人研究のprimary baselineとして、`Qwen/Qwen3.5-9B`を採用する。モデル選定と有料実行方針は2026-09-15にPR #31でHuman承認された。モデルは**採用済み、実機評価は未実行**である。

採用理由は次のとおり。

- 公開重みかつApache-2.0で、内部componentを変更する実験ができる
- 公式公表値はMMLU-Pro 82.5、GPQA Diamond 81.7で、小型ながら比較対象として十分に強い候補である
- BF16 weightは約19.3 GBで、L4 24 GB 1基に収まる見込みがある
- AWS東京リージョンのOn-Demandを数時間だけ利用でき、個人でも失敗・修正・再実行を繰り返しやすい

9BでGoal達成を確定するわけではない。Qwen3.5-4Bは安価なコード疎通用、Qwen3.8-27Bは9Bで有望だった仮説のscale-up確認用とし、proxyの結果をprimaryの改善とは扱わない。

| 候補 | BF16 weight / 構造 | 位置づけ |
|---|---:|---|
| Qwen3.5-4B | 9.33 GB / dense 4.66B | 安価だがprimaryには能力余裕が小さい。疎通用proxy |
| **Qwen3.5-9B** | **19.32 GB / dense 9.65B** | **品質、費用、単一GPUでの変更容易性の均衡がよい。primary推奨** |
| Qwen3.5-35B-A3B | 71.93 GB / MoE 35.95B | 介入とweight配置が複雑で初期反復に不向き |
| Qwen3.8-27B | 55.62 GB / dense 27.78B | H100級が必要。少数の有望仮説のscale-up確認用 |
| DeepSeek-V3 / Kimi-K2 | 約689 GB / 約1.03 TB / 大規模MoE | 16 GPU級で個人研究の反復用primaryには不向き |

weight容量は2026-09-13にpinned Hugging Face repository metadataから確認したtensor storageで、KV cache、activation、CUDA context等は含まない。provider公表benchmarkは条件がこのrepositoryのpilotと異なるため、能力帯の確認にだけ使う。

## AWS東京リージョンでの費用案

モデル採用後の初回実機runには、東京リージョン（`ap-northeast-1`）のEC2 Linux On-Demand `g6.2xlarge`を提案する。

| 項目 | 提案 |
|---|---|
| GPU | NVIDIA L4 x1、24 GB、MIGなし |
| Host / local storage | 8 vCPU、32 GiB RAM、450 GB NVMe |
| Root volume | 暗号化gp3 100 GB、削除時にinstanceとともに削除 |
| 数値条件 | BF16、量子化なし、TF32なし、CPU/disk offloadなし |
| On-Demand参考単価 | **$1.4178/hour**（2026-09-14確認） |
| 作業上限 | **4時間** |
| Compute概算 | **$5.67**（$1.4178 x 4時間） |
| 承認依頼額 | **$10.00上限**（EBS、少量の転送、tax・為替手数料の余裕を含む） |

On-Demand単価は変わり得るため、起動直前にAWS accountで東京リージョンの実単価、利用可能AZ、G-family quotaを検索し、PRに提示する。見積もりが$10を超える場合は起動せず、再承認を求める。初回は中断による環境差を避けるためSpotを使わない。

承認は二段階に分ける。

1. `Qwen/Qwen3.5-9B`をprimary baselineとして採用する
2. 採用後、実単価・AZ・4時間/$10上限・停止条件・実行担当者を確認し、有料実行を明示承認する

## 固定する評価条件

機械可読なsource of truthは [`mark2/configs/qwen35_9b_mmlu.json`](../../mark2/configs/qwen35_9b_mmlu.json) である。

- Model: `Qwen/Qwen3.5-9B` revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`
- Dataset: `cais/mmlu` revision `c30699e8356da336a370243923dbaf21066bb9fe`、`all/test`
- Sample: question・choices・answerのhash順で固定した100問
- Prompt: zero-shot multiple choice、公式chat template、thinking無効
- Generation: BF16、無量子化、greedy、seed `20260913`、入力2,048 tokens以下、出力最大4 tokens
- Metric: 最初の独立したA〜Dを採用するexact-match accuracy。parse不能は不正解
- 再現条件: 独立2 runでcontract、question hashと予測列が同一、accuracy差0.0

各runはcommit、作業ツリー、環境、依存、GPU、source hash、時間、peak memory、予測、metric、成否をrun ID別artifactへ保存する。mock結果は`mock-only`、未実行の実機結果は`unverified`として区別する。

## 実行方法

無料の事前検査:

```bash
python3 -m mark2.run check-config
python3 -m unittest discover -s tests -v
python3 -m mark2.run run --backend mock --run-id mock-1
python3 -m mark2.run run --backend mock --run-id mock-2
python3 -m mark2.run compare artifacts/mark2/mock-1 artifacts/mark2/mock-2
```

Humanによる二段階の承認後、Python 3.10以上の隔離環境と `mark2/requirements.txt` の固定依存を使い、同じcommit・machineで実機runを2回行う。

```bash
python3 -m mark2.run run --backend transformers --run-id baseline-01
python3 -m mark2.run run --backend transformers --run-id baseline-02
python3 -m mark2.run compare \
  artifacts/mark2/baseline-01 \
  artifacts/mark2/baseline-02 \
  --output artifacts/mark2/reproducibility.json
```

次の場合は条件を変更せず停止し、logとartifactを退避してinstanceとEBSを削除する。

- 承認したregion/AZ、GPU、単価、構成と異なる
- revision、依存、実行commitが固定値と異なる
- CUDA/BF16が使えない、単一L4に収まらない、offloadまたはOOMが発生する
- local NVMe空きが開始時100 GB未満、download後50 GB未満
- unit test、mock比較、1回目runが失敗する
- 各準備phase 45分、各baseline run 45分、全工程4時間、または総額$10の超過が見込まれる

終了時はartifactを退避し、instance、EBS、snapshot、Elastic IP等の残存を確認して不要resourceを削除する。実時間、概算額、resource ID、削除時刻をPRへ記録する。

## 現在の結果

- 設定検査・mock実行・artifact分離・失敗記録・再現比較: 自動テスト済み
- Qwen3.5-9Bのprimary baseline採用: **Human承認済み**（PR #31）
- Qwen3.5-9B実機run: **未実行**
- L4 24 GBでのload、所要時間、peak memory、独立2 runの一致: **未検証**

## 一次情報

- [Pinned Qwen3.5-9B repository](https://huggingface.co/Qwen/Qwen3.5-9B/tree/c202236235762e1c871ad0ccb60c8ee5ba337b9a)
- [Pinned Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)
- [Pinned MMLU dataset](https://huggingface.co/datasets/cais/mmlu/tree/c30699e8356da336a370243923dbaf21066bb9fe)
- [Amazon EC2 G6 instances](https://aws.amazon.com/ec2/instance-types/g6/)
- [Amazon EC2 accelerated instance specifications](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html)
- [Amazon EC2 On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
- [AWS Pricing Calculator](https://calculator.aws/)
