# Mark2 primary baseline candidate decision

- Status: **選定案（Human decision待ち、未採用）**
- Comparison date: 2026-09-13
- Recommended candidate: `Qwen/Qwen3.8-27B`
- Candidate revision: `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`
- Proposed scope: text-only, post-trained model, non-thinking mode, unquantized BF16

## 結論

現時点ではprimary baselineを採用済みとはしない。候補比較とAWS費用調査に基づき、`Qwen/Qwen3.8-27B`を**Human確認にかける推奨候補**とする。固定評価configとrunnerは、この候補の実行可能性を検証するためのものとして扱う。

Qwen候補は27B dense、公開重み、Apache-2.0、公式Transformers対応で、BF16 weightは約55.6 GBである。AWSでは1基のH100 80 GBを持つ`p5.4xlarge`を候補にできる。一方、DeepSeek-V3とKimi-K2は総parameterを配置するため16 GPU級の公式例があり、AWS最小予約費の桁と分散実行の変数が増える。今回の100問pilotに対してはQwen候補が費用・実装・介入可能性のバランスに優れる。

ただし、次の2段階のHuman判断を分ける。

1. **モデル選定**: この比較を確認し、Qwen3.8-27Bをprimary baselineとして採用するか判断する
2. **有料実行**: 採用後、[`PAID_GPU_PLAN.md`](PAID_GPU_PLAN.md) の実際のCapacity Block offering、上限額、停止条件を別途承認する

モデル選定が承認されるまでは、本書のstatusを「採用」に変えず、有料resourceも予約しない。採用された場合は承認コメントへのlinkと日付を本書へ追記する。却下された場合は同じ評価軸で候補を再比較し、configを変更する。

## 比較方法

比較の対象はIssue #30が挙げた公開checkpointとし、次を確認した。

- 公開重み、ライセンス、固定revisionの有無
- dense/MoE、総parameter数、1 tokenあたりのactive parameter数
- 配布checkpointの数値形式とweight配置に必要な概算memory
- 公式または公式が示す実行方法、model codeを変更できるか
- 2026-09-13時点のAWS EC2 Capacity Blocksで必要となる構成と最低予約費

weight memoryはcheckpoint metadataのtensor数とdtypeから求めた概算であり、KV cache、activation、CUDA context、inference engineのworkspaceを含まない。MoEのactive parameter数は1 tokenの計算量には関係するが、全expertのweight配置量を減らさない。

## モデル・実行要件の比較

| 候補 | 公開構造・配布形式 | weight memoryの目安 | ライセンス・介入可能性 | AWS上の実行判断 |
|---|---|---:|---|---|
| Qwen3.8-27B | dense 27,781,427,952 parameters、BF16 | 55.6 GB（約51.7 GiB） | Apache-2.0。重み・設定公開、Transformers対応 | `p5.4xlarge`のH100 80 GB x1をpreflight候補にできる。単一GPUのため分散方式を追加しない |
| DeepSeek-V3 | MoE 671B main + 14B MTP、37B active、公式checkpointは主にFP8 | 公式checkpoint metadataから約688.6 GB。BF16 main weightsだけなら約1.34 TB | codeはMIT、weightsはDeepSeek Model License。重み・推論code公開 | H100 80 GB x8の640 GBにはcheckpointだけでも収まらない。公式demoは16 GPU / 2 nodeで、BF16なら少なくともH200 x16級を安全側の比較構成とする |
| Kimi-K2 | MoE約1T、32B active、block-FP8 | metadata上のtensor storageは約1.03 TB（約958.5 GiB） | Modified MIT。重み公開、推奨engine公開 | H200 x8の1,128 GBは余裕が小さく、公式deployment guideの最小単位はFP8で16 GPU。AWS比較もH200 x16 / 2 nodeとする |

Qwenの55.6 GBは27,781,427,952 BF16 parametersを2 bytesとして算出した。DeepSeekとKimiはHugging Faceのpinned checkpoint metadataにあるdtype別tensor数から算出した。実機でのpeak memory保証値ではないため、QwenについてもH100 80 GBでのloadをpreflightし、CPU/disk offloadなしで収まらなければ不採用または構成再検討とする。

## AWS費用比較

比較条件はLinux、EC2 Capacity Blocks for ML、掲載表の米国東部価格（`p5.4xlarge`はN. Virginia、`p5e.48xlarge`はOhio）、最短1日である。Capacity Blockは1日単位、予約料金は前払いで、購入後は変更・キャンセルできない。実際のofferingは需給で変わるため、表は2026-09-13に確認した掲載単価による**比較見積もり**であり購入価格ではない。

