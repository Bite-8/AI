# Mark2 baseline decision and execution plan

この資料だけを確認すれば、採用したbaseline、選定理由、AWS東京リージョンでの費用、AMIとOSを含む実機構成、実行前の確認事項と実行方法が分かるように情報を集約している。細かな変更経緯はgitとPRの履歴を参照する。

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

実機runは、東京リージョン（`ap-northeast-1`）のEC2 Linux On-Demand `g6.2xlarge`で行う。このinstanceはHumanが1回だけ作成し、以後は使う時だけstartして終了後にstopする常設の実行環境とする（運用は「実行環境の分離と接続方法」を参照）。東京リージョンの使用は2026-09-15にPR #31でHuman承認済みであり、料金調査だけでは確定できない事項ではない。Availability Zoneは初回作成の直前にaccount上の提供状況を確認して決める。東京で条件を満たせない場合も別regionへ自動変更せず、停止して再承認を求める。

| 項目 | 提案 |
|---|---|
| GPU | NVIDIA L4 x1、24 GB、MIGなし |
| Host / local storage | 8 vCPU、32 GiB RAM、450 GB NVMe |
| Root volume | 暗号化gp3 100 GB。stop中も保持し、repository、virtual environment、model/dataset cacheを置く |
| 数値条件 | BF16、量子化なし、TF32なし、CPU/disk offloadなし |
| On-Demand単価 | **$1.41781/hour**（2026-09-21 AWS Price List確認） |
| 初回baseline sessionの作業上限 | **4時間** |
| 初回session AWS利用料概算 | **$5.74**（EC2、gp3、Public IPv4。税別） |
| 初回session承認済み上限 | **$10.00**（tax・為替手数料と端数の余裕を含む） |
| stop中の維持費 | **$9.60/月**（root EBS gp3 100 GBのみ。税別） |

使う課金resourceと内訳は次のとおり。月額は比較しやすいよう730時間連続利用で換算した値であり、実際に1か月動かす計画ではない。gp3の4時間額は730時間月として按分している。

| 課金resource | 数量・単価 | 4時間上限の概算 | 730時間の月額換算 |
|---|---:|---:|---:|
| EC2 `g6.2xlarge` Linux On-Demand | 1台、$1.41781/hour | $5.67 | $1,035.00 |
| EBS gp3 root volume | 100 GB、$0.096/GB-month、baseline 3,000 IOPS / 125 MB/s | $0.05 | $9.60 |
| Public IPv4 | 1 address、$0.005/hour | $0.02 | $3.65 |
| Instance store NVMe | 450 GB、instance料金に含む | $0.00 | $0.00 |
| Internet data transfer | model downloadは受信のため$0。artifact送信はaccount全体の月間100 GB無料枠内を想定 | $0.00見込み | 利用量とaccount全体の使用状況による |
| **合計** |  | **$5.74** | **$1,048.25 + 無料枠超過分** |

stop中はEC2料金とPublic IPv4料金はかからず、root EBSの$0.096/GB-monthだけが継続する。100 GBでは$9.60/月（1日あたり約$0.32）で、instanceを削除するまで発生する。この維持費は1 sessionの$10上限とは別枠であり、stop運用の採用にともなって新たに発生する。root volumeを100 GBより大きくする場合は維持費が比例して増えるため、実施前にHumanの承認を得る。

日本の消費税10%が全額にかかる単純な保守計算でも4時間は約$6.32で、承認済み$10上限内である。実際の請求はbilling address、為替、account全体の無料枠使用状況に依存する。NAT Gateway、Load Balancer、EBS snapshot、custom AMI、Elastic IP、追加EBS、長期保存用S3は使用しない。VPC、Security Group、Internet Gateway、IAM、SSM Session Manager（標準機能。VPC endpointを作らない構成）にはこの最小構成で追加時間料金を見込まない。

単価は変わり得るため、初回作成の直前にAWS accountで東京リージョンの実単価、利用可能AZ、G-family quotaを検索し、PRに提示する。以後のsessionでもstart前に実単価を確認する。現在の実行roleではAZとquotaを参照する権限がないため、この2点は未確認である。見積もりが$10を超える場合は起動せず、再承認を求める。初回は中断による環境差を避けるためSpotを使わない。

PR #31では次の二段階が承認済みである。

