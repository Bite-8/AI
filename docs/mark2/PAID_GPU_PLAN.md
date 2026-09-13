# Paid GPU execution plan

- Status: **Human approval待ち（未実行）**
- Price checked: 2026-09-13
- Workload: `Qwen/Qwen3.8-27B`、unquantized BF16、MMLU 100問、独立2 run

## 提案構成

| 項目 | 固定する内容 |
|---|---|
| Provider | Runpod Secure Cloud Pod |
| Region | 作成時にH200を提供できるregion。2 runは同一Pod上で行い、実際のregionをmanifestとIssueコメントに記録する |
| GPU | NVIDIA H200 x 1、141GB VRAM（MIG不使用） |
| Host | 24 vCPU、276GB RAM（2026-09-13時点の掲載構成） |
| Disk | container disk 200GB。開始前に少なくとも150GBが空いていることを確認する |
| Numerical contract | BF16、量子化なし、TF32なし。OOM時も自動変更しない |
| Software | `mark2/requirements.txt` のexact pin、固定model/dataset revision、実行commitをmanifestへ記録する |

Qwen3.8-27BのBF16 weight filesは約55.6GBで、model loadにはweight以外のCUDA・activation・KV cache・framework領域も必要になる。H200はNVIDIA公表で141GB memoryとBF16 Tensor Core対応であり、80GB GPUよりOOMリスクを下げつつ、単一GPUなのでmodel parallelismという追加変数を避けられる。この余裕を使って評価条件を増やすことはしない。

2026-09-13時点の[Runpod公式料金表](https://www.runpod.io/pricing)は、Secure Cloud H200 Podを **$4.59/GPU-hour**、同構成を141GB VRAM・276GB RAM・24 vCPUと掲載している。[NVIDIA H200仕様](https://www.nvidia.com/en-us/data-center/h200/)は141GB GPU memoryとBF16対応を示している。作成画面の構成または単価がこれと異なる場合は開始せず、再見積もりする。

## 時間・費用上限

| Phase | 時間上限 | 完了条件 |
|---|---:|---|
| provision、依存導入、無料検査 | 45分 | `check-config`、unit test、mock比較がすべて成功 |
| pinned artifact download、model load preflight | 45分 | revision一致、BF16の単一GPU load成功、十分な空きdiskを確認 |
| `baseline-01` | 60分 | completed manifest、100 predictions、metricを保存 |
| `baseline-02` | 60分 | 同一環境でcompleted manifest、100 predictions、metricを保存 |
| compare、artifact退避、削除 | 30分 | 比較結果を保存し、必要ファイル退避後にPodとdiskを削除 |
| **合計絶対上限** | **4時間** | 超過前に停止・削除 |

- GPU compute上限: `$4.59/hour x 4 hours = $18.36`（税・為替手数料を除く）
- Container disk掲載単価: `$0.10/GB/month`。200GBなら1か月保持時は`$20.00`。4時間で削除し時間按分される場合の参考値は約`$0.11`だが、課金単位は作成画面で確認する
- **承認を求める総額上限: $25.00（税・為替手数料を除く）**。作成画面でこの上限を保証できない場合は開始しない
- model downloadのegress等、公式料金表だけで確定できない追加料金が表示された場合は上限内でも開始せず、再承認を求める

時間は実測前の安全側の運用枠であり、所要時間の予測値ではない。各phaseが早く終了しても、余った時間を追加runや別条件へ転用しない。

## 実行前ゲート

次をすべて満たすまで有料Podを作成しない。

1. Issue #30またはPR #31で、HumanがGPU構成、4時間上限、$25上限、停止条件を明示承認している
2. 実行対象commitがreview済みで、作業ツリーがcleanである
3. Runpod作成画面でH200 x 1、141GB VRAM、MIGなし、単価`$4.59/hour`以下を確認できる
4. Podとdiskを削除できる権限を持つHumanを実行担当者・削除責任者としてIssueコメントに記名する
5. artifact退避先と、秘密情報を含まないことの確認方法を決めている

## 停止条件

以下のいずれかで新しいphaseへ進まず、可能なmanifest/logを退避してPodとdiskを削除する。

- GPU型・枚数・VRAM、MIG状態、region、単価が承認内容と一致しない
- modelまたはdataset revision、contract SHA、依存version、実行commitが固定値と一致しない
- CUDA GPUまたはBF16が利用できない、あるいはpreflightでmodel loadがOOMになる
- container diskの空きが開始時150GB未満、またはdownload後70GB未満になる
- unit test、mock比較、1回目のbaseline runのいずれかが失敗する
- provision開始から4時間、各phaseの時間上限、または総額$25のいずれかへ到達する見込みになる
- provider画面に未見積もりの有料resourceまたは追加料金が現れる
- 2 run間でGPU、driver、CUDA、依存、commit、contractが変化する

OOM時に複数GPU、CPU offload、FP16、量子化へ切り替えない。それらはbaseline条件を変えるため、失敗manifestと実測peak情報を提示して別途Human判断を求める。2 runの予測不一致は削除対象の失敗ではなく再現性結果として保存し、恣意的な再試行は行わない。

## 終了・削除責任

有料resourceをRunpod上で作成する**記名済みHuman実行担当者**を、Podと全diskの停止・削除に関する最終責任者とする。Codexが操作を代行できる場合も、実行担当者はprovider consoleで削除完了と課金対象resourceが0件であることを確認する。

実行担当者は終了・失敗・中断のいずれでも、次の順で処理し、Issue #30へ結果を記録する。

1. manifest、predictions、比較結果、必要な失敗logを退避する
2. artifactにtoken、credential、private host情報がないことを確認する
3. Podをterminateし、container/volume/network diskを削除する
4. provider consoleで課金対象resourceが0件であることを確認する
5. 実時間、概算請求額、削除確認、artifact pathをIssueコメントへ記録する

停止だけではdisk課金が残り得るため、確認対象はPodの停止ではなく**Podとdiskの削除**である。

## 代替候補（再承認が必要）

Runpod公式掲載値ではA100 80GBが`$1.59/hour`、H100 PCIe 80GBが`$2.89/hour`である。ただし55.6GBのweight以外に使えるVRAM余裕がH200より小さい。初回は実行可能性を優先してH200を提案し、H200が利用不能な場合も自動で代替候補を作成せず、GPU構成・費用上限を更新してHumanの再承認を得る。