| 候補・構成 | GPU memory | 掲載実効単価 | 4時間の作業時間相当 | 最短24時間の予約料金 |
|---|---:|---:|---:|---:|
| Qwen: `p5.4xlarge` x1（H100 x1） | 80 GB | $5.191/hour | $20.76 | **$124.58** |
| DeepSeek: `p5e.48xlarge` x2（H200 x16） | 2,256 GB | $95.52/hour | $382.08 | **$2,292.48** |
| Kimi: `p5e.48xlarge` x2（H200 x16） | 2,256 GB | $95.52/hour | $382.08 | **$2,292.48** |

`p5e.48xlarge` x1（H200 x8、1,128 GB、$47.76/hour、24時間で$1,146.24）はDeepSeek FP8 checkpointの容量上は候補になり得るが、公式demoの16 GPU構成を満たさないため、未検証の下限案として採用比較には使わない。Kimiもweightだけならx1に近いが、公式guideが16 GPUを最小単位としているためx2で比較した。いずれもengine・precisionが現在のQwen用runnerと異なり、同じconfigの差し替えだけでは実行できない。

上表にOS premium、EBS、tax、internet転送、artifact保管は含まない。Qwen実行の詳細見積もりと上限は[`PAID_GPU_PLAN.md`](PAID_GPU_PLAN.md)に記す。

## 推奨理由と反証条件

Qwenを推奨する主な理由は次のとおり。

- 比較構成の最短予約料金が、大規模MoE候補の約18分の1である
- 単一GPUかつ公式Transformers対応で、分散engine・通信topologyをcontrolled experimentの追加変数にしなくてよい
- dense checkpointとApache-2.0により、後続の内部介入と再配布条件を扱いやすい
- BF16のまま実行できる見込みがあり、FP8/量子化をbaseline契約へ持ち込まずに済む

一方、これはQwenが他候補より品質面で優れているという結論ではない。各model cardのbenchmarkは条件が揃っておらず、このpilot contractとも同一ではないため、横並びの採否根拠にしない。

HumanがQwenを採用しても、次のいずれかなら有料実行を中止し、primary選定またはAWS構成へ戻る。

- 購入前のCapacity Block offeringと付随料金が承認上限を超える
- H100 80 GBでCPU/disk offloadなしのBF16 loadに失敗する
- 固定revisionがrunnerの固定依存で動作しない
- 後続の脳型介入に必要なmodel componentへ安定したaccess pointを定義できない

## 一次情報

### Models

- [Pinned Qwen3.8-27B repository](https://huggingface.co/Qwen/Qwen3.8-27B/tree/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0): model card、config、BF16 weights、Apache-2.0
- [Qwen3.8 official repository](https://github.com/QwenLM/Qwen3.8): model familyと公式実行方法
- [Pinned DeepSeek-V3 repository](https://huggingface.co/deepseek-ai/DeepSeek-V3/tree/e815299b0bcbac849fa540c768ef21845365c9eb): FP8/BF16 tensor metadataとcheckpoint容量
- [DeepSeek-V3 official repository](https://github.com/deepseek-ai/DeepSeek-V3): 671B/37B構造、license、16 GPU / 2 nodeのdemo
- [DeepSeek-V3 weight description](https://github.com/deepseek-ai/DeepSeek-V3/blob/main/README_WEIGHTS.md): main weightsとMTPの内訳
- [Pinned Kimi-K2-Base repository](https://huggingface.co/moonshotai/Kimi-K2-Base/tree/bf2eca9bd560071ce3e29dac6cd32a6f1da3e601): block-FP8 checkpoint metadata
- [Kimi-K2 official repository](https://github.com/MoonshotAI/Kimi-K2): 1T/32B構造、Modified MIT
- [Kimi-K2 deployment guide](https://github.com/MoonshotAI/Kimi-K2/blob/main/docs/deploy_guidance.md): H200/H20上のFP8最小16 GPU構成
- [MMLU dataset repository](https://huggingface.co/datasets/cais/mmlu/tree/c30699e8356da336a370243923dbaf21066bb9fe): MIT、固定dataset revision

### AWS

- [EC2 accelerated instance specifications](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html): `p5.4xlarge`、`p5e.48xlarge`のGPU数とmemory
- [EC2 P5 instance details](https://aws.amazon.com/ec2/instance-types/p5/): vCPU、host memory、local NVMe、network
- [Capacity Blocks pricing](https://aws.amazon.com/ec2/capacityblocks/pricing/): region別の`p5.4xlarge`、`p5e.48xlarge`掲載単価
- [Finding and purchasing Capacity Blocks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-purchase.html): 1日単位、offering確認、予約後キャンセル不可
- [Capacity Blocks billing](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-blocks-pricing-billing.html): 需給連動価格、前払い