1. `Qwen/Qwen3.5-9B`をprimary baselineとして採用する
2. 東京リージョン、4時間/$10上限、停止条件に従って有料実行する

有料resourceはまだ作成していない。初回作成前に、未確認の実単価・AZ・quotaと実行担当者をPRへ記録し、承認済み条件をすべて満たすことを確認する。

## 固定する実機構成

### AMI、OS、driver

初回実機runでは、AWS公式の次のBase DLAMI releaseを使用する。

| 項目 | 固定値 |
|---|---|
| AMI release名 | `Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04) 20260915` |
| AMI提供者 | Amazon。起動前のimage照会でownerがAmazonであることを確認する |
| Architecture | `x86_64` |
| OS | Ubuntu 24.04.5 LTS |
| Kernel | `7.0.0-1012-aws` |
| System Python | `/usr/bin/python3.12` |
| NVIDIA driver | `595.91.07`（OSS driver） |
| Default CUDA | `13.2`（`/usr/local/cuda-13.2/`） |
| 同梱CUDA | 12.8、12.9、13.0、13.2 |
| SSM Agent | `3.3.4793.0` |
| DLAMI上のNVMe mount先 | `/opt/dlami/nvme` |

AWS公式release notesは、このreleaseがG6をsupportし、上記のOS・kernel・driver・CUDAを含むことを示している。通常のUbuntu AMIへdriverを後付けする案より、GPU driverとG6対応がAWSによって組み合わされたDLAMIを使う方が、4時間枠内のsetup失敗を減らせる。

PyTorch同梱DLAMIは使わない。このrepositoryは `mark2/requirements.txt` でPyTorchを含むPython依存を固定しているため、frameworkを含まないBase DLAMI上に専用virtual environmentを作り、固定versionだけをinstallする。AMIのglobal Python環境へinstallせず、OS packageの一括upgradeとNVIDIA driver/CUDAの更新もrun前には行わない。

AMI IDはregionごとに異なる。東京のIDを推測値で文書へ固定せず、起動直前に次の固定release名で照会し、実際に使用するIDと照会結果をPRへ記録する。`latest` parameterはreleaseが進むため起動指定には使わない。

```bash
aws ec2 describe-images \
  --region ap-northeast-1 \
  --owners amazon \
  --filters \
    'Name=name,Values=Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04) 20260915' \
    'Name=state,Values=available' \
    'Name=architecture,Values=x86_64'
```

照会結果が1件でない、Amazon所有と確認できない、G6非対応、または削除済みの場合は起動しない。勝手なrelease変更で解決せず、変更後のOS・kernel・driver・CUDAと理由をPRに提示してHumanの再確認を得る。2026-09-22現在、この実行roleには `ec2:DescribeImages` がないため、東京固有AMI IDは未確認である。

### 実行環境の分離と接続方法

実装・repository作業と、model実行は別のinstanceで行う。

| 役割 | instance | 稼働 | 用途 |
|---|---|---|---|
| 実装環境 | 既存の開発用EC2（GPUなし） | 常用 | repository編集、commit、PR、起動前確認、GPU instanceへのSSM接続元 |
| 実行環境 | `g6.2xlarge` 1台 | runの間だけrunning。それ以外はstopped | model runの実行のみ。Humanが1回作成し、以後はstart/stopで再利用する |

GPU instance上でrepositoryの実装作業は行わない。GPUはrunning中だけ課金されるため、編集やreviewのために起動したままにしない。

#### 作成・起動・停止の分担

GPU instanceは作成済みのものをstart/stopで使い回し、runのたびにterminateして作り直すことはしない。作成・起動・停止・削除はHumanが行い、エージェントにはEC2の作成・削除権限を付与しない。

| 操作 | 実施者 | 時期 |
|---|---|---|
| 初回作成（Security Group、instance profile、instance） | Human | 1回だけ |
| start | Human | runを行うsessionの開始時 |
| SSM接続、host検査、依存確認、run、artifact回収 | 実行担当者（Humanまたはエージェント） | session中 |
| stop | Human（明示的に実施） | session終了時。fallback timerは停止し忘れ対策 |
| terminateと再作成 | Human | 下記の再作成条件に当たった場合だけ |

stop運用を採る理由は次のとおり。

