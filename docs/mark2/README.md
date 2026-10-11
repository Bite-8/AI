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

## 固定GPU instanceと運用境界

Mark2はHumanが用意した既存GPU EC2を再利用する。機械可読なsource of truthは [`mark2/configs/gpu_instance.json`](../../mark2/configs/gpu_instance.json) であり、regionは`ap-northeast-1`、instance IDは`i-0fb8c2572680019af`に固定する。CLI引数や環境変数で別targetへ切り替えられない。target変更はconfigとvalidatorを更新するreview可能なRepository変更として行う。

2026-10-10にinstanceを起動せずread-only APIだけで確認したinventoryは次のとおり。credential、account ID、private network情報、volume IDは記録しない。

| 項目 | 確認結果 |
|---|---|
| EC2 state | `stopped` |
| AMI ID | `ami-0018e78b14211afb1` |
| instance type / architecture | `g6.2xlarge` / `x86_64` |
| root device | `/dev/sda1`、EBS 1本、termination時削除=true |
| AMI name | `ec2:DescribeImages`権限不足のため未検証 |
| volume type / size / encryption | `ec2:DescribeVolumes`権限不足のため未検証 |
| SSM登録・ping状態 | `ssm:DescribeInstanceInformation`権限不足のため未検証 |
| guest OS / kernel / Python | stoppedのため未検証 |
| NVIDIA driver / CUDA / GPU型・VRAM | stoppedのため未検証 |
| SSM Agent version | stoppedかつSSM照会権限不足のため未検証 |

未検証項目を推測で固定しない。次にHumanが対象、利用目的、費用上限、終了時刻を明示して有料startを承認したsessionで、`run-command inventory`を実行する。その出力が[`qwen35_9b_l4_profile.json`](../../mark2/configs/qwen35_9b_l4_profile.json)と一致するか確認し、不一致ならmodel/datasetを取得せず停止する。AMI nameとvolume構成は必要なread-only権限が付与された後に再取得する。

Repository機能が許可する操作は固定targetの`status`、通常の`start`/`stop`、allowlist済みSSM Run Command、SSM Session Managerだけである。新規resource作成、terminate、reboot、強制stop、構成・権限変更、SSH fallbackは実装しない。各actionはEC2とSSMから返ったinstance IDを固定値と照合し、0件、複数件、ID不一致、terminated、不明・遷移中state、SSM未登録・offline、権限エラー、timeoutでfail closedする。別instance、別region、別接続方式へfallbackしない。

`start`は課金を開始する。Humanが利用目的と時間上限を明示した後に限り、固定instance IDをconfirmationとして指定する。作業者はsession終了時に`stop`を実行し、続けて`status`で`stopped`を確認する責任を持つ。自動化やAI workflowはHumanの明示承認なしにstartしない。単価や上限は変わり得るため、過去の見積りを承認として流用しない。

必要な実行権限は固定targetに対するEC2状態参照・start・通常stopと、SSM managed-instance参照・Run Command・Session Managerである。AWS CLIとSession Manager pluginが利用可能でなければ停止する。SSH用inbound ruleや永続keyは不要である。

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

## Controlled experiment contract

variantを実行する前に、baseline評価契約とは別のcontrolled experiment contractを作成する。形式例は [`mark2/configs/experiment_contract_example.json`](../../mark2/configs/experiment_contract_example.json) である。この例はvalidatorとartifact記録の確認専用であり、実際の脳科学的仮説、variant結果、仮説支持を表さない。

contractは次を結果取得前に固定する。

- `experiment_id`と`hypothesis_id`: 1〜80文字の安定した識別子
- `independent_variable`: 変更を許可する一つの識別子と説明
- `primary_metric`: `exact_match_accuracy`を増加させる方向
- `decision_rule`: 最小accuracy差、有意水準、one-sided exact paired testの識別子、variant 2 runの予測一致要件

未知・欠落key、不正な型やID、非有限数、範囲外の値は拒否される。特にbooleanを数値としては受理しない。まず作成したcontract単体を検査し、成功後に同じファイルをrunnerへ指定する。

```bash
python3 -m mark2.run check-experiment-contract \
  --experiment-contract mark2/configs/experiment_contract_example.json
python3 -m mark2.run run --backend mock --run-id experiment-bookkeeping \
  --experiment-contract mark2/configs/experiment_contract_example.json
```

