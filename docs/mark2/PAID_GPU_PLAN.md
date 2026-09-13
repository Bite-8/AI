# AWS paid GPU execution plan

- Status: **モデル選定・Human実行承認待ち（未予約・未実行）**
- Price checked: 2026-09-13
- Proposed workload: `Qwen/Qwen3.8-27B`、unquantized BF16、MMLU 100問、独立2 run
- Purchase option: Amazon EC2 Capacity Blocks for ML

## この計画の前提

[`BASELINE_DECISION.md`](BASELINE_DECISION.md)はQwen3.8-27Bを推奨候補としており、まだprimary baselineとして採用していない。まずモデル選定のHuman確認を得る。その後、この計画に対する別の明示承認を得るまでCapacity Blockを検索・購入しない。

Capacity Blockは通常の4時間従量課金として扱えない。AWS公式手順ではdurationは1日単位で、料金は購入時に前払いされ、予約後は変更・キャンセルできない。そのため、作業上限が4時間でも最低24時間分を予算化する。

## 提案構成

| 項目 | 固定する内容 |
|---|---|
| Provider | Amazon Web Services / Amazon EC2 Capacity Blocks for ML |
| Region | US East (N. Virginia)を第一候補。購入前に返されたAvailability Zoneとoffering IDを承認コメントへ記録する |
| Instance | `p5.4xlarge` x1 |
| GPU | NVIDIA H100 x1、80 GB HBM3、MIG不使用 |
| Host | 16 vCPU、256 GiB RAM |
| Local storage | 3.84 TB NVMe instance store。model cacheと一時artifactに使用し、終了時に消失する前提 |
| EBS | 暗号化gp3 root 100 GB、baseline 3,000 IOPS / 125 MiB/s。追加IOPS・throughputなし |
| OS | AWS提供Linux AMI。premium OSを使わない。AMI IDを実行記録へ残す |
| Numerical contract | BF16、量子化なし、TF32なし、CPU/disk offloadなし。OOM時も自動変更しない |
| Software | `mark2/requirements.txt`のexact pin、固定model/dataset revision、実行commitをmanifestへ記録する |

Qwen3.8-27BのBF16 weightsは約55.6 GBで、H100 80 GBに残る約24.4 GBをCUDA context、activation、KV cache、framework領域へ使える。ただしこれは容量計算であって実機保証ではない。preflightでCPU/disk offloadなしのloadとGPU配置を確認し、収まらなければ停止する。