- instanceのIDとinstance profileが固定されるため、開発用EC2からの接続権限を1回設定すれば済む。作成のたびにIAM policyやSecurity Groupを更新する運用負荷と設定誤りを避けられる。
- エージェントにEC2作成・削除という広い権限を渡さずに済む。
- root EBSに依存とmodel cacheを残せるため、2回目以降のsessionでinstallとdownloadを省ける。

代わりに、stop中もroot EBSの維持費（100 GBで$9.60/月）が継続する。また環境を持ち越すため、再現性は次の方法で担保する。

- 初回作成時にunattended-upgradesを無効化し、OS package、kernel、NVIDIA driver、CUDAを自動更新させない。
- 各sessionのhost検査でOS、kernel、driver、CUDAが固定値と一致することを確認する。
- 各runでrepository commit、installed package version、model/dataset revisionをartifactへ記録する（既存のrun artifactの記録項目）。
- 手作業でglobal環境へpackageを追加しない。依存変更はrepositoryの `mark2/requirements.txt` の変更として行い、virtual environmentを作り直す。

次の場合だけ、Humanがinstanceをterminateして固定AMIから作り直す。

- host検査で固定値との不一致が見つかり、原因を戻せない
- `InsufficientInstanceCapacity` 等でstartできない状態が続く
- driver、CUDA、依存の組み合わせが合わずrunが成立しない
- AMI、instance type、volume構成の変更がHumanに承認された

作り直す場合も、この節と下表の構成に従い、新しいinstance IDとAMI IDをPRへ記録する。

接続は**SSM Session Manager**を第一手段とする。開発用EC2からAWS CLIでsessionを開始し、SSHのinbound portは開けない。

| 観点 | SSM Session Manager（採用） | SSH（採用しない） |
|---|---|---|
| inbound | 不要。Security Groupのingressを0件にできる | TCP/22のingressが必要 |
| 認証 | IAMのみ。instanceへ置く鍵がない | 鍵またはEC2 Instance Connectの鍵配布が必要 |
| 送信元IP | 開発用EC2のglobal IP変動に依存しない | `/32` 許可の更新が必要 |
| 監査 | CloudTrailにsession記録が残る | instance内のlogのみ |
| 追加費用 | なし | なし |
| 前提 | instance profileと開発用EC2 roleへのIAM権限、SSM endpointへのoutbound HTTPS | 鍵運用 |

選定したBase DLAMIにはSSM Agent `3.3.4793.0` が同梱されているため、追加installは不要である。GPU instanceはpublic subnetでpublic IPv4とInternet Gatewayを使ってoutboundを取り、SSM endpointへもそこから到達する。VPC endpointやNAT Gatewayは作らない。

artifactの回収は、SSMのport forwarding sessionをlocalの一時portからinstanceの22へ張り、そのtunnel越しに`scp`する。tunnelはSSM Agent内部で終端するため、Security Groupのingressは不要である。鍵はEC2 Instance Connectでsession直前に一時公開鍵を配布し、instanceへ永続鍵を置かない。

instanceが固定されるため、開発用EC2 roleのSSM・EC2 Instance Connect権限は、このinstanceのIDまたは `Project=AI-Mark2` tagに限定して1回だけ付与すればよい。作り直した場合も同じtagを付ければ権限を更新する必要はない。

SSMが利用できない場合は、勝手にSSHへ切り替えない。原因（instance profile未付与、権限不足、agent未起動、outbound不通）を記録して停止し、Humanの判断を待つ。

### EC2、storage、network

