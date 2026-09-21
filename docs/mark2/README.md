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

## AWS東京リージョンでの実行計画と費用

初回実機runは、東京リージョン（`ap-northeast-1`）のEC2 Linux On-Demand `g6.2xlarge`で行う。東京リージョンの使用は2026-09-15にPR #31でHuman承認済みであり、料金調査だけでは確定できない事項ではない。Availability Zoneは起動直前にaccount上の提供状況を確認して決める。東京で条件を満たせない場合も別regionへ自動変更せず、停止して再承認を求める。

| 項目 | 提案 |
|---|---|
| GPU | NVIDIA L4 x1、24 GB、MIGなし |
| Host / local storage | 8 vCPU、32 GiB RAM、450 GB NVMe |
| Root volume | 暗号化gp3 100 GB、削除時にinstanceとともに削除 |
| 数値条件 | BF16、量子化なし、TF32なし、CPU/disk offloadなし |
| On-Demand単価 | **$1.41781/hour**（2026-09-21 AWS Price List確認） |
| 作業上限 | **4時間** |
| AWS利用料概算 | **$5.74**（EC2、gp3、Public IPv4。税別） |
| 承認済み上限 | **$10.00**（tax・為替手数料と端数の余裕を含む） |

使う課金resourceと内訳は次のとおり。月額は比較しやすいよう730時間連続利用で換算した値であり、実際に1か月動かす計画ではない。gp3の4時間額は730時間月として按分している。

| 課金resource | 数量・単価 | 4時間上限の概算 | 730時間の月額換算 |
|---|---:|---:|---:|
| EC2 `g6.2xlarge` Linux On-Demand | 1台、$1.41781/hour | $5.67 | $1,035.00 |
| EBS gp3 root volume | 100 GB、$0.096/GB-month、baseline 3,000 IOPS / 125 MB/s | $0.05 | $9.60 |
| Public IPv4 | 1 address、$0.005/hour | $0.02 | $3.65 |
| Instance store NVMe | 450 GB、instance料金に含む | $0.00 | $0.00 |
| Internet data transfer | model downloadは受信のため$0。artifact送信はaccount全体の月間100 GB無料枠内を想定 | $0.00見込み | 利用量とaccount全体の使用状況による |
| **合計** |  | **$5.74** | **$1,048.25 + 無料枠超過分** |

日本の消費税10%が全額にかかる単純な保守計算でも4時間は約$6.32で、承認済み$10上限内である。実際の請求はbilling address、為替、account全体の無料枠使用状況に依存する。NAT Gateway、Load Balancer、EBS snapshot、Elastic IP、追加EBS、長期保存用S3は使用しない。VPC、Security Group、Internet Gateway、IAMにはこの最小構成で追加時間料金を見込まない。

単価は変わり得るため、起動直前にAWS accountで東京リージョンの実単価、利用可能AZ、G-family quotaを検索し、PRに提示する。現在の実行roleではAZとquotaを参照する権限がないため、この2点は未確認である。見積もりが$10を超える場合は起動せず、再承認を求める。初回は中断による環境差を避けるためSpotを使わない。

PR #31では次の二段階が承認済みである。

1. `Qwen/Qwen3.5-9B`をprimary baselineとして採用する
2. 東京リージョン、4時間/$10上限、停止条件に従って有料実行する

有料resourceはまだ作成していない。起動前に、未確認の実単価・AZ・quotaと実行担当者をPRへ記録し、承認済み条件をすべて満たすことを確認する。

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
- [AWS Price List Bulk API: EC2 Tokyo](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/ap-northeast-1/index.csv)
- [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/)
- [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)