AWS公式仕様では`p5.4xlarge`はH100 80 GB x1、256 GiB host memory、3.84 TB local NVMeを持つ。2026-09-13時点の[Capacity Blocks pricing](https://aws.amazon.com/ec2/capacityblocks/pricing/)はUS East (N. Virginia)の`p5.4xlarge`を**$5.191/instance-hour**と掲載している。ただし購入価格は需給と実offeringで決まるため、購入画面/APIの総前払額を最終見積もりとする。

## 時間・費用上限

### 作業時間

| Phase | 時間上限 | 完了条件 |
|---|---:|---|
| instance launch、driver/依存導入、無料検査 | 45分 | `check-config`、unit test、mock比較がすべて成功 |
| pinned artifact download、model load preflight | 45分 | revision一致、単一GPU BF16 load、offloadなし、十分な空きdiskを確認 |
| `baseline-01` | 60分 | completed manifest、100 predictions、metricを保存 |
| `baseline-02` | 60分 | 同一環境でcompleted manifest、100 predictions、metricを保存 |
| compare、artifact退避、instance/EBS削除 | 30分 | 比較結果を保存し、instance terminateとEBS削除を確認 |
| **作業上限** | **4時間** | 超過見込みなら処理を停止しresourceを削除 |

Capacity Block自体は24時間予約するが、余った時間を追加run、別model、別条件へ転用しない。instanceは作業終了後すぐterminateする。早期terminateしても前払いの予約料金は返金されない。

### 予算

| 項目 | 計算 | 見積額 |
|---|---:|---:|
| Capacity Block reservation | $5.191 x 24 hours x 1 instance | $124.58 |
| gp3 100 GBを24時間 | $0.08/GB-month x 100 / 30 | $0.27 |
| 予備枠 | offering差、少量の転送・artifact保管等 | $15.15 |
| **承認を求める絶対上限** |  | **$140.00** |

- Linux以外のOS料金、tax、為替手数料は上表に含めない。これらを含めてAWS購入確認画面の支払額が$140を超える場合は購入しない
- AWSのinbound転送や実料金を「無料」と仮定して予算を使い切らない。未見積もりの有料項目が表示された場合は開始せず再見積もりする
- gp3単価はUS East (N. Virginia)のAWS公式例に基づく。EBSは使用後に必ず削除する
- Capacity Blockの掲載単価は購入時まで保証されない。実offeringの前払額、開始・終了時刻、AZを提示して最終承認を得る

## 承認ゲート

次の順番を崩さない。

1. Reviewer/Humanが候補比較を確認し、Qwen3.8-27Bをprimary baselineとして採用する
2. AWS accountで`p5.4xlarge` x1・1日のofferingを**検索だけ**行い、offering ID、AZ、開始・終了時刻、前払額、失効条件を記録する
3. PR #31またはIssue #30へ、実offeringと本書の4時間作業上限・$140絶対上限・停止条件・実行担当者を提示する
4. 記名されたHumanが購入を明示承認する
5. 承認対象とofferingが完全一致する場合だけ購入する

offering検索は課金を発生させないが、購入操作は即時の前払いにつながりキャンセルできない。Codexが操作可能でも、明示承認前に購入APIを呼ばない。

## 実行前ゲート

購入後も次をすべて満たすまでbaseline推論を始めない。

1. 実行対象commitがreview済みで、作業ツリーがcleanである
2. Capacity Blockのregion、AZ、instance type、台数、時刻、料金が承認内容と一致する
3. 実行担当者がinstanceとEBSを削除でき、AWS Billing/Cost Managementを確認できる
4. artifact退避先と、secret/private host情報を含まないことの確認方法を決めている
5. account quota、Hugging Faceからのdownload、AMI、IAM、security groupが準備済みである

## 停止条件

以下のいずれかで新しいphaseへ進まず、可能なmanifest/logを退避してinstanceとEBSを削除する。

- instance type、GPU型・枚数・VRAM、MIG状態、region/AZが承認内容と一致しない
- modelまたはdataset revision、contract SHA、依存version、実行commitが固定値と一致しない
- CUDA GPUまたはBF16が利用できない
- modelがH100だけに配置されず、CPU/disk offloadが発生する、またはmodel loadがOOMになる
- local NVMeの空きが開始時200 GB未満、またはdownload後100 GB未満になる
- unit test、mock比較、1回目のbaseline runのいずれかが失敗する
- instance launchから4時間、各phaseの時間上限、または総額$140のいずれかへ到達する見込みになる
- AWS画面に未見積もりの有料resourceまたは追加料金が現れる
- 2 run間でGPU、driver、CUDA、依存、commit、contractが変化する

OOM時に複数GPU、CPU offload、FP16、FP8、量子化へ切り替えない。それらはbaseline条件を変えるため、失敗manifestと実測peak情報を提示してmodel選定または構成判断へ戻る。2 runの予測不一致は再現性結果として保存し、結果を合わせるための恣意的な再試行は行わない。

## 終了・削除責任

Capacity Blockを購入する**記名済みHuman実行担当者**を、instance、EBS、snapshot、Elastic IP等の付随resource削除と課金確認の最終責任者とする。Capacity Block予約自体は早期キャンセルできず、期限まで残る。

終了・失敗・中断のいずれでも、次の順で処理しIssue #30へ記録する。

1. manifest、predictions、比較結果、必要な失敗logを永続先へ退避する
2. artifactにtoken、credential、account ID、private host情報がないことを確認する
3. EC2 instanceをterminateする
4. rootを含むEBS volume、snapshot、Elastic IP、不要なsecurity group等を削除または解放する
5. EC2 consoleとBilling/Cost Managementで、Capacity Block以外の継続課金resourceが0件であることを確認する
6. 実時間、予約前払額、付随費用、削除確認、artifact pathをIssueコメントへ記録する

local NVMeのartifactはinstance terminateで失われるため、退避確認を先に行う。instanceのstopだけではEBSやElastic IPの課金が残り得るため、停止ではなくterminateと付随resourceの削除を確認する。

## AWS一次情報

- [EC2 P5 instance details](https://aws.amazon.com/ec2/instance-types/p5/): `p5.4xlarge`のH100、host memory、local NVMe
- [Accelerated instance specifications](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html): GPU数とGPU memory
- [Capacity Blocks pricing](https://aws.amazon.com/ec2/capacityblocks/pricing/): 掲載単価、前払い料金の説明
- [How Capacity Blocks work](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-how.html): durationと終了前の自動terminate
- [Find and purchase Capacity Blocks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-purchase.html): offering検索、1日単位、購入後キャンセル不可
- [Capacity Blocks pricing and billing](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-pricing-billing.html): 需給連動、購入時前払い
- [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/): gp3の課金方法とUS Eastの例