| 項目 | 構成 |
|---|---|
| Region | `ap-northeast-1`（東京） |
| Availability Zone | `g6.2xlarge` を提供するAZを初回作成の直前に1つ選び、PRへ記録。以後はstopしても同じAZに固定される |
| Purchase option | Linux On-Demand。Spot、Capacity Reservation、Savings Planは使わない |
| Instance | `g6.2xlarge`: 8 vCPU、32 GiB RAM、NVIDIA L4 24 GB x1 |
| Root EBS | gp3 100 GB、3,000 IOPS、125 MB/s、暗号化。repository、virtual environment、model/dataset cache、run artifactを置く永続領域。`DeleteOnTermination=true` とし、意図して作り直す時だけ一緒に削除する |
| Instance store | 450 GB NVMe。DLAMIの `/opt/dlami/nvme`。stopで消えるため一時作業領域だけに使い、残す必要のあるものを置かない |
| Public address | 自動割当Public IPv4 x1。stopで解放され、startごとに変わる。SSM接続はIPに依存しないためElastic IPは作らない |
| Security Group | このinstance専用。inbound ruleは0件。outboundはHTTPSのみ許可する |
| IAM instance profile | `AmazonSSMManagedInstanceCore` 相当の最小権限のみ。S3、EC2操作、その他のAWS API権限は付けない |
| 接続 | 開発用EC2からのSSM Session Manager。artifact回収はSSM port forwarding越しの `scp`。永続key pairやrepository tokenをinstanceへ保存しない |
| Outbound | model、dataset、Python package、repositoryの取得にHTTPSを使用。NAT Gateway、proxy、Load Balancerは作らない |
| Instance metadata | IMDSv2必須、hop limit 1 |
| 終了動作 | instance initiated shutdownを**stop**に設定。termination protectionを有効にする。停止し忘れ対策として、boot時に起動する235分後のshutdown timerを設定する（sessionを延長する場合は実行担当者が明示的に解除・再設定し、PRへ記録する） |
| 自動更新 | unattended-upgradesを無効化する |
| Tag | `Project=AI-Mark2`、`Purpose=baseline-validation`、`Issue=33`、`Lifecycle=persistent-stop` |

QwenとMMLUはpublicな固定revisionから取得するためHugging Face tokenは使わない。repositoryもpublic HTTPSでcloneする。instanceへAWS access key、GitHub token、その他のlong-lived secretを置かない。

root EBSの配置は次のとおりとする。

| path | 内容 |
|---|---|
| `/home/ubuntu/mark2/AI` | public repositoryのclone。sessionごとに固定commitをcheckoutする |
| `/home/ubuntu/mark2/venv` | `mark2/requirements.txt` の固定依存だけを入れたvirtual environment |
| `/home/ubuntu/mark2/hf-cache` | `HF_HOME`。固定revisionのmodel/datasetだけを保持する |
| `/home/ubuntu/mark2/AI/artifacts/mark2` | run artifact |

Qwen3.5-9B weight約19.3 GBとvirtual environmentを置くため、初回作成時のroot空きは50 GB以上を必要とする。不足する場合はvolumeを勝手に拡張せず、必要容量と維持費の増分をPRに提示してHumanの承認を待つ。

run artifactは実行担当者がSSM port forwarding越しの `scp` で開発用EC2へ回収してhashを照合する。stopしてもroot EBS上のartifactは残るが、PRへ記録する結果の正本は回収したものとする。4時間上限が優先され、時間切れが近い場合は取得済みの失敗manifestとlogだけを回収し、runを継続しない。S3、EBS snapshot、追加volumeは使わない。

### 初回作成とsessionの手順

#### A. 初回作成（Humanが1回だけ実施）

1. **作成前gate**
   - 上記release名から東京のAMI ID、owner、architecture、stateを確認する。
   - `g6.2xlarge` の提供AZ、On-Demand価格、G-family On-Demand vCPU quotaが条件を満たすことを確認する。
   - AMI ID、AZ、見積額（初回session上限とstop中の維持費）をPRへ記録する。
   - 構成や上限から外れる場合は作成せず、Humanの再確認を待つ。
2. **作成**
   - 専用Security Group（inbound 0件、outbound HTTPSのみ）、SSM用instance profile、EC2 1台を上表の構成で作成する。
   - 開発用EC2 roleへ、`Project=AI-Mark2` tagに限定した `ssm:StartSession`、`ssm:TerminateSession`、`ec2-instance-connect:SendSSHPublicKey` を付与する。
   - instance ID、volume ID、AMI ID、作成時刻をPRへ記録する。
3. **初回設定（作成直後のsession内で実施）**
   - SSM Session Managerで接続できることを確認する。接続できなければSSHへ切り替えず停止する。
   - unattended-upgradesを無効化し、boot時の235分shutdown timerを設定する。
   - root空きが50 GB以上あることを確認する。
   - root EBS上へpublic repositoryをcloneし、virtual environmentを作り、`mark2/requirements.txt` の固定依存をinstallする。

#### B. 各session（startからstopまで）

1. **start前確認（実行担当者）**
   - `origin/main` の実行commitを固定し、working treeがcleanであることを記録する。
   - On-Demand価格を確認し、そのsessionの時間上限と見積額をPRへ記録する。承認済み上限を超える見込みならstartしない。