指定時、runnerはbackend開始前に検証済み本体、canonical JSONのSHA-256、入力copyのファイル名を`manifest.json`へ保存し、run directoryへ`experiment_contract.json`をcopyする。保存copyを読み直して同じcanonical hashを計算すれば、本体・宣言hash・copyの対応を再検証できる。不正なcontractはrun directory作成前にnon-zeroで拒否される。`--experiment-contract`を指定しない既存baseline runのartifact形式は変わらない。

controlled experimentは「contract固定 → baseline 2 runとvariant 2 run → 4 artifactの適格性判定 → paired統計・三値判定」の順に進める。4 runすべてで同じ`--experiment-contract`を指定し、結果取得後に次を実行する。

```bash
python3 -m mark2.run qualify-experiment \
  artifacts/mark2/baseline-01 \
  artifacts/mark2/baseline-02 \
  artifacts/mark2/variant-01 \
  artifacts/mark2/variant-02 \
  --output artifacts/mark2/experiment-qualification.json
python3 -m mark2.run evaluate-experiment \
  artifacts/mark2/baseline-01 \
  artifacts/mark2/baseline-02 \
  artifacts/mark2/variant-01 \
  artifacts/mark2/variant-02 \
  --output artifacts/mark2/experiment-evaluation.json
```

位置引数はbaseline 2 run、variant 2 runの順である。`qualify-experiment`は各artifactに既存のrepository-measured検査を適用し、experiment contractの本体・canonical SHA-256・保存copy、全directory/run IDの一意性、各pair内のcommit/source/固定環境、variantの事前登録済み予測再現条件、pair間の評価contract・sample順・target・prompt/model/runtime条件を検査する。baselineとvariantのcommit/source差だけは許可し、`pair_sources`へ明示する。

qualification reportの`eligible`は統計処理へ渡せるartifact集合であることだけを表す。1 checkでも不合格ならexit code 1となり、統計へ進めない。

`evaluate-experiment`も保存済みqualification reportを信用せず、指定された元artifactへ同じ適格性検査を毎回再実行する。不適格なら`qualification`に全checkを保持し、`comparisons`や`classification`を生成せずexit code 1となる。

適格な場合はbaseline run 1対variant run 1、run 2対run 2を別々のpaired evidenceとして扱う。各比較にsample数、双方の正解数・accuracy・符号付き差、both correct、both incorrect、variant only correct、baseline only correct、discordant pair数と改善・悪化それぞれのone-sided exact binomial p-valueを記録する。2 runを独立sampleとしてpoolしない。discordant pairが0なら両p-valueは1である。

最終`classification.result`はcontractの最小accuracy差と有意水準を両比較へ同じように適用する。両方が改善条件を満たす場合だけ`supported`、両方が悪化条件を満たす場合だけ`regressed`、方向・有意性・最小効果条件が一致しない場合を含む残りは`inconclusive`となる。適格な実験を規則どおり判定できた場合、3分類のどれでもexit code 0であり、非支持という科学的結果を実行障害とは扱わない。reportにはexperiment/hypothesis ID、contract hash、run ID、pair source、適用threshold、各比較値、classificationと理由が残る。

実機hostの承認済み条件は [`mark2/configs/qwen35_9b_l4_profile.json`](../../mark2/configs/qwen35_9b_l4_profile.json) に固定する。Python 3.10以上、`mark2/requirements.txt`のexact pin、CUDA/BF16、NVIDIA L4 1基、22,500 MiB以上のVRAM、開始時100 GiB以上の空き容量を要求する。実行時には別途、承認対象となったrepository commitの完全なSHAを渡す。

## 実行方法

Repositoryと固定target configの無料の事前検査:

```bash
python3 -m mark2.run check-config
python3 -m mark2.run check-experiment-contract
python3 -m mark2.instance --help
python3 -m unittest discover -s tests -v
python3 -m mark2.run run --backend mock --run-id mock-1
python3 -m mark2.run run --backend mock --run-id mock-2
python3 -m mark2.run compare artifacts/mark2/mock-1 artifacts/mark2/mock-2
```

`status`はread-onlyだが、EC2とSSMの両方を検証できなければnon-zeroになる。

```bash
python3 -m mark2.instance status
```

Humanが対象、目的、時間・費用上限を明示してstartを承認した後だけ、次を実行する。confirmationは課金開始の誤操作を防ぐため固定instance IDと完全一致させる。`start`はEC2がrunningかつSSM Onlineになるまで最大10分だけ待つ。

