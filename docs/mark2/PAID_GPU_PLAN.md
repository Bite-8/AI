# AWS paid GPU execution plan

- Status: **モデル選定・Human実行承認待ち（未作成・未実行）**
- Price checked: 2026-09-13
- Proposed workload: `Qwen/Qwen3.5-9B`、unquantized BF16、MMLU 100問、独立2 run
- Purchase option: Amazon EC2 Linux On-Demand

## 前提と選択理由

[`BASELINE_DECISION.md`](BASELINE_DECISION.md)は個人研究向けprimaryとしてQwen3.5-9Bを推奨しているが、まだ採用していない。モデル選定と、この有料実行のHuman承認を順に得るまでinstanceを起動しない。

短期・不定期で中断させたくない初回baselineなので、秒課金（60秒最低）・前払いなしのOn-Demandを使う。Spotは安い可能性があるが中断が再現性検証を汚すため初回には使わない。Capacity Blockは24時間前払いが個人研究の反復性を損なうため使わない。

## 提案構成

| 項目 | 固定する内容 |
|---|---|
| Provider | Amazon Web Services / Amazon EC2 On-Demand |
| Region | US East (N. Virginia)。起動前に利用可能AZと単価を承認コメントへ記録 |
| Instance | `g6.2xlarge` x1 |
| GPU | NVIDIA L4 x1、24 GB、MIG不使用 |
| Host | 8 vCPU、32 GiB RAM |
| Local storage | 450 GB NVMe。model cacheと一時artifactに使用し終了時消失 |
| EBS | 暗号化gp3 root 100 GB、3,000 IOPS / 125 MiB/s。追加性能なし |
| Numerical contract | BF16、量子化なし、TF32なし、CPU/disk offloadなし |
| Software | exact pin、固定model/dataset revision、実行commitをmanifestへ記録 |

BF16 weightは約19.3 GBで、24 GB GPUに約4.7 GB残る計算だが実機保証ではない。短いprompt・batch size 1でpreflightし、offloadまたはOOMなら条件を変えず停止する。

## 時間・費用上限

| Phase | 上限 | 完了条件 |
|---|---:|---|
| launch、driver/依存、無料検査 | 45分 | check-config、unit test、mock比較成功 |
| download、revision検査、load preflight | 45分 | 単一GPU BF16、offloadなし、disk余裕確認 |
| `baseline-01` | 45分 | completed manifest、100 predictions |
| `baseline-02` | 45分 | 同一環境のcompleted manifest、100 predictions |
| compare、退避、terminate・削除 | 30分 | 比較保存、instance/EBS削除確認 |
| **作業上限** | **4時間** | 超過見込みなら停止してresource削除 |

参考単価$0.9776/hourなら4時間のcomputeは$3.91。gp3 100 GBを4時間保持する概算は約$0.04である。単価差、少量の転送・artifact保管、終了処理の余裕を含め、**tax・為替手数料込み絶対上限を$8.00**とする。実行直前の見積もりが上限を超える場合は起動しない。

## 承認ゲート

1. HumanがQwen3.5-9Bをprimaryとして採用する
2. AWS accountでG-family On-Demand quota、`g6.2xlarge` availability、Linux単価を検索だけ行う
3. PR #31またはIssue #30へAZ、単価、4時間/$8上限、停止条件、実行担当者を提示する
4. 記名Humanが明示承認する
5. 承認内容と一致する場合だけinstanceを起動する

## 実行前ゲートと停止条件

実行commitがreview済みかつcleanで、削除担当者・artifact退避先・quota・AMI・IAM・security groupが準備済みであることを確認する。次のいずれかで新phaseへ進まず、manifest/logを退避してinstanceとEBSを削除する。

- instance、GPU、VRAM、region/AZ、単価が承認内容と異なる
- model/dataset revision、contract SHA、依存、commitが固定値と異なる
- CUDA/BF16が使えない、単一L4に配置されない、offloadまたはOOMが発生する
- local NVMe空きが開始時100 GB未満、download後50 GB未満
- unit test、mock比較、1回目runのいずれかが失敗する
- launchから4時間、phase上限、総額$8の到達が見込まれる
- 未見積もりの有料resource、または2 run間の環境変化がある

OOM時に複数GPU、CPU offload、FP16、FP8、量子化へ自動変更しない。条件変更は別decisionとして再レビューする。

## 削除・課金停止

起動を承認された記名Humanを、instance、EBS、snapshot、Elastic IP等の削除と課金確認の最終責任者とする。

1. artifactを退避しsecret/private host情報がないか確認
2. instanceをterminateし`terminated`を確認
3. rootを含むEBS、snapshot、Elastic IP、NAT Gateway等の残存を確認して不要分を削除
4. Billing/Cost Managementで継続課金resourceが0件であることを確認
5. 実時間、概算額、resource ID、削除時刻をPR/Issueへ記録

## 一次情報

- [EC2 G6 instances](https://aws.amazon.com/ec2/instance-types/g6/): L4 24 GB
- [EC2 accelerated instance specifications](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html): `g6.2xlarge`の8 vCPU、32 GiB、L4、NVMe
- [EC2 On-Demand](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-on-demand-instances.html): 秒課金、60秒最低、前払いなし
- [EC2 On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/): 起動直前に再確認する単価
- [EBS pricing](https://aws.amazon.com/ebs/pricing/): gp3の時間比例課金
- [EC2 Spot best practices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-best-practices.html): 初回でSpotを使わない根拠