2. **start（Human）**
   - HumanがinstanceをstartしてPRへ開始時刻を記録する。startできない場合は別AZや別typeへ変えず、Humanが再作成を判断する。
3. **host検査（startから15分以内）**
   - SSMで接続し、`cat /etc/os-release`、`uname -r`、`python3 --version`、`nvidia-smi`、`nvcc --version`、`lsblk`、`df -h` を保存する。
   - GPUがL4 24 GB x1でない、OS・kernel・driver・CUDAが固定値と異なる、root空きが30 GB未満なら停止する。
4. **依存と無料検査（startから45分以内）**
   - repositoryで固定commitをcheckoutする。`mark2/requirements.txt` が前回installから変わっていればvirtual environmentを作り直す。
   - installed package versionを保存し、`check-config`、unit test、mock 2 runと比較を実行する。1つでも失敗したら実機runへ進まない。
5. **baseline run**
   - `HF_HOME` をroot EBSのcacheに向け、固定revisionだけを使う。cacheがなければ取得し、あれば再利用する。
   - `baseline-01`、`baseline-02` を順に実行し、再現比較を行う。各run45分の上限を維持する。
   - OOMやoffload要求が出ても、instance変更、量子化、FP16、CPU/disk offloadへ変更しない。
6. **回収とstop**
   - manifest、predictions、比較結果、host検査logを開発用EC2へ回収してSHA-256を照合する。
   - HumanがinstanceをstopしてEC2 consoleまたはCLIで `stopped` を確認する。停止を確認するまでsessionを終了扱いにしない。
   - start・stop時刻、実時間、概算額、artifact hashをPRへ記録する。成功・失敗のどちらでも記録する。

この手順を自動化するInfrastructure as Codeや起動scriptの実装、実際のresource作成、実機runはIssue #33の文書化範囲には含めない。Humanがこの構成を確認した後、#30の残作業として実行する。

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

次の場合は条件を変更せず停止し、logとartifactを退避してinstanceをstopする。instanceの削除と再作成は「実行環境の分離と接続方法」の再作成条件に当たる場合だけHumanが判断する。

- 承認したregion/AZ、GPU、単価、構成と異なる
- revision、依存、実行commitが固定値と異なる
- CUDA/BF16が使えない、単一L4に収まらない、offloadまたはOOMが発生する
- root EBS空きが開始時30 GB未満、download後10 GB未満
- unit test、mock比較、1回目runが失敗する
- 各準備phase 45分、各baseline run 45分、1 session 4時間、または1 session $10の超過が見込まれる

終了時はartifactを退避してinstanceをstopし、`stopped` であること、snapshot、Elastic IP、追加volume等の想定外resourceがないことを確認する。実時間、概算額、instance ID、stop時刻をPRへ記録する。

## 現在の結果

- 設定検査・mock実行・artifact分離・失敗記録・再現比較: 自動テスト済み
- Qwen3.5-9Bのprimary baseline採用: **Human承認済み**（PR #31）
- 実機のAMI・OS・network・storage・実行手順: **Human確認待ち**（Issue #33）
- Qwen3.5-9B実機run: **未実行**
- L4 24 GBでのload、所要時間、peak memory、独立2 runの一致: **未検証**

## 一次情報

- [Pinned Qwen3.5-9B repository](https://huggingface.co/Qwen/Qwen3.5-9B/tree/c202236235762e1c871ad0ccb60c8ee5ba337b9a)
- [Pinned Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)
- [Pinned MMLU dataset](https://huggingface.co/datasets/cais/mmlu/tree/c30699e8356da336a370243923dbaf21066bb9fe)
- [Amazon EC2 G6 instances](https://aws.amazon.com/ec2/instance-types/g6/)
- [Amazon EC2 accelerated instance specifications](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html)
- [Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04) 20260915 release notes](https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-ami-gpubaseoss-ul2404-2026-09-16.html)
- [Deep Learning Base GPU AMI (Ubuntu 24.04) release index and lookup methods](https://docs.aws.amazon.com/dlami/latest/devguide/aws-deep-learning-x86-base-gpu-ami-ubuntu-24-04.html)
- [Amazon EC2 On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
- [AWS Price List Bulk API: EC2 Tokyo](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/ap-northeast-1/index.csv)
- [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/)
- [Amazon VPC pricing](https://aws.amazon.com/vpc/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)