```bash
python3 -m mark2.instance start \
  --confirm-start i-0fb8c2572680019af
python3 -m mark2.instance run-command inventory
python3 -m mark2.instance session
```

Run CommandはRepositoryに固定された`inventory`だけを受け付け、任意shell文字列をCLI引数から組み立てない。command ID、最終status、stdout、stderrを表示し、失敗または15分timeoutでnon-zeroになる。session開始失敗時もSSHへfallbackしない。

inventoryが承認済みprofileと一致した後、Python 3.10以上の隔離環境と `mark2/requirements.txt` の固定依存を使う。承認されたcommit SHAを記録し、modelまたはdatasetを取得する前にhost preflightを実行する。

```bash
EXPECTED_COMMIT=<承認された40文字のcommit SHA>
python3 -m mark2.run preflight \
  --expected-commit "$EXPECTED_COMMIT" \
  --run-id baseline-preflight
```

preflightは各条件の期待値、実測値、合否、理由を`artifacts/mark2/baseline-preflight/preflight.json`へ保存する。全条件合格時だけexit code 0となる。失敗時もartifactは残り、同じrun IDでは上書きしない。CPU-only hostで実行した場合はCUDA/GPU条件を理由としてdownload前にnon-zeroで停止する。

preflightのJSONが合格であることを確認してから、同じcommit・machineで実機runを2回行う。本実行もdownload前に同じgateを再評価するため、承認commitを各runへ渡す。

```bash
python3 -m mark2.run run --backend transformers \
  --expected-commit "$EXPECTED_COMMIT" --run-id baseline-01
python3 -m mark2.run run --backend transformers \
  --expected-commit "$EXPECTED_COMMIT" --run-id baseline-02
python3 -m mark2.run compare \
  artifacts/mark2/baseline-01 \
  artifacts/mark2/baseline-02 \
  --output artifacts/mark2/reproducibility.json
python3 -m mark2.run qualify \
  artifacts/mark2/baseline-01 \
  artifacts/mark2/baseline-02 \
  --output artifacts/mark2/baseline-qualification.json
```

`compare`はmockを含むoffline bookkeeping向けの再現性比較であり、実機baselineの採用判定ではない。実機2 run後は必ず`qualify`を実行する。`qualify`は各runの分類・preflight・contract・source・dataset selection・prediction・metric・model artifactの内部整合性と、2 run間のrun ID、commit、clean tree、固定依存・GPU条件、各hash、予測、accuracy差を検査する。全checkの名前、期待値、実測値、理由、合否と総合`eligible`判定をJSONへ保存し、1件でも不合格ならnon-zeroで終了する。mock-only、unverified、非transformers artifactはここで拒否される。

`baseline-qualification.json`の`eligible`がtrueであることを確認し、実機runのartifact path、commit、accuracy、同JSONをIssue #30へ記録する。falseの場合は不合格checkの`reason`を記録して停止し、artifactをbaselineとして採用しない。

次の場合は条件を変更せず実験を中止し、logとartifactを回収して通常stopする。

- 承認したregion/AZ、GPU、単価、構成と異なる
- revision、依存、実行commitが固定値と異なる
- CUDA/BF16が使えない、単一L4に収まらない、offloadまたはOOMが発生する
- disk空きが開始時100 GB未満、download後50 GB未満
- unit test、mock比較、1回目runが失敗する
- Humanが承認した時間または費用上限の超過が見込まれる

artifactはguest上の`artifacts/mark2/`でmanifestとhashを確認し、SSM session経由の承認済み転送方法で開発hostへ回収する。回収後に双方で`sha256sum`を計算し、一致を確認してからguest側copyの扱いを決める。command文字列へcredentialやsecretを含めず、stdout/stderrにも保存しない。

終了時は必ず次を実行する。`stop`は通常停止だけを要求して最大10分待つ。`status`で`stopped`を確認できなければ、別操作で回復を試みずHumanへtargetと失敗段階を報告する。

```bash
python3 -m mark2.instance stop
python3 -m mark2.instance status
```

実時間、概算額、run ID、artifact hash、停止確認時刻を対象Issue/PRへ記録する。instanceやEBSは削除せず、次の承認済みsessionまでstoppedで維持する。

## 現在の結果

- 設定検査・mock実行・artifact分離・失敗記録・再現比較: 自動テスト済み
- Qwen3.5-9Bのprimary baseline採用: **Human承認済み**（PR #31）
- 固定GPU EC2のread-only inventory: **一部確認済み**（権限不足項目とguest情報は未検証）
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
