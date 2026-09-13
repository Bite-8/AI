# Mark2 primary baseline candidate decision

- Status: **選定案（Human decision待ち、未採用）**
- Comparison date: 2026-09-13
- Research context: 個人研究（反復可能な費用と単一GPUでの変更容易性を優先）
- Recommended primary: `Qwen/Qwen3.5-9B`
- Candidate revision: `c202236235762e1c871ad0ccb60c8ee5ba337b9a`
- Proposed scope: text-only, post-trained model, non-thinking mode, unquantized BF16

## 結論

個人研究のprimary baselineには`Qwen/Qwen3.5-9B`を推奨する。まだ採用済みとはせず、Human確認後に決定する。

9Bは公開重み、Apache-2.0、公式Transformers対応で、公式公表のMMLU-Pro 82.5、GPQA Diamond 81.7と小型ながら強い。一方、BF16 checkpointは約19.3 GBでAWSのL4 24 GB 1基に収まる見込みがあり、On-Demandを数時間だけ使える。27BをH100 Capacity Blockで1回検証する案より、同じ予算で実装・失敗・再実行を何度も反復できることを重視した。

役割は次のように分ける。

- **Primary**: Qwen3.5-9B。仮説の採否を判断する固定baseline
- **Proxy**: Qwen3.5-4B。runnerや介入コードの安価な疎通用。proxyの改善をGoal達成の証拠にしない
- **Scale-up confirmation**: Qwen3.8-27B。9Bで有望な仮説だけを、別Issue・別契約・別予算で確認する

これにより「小さいモデルだけで結論を出す」ことも「毎回H100の24時間予約が必要で反復できない」ことも避ける。Goalの最終主張には、9Bだけで十分かを事前登録された複数benchmarkとscale-up確認の結果から改めて判断する。

Human判断は二段階に分ける。

1. 本書を確認し、Qwen3.5-9Bをprimary baselineとして採用する
2. 採用後、[`PAID_GPU_PLAN.md`](PAID_GPU_PLAN.md) の実行直前単価、上限額、停止条件を別途承認する

## 個人研究向け評価軸

候補は次の順で評価した。

1. 1人で繰り返し支払える1 experiment cycleの費用
2. 単一GPU、無量子化BF16、CPU/disk offloadなしで動かせること
3. 公開重み・許容的license・内部componentへ介入できること
4. 高性能baselineと呼べる提供者公表値を持つこと
5. 新しさや最大性能。ただし、反復不能になる場合は優先しない

provider公表benchmarkは実行条件がrepositoryのpilotと異なるため、候補の大まかな能力帯の確認にだけ使い、repository実測値として扱わない。

## 候補比較

| 候補 | BF16 weight / 構造 | provider公表値の例 | AWSでの最小現実案 | 個人研究での役割 |
|---|---:|---:|---|---|
| Qwen3.5-4B | 9.33 GB / dense 4.66B | MMLU-Pro 79.1 | L4 24 GB x1 | 安価なproxy。primaryより能力余裕が小さい |
| **Qwen3.5-9B** | **19.32 GB / dense 9.65B** | **MMLU-Pro 82.5、GPQA 81.7** | **`g6.2xlarge`, L4 24 GB x1, On-Demand** | **推奨primary。品質・費用・単一GPU介入の均衡が最良** |
| Qwen3.5-35B-A3B | 71.93 GB / MoE 35.95B, 3B active | MMLU-Pro 85.3 | H100 80 GBは余裕が小さくpreflightリスクあり | 9Bとの差に対しweight配置とMoE介入が重い |
| Qwen3.8-27B | 55.62 GB / dense 27.78B | Qwenが同family中の高能力世代として公表 | `p5.4xlarge`, H100 80 GB x1 Capacity Block | 有望仮説のscale-up確認。初期反復には高価 |
| DeepSeek-V3 / Kimi-K2 | 約689 GB / 約1.03 TB / 大規模MoE | 条件不統一のため数値比較しない | 公式例は16 GPU級 | 個人研究のprimaryから除外 |

weight値は2026-09-13にHugging Face APIのpinned repository metadataから確認したtensor storageで、KV cache、activation、CUDA context、workspaceを含まない。

## AWS費用と反復性

Qwen3.5-9Bは`g6.2xlarge`（L4 24 GB x1、host RAM 32 GiB、local NVMe 450 GB）のLinux On-Demandを第一候補にする。On-Demandは60秒最低の秒課金で、長期契約・前払いがなく、短期で中断させたくない不定期workload向けとAWSが説明している。

2026-09-13にAWS Price List相当で確認したUS East (N. Virginia)の参考単価は$0.9776/hourで、4時間のcomputeは$3.91である。実行直前にAWS accountで単価とAZ availabilityを再確認する。これに対し、Qwen3.8-27B用`p5.4xlarge` Capacity Blockの既調査案は最低24時間$124.58だった。単純な1 cycle比較で約32分の1であり、個人研究では9Bを約30 cycle試せる予算を27Bの1予約に固定しない方がよい。

Spotはさらに安い可能性があるが、2分前通知で中断され得る。最初の再現性baselineは環境差を増やさないOn-Demandとし、checkpoint付きで中断耐性を持つ後続batchだけをSpot候補にする。

## 採用後の反証・昇格条件

次のいずれかなら実行を止め、primaryまたは構成を再検討する。

- L4 24 GBで単一GPU BF16 loadに失敗する、または余裕不足で100問を完走できない
- 固定revisionが固定依存で動かない
- 脳型介入に必要なcomponentへ安定したaccess pointを定義できない
- repositoryの事前登録benchmarkで高性能baselineとして不十分と判定される

9B上で再現可能な改善が出た後は、仮説を最大3件程度に絞り、同じ独立変数をQwen3.8-27Bへ移してscale-up確認する。27Bを日常の開発loopには使わない。

## 一次情報

- [Pinned Qwen3.5-9B repository](https://huggingface.co/Qwen/Qwen3.5-9B/tree/c202236235762e1c871ad0ccb60c8ee5ba337b9a): weights、config、model card、Apache-2.0
- [Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md): provider公表benchmark
- [Pinned Qwen3.5-4B repository](https://huggingface.co/Qwen/Qwen3.5-4B/tree/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a): proxy候補
- [Pinned Qwen3.5-35B-A3B repository](https://huggingface.co/Qwen/Qwen3.5-35B-A3B/tree/59d61f3ce65a6d9863b86d2e96597125219dc754): MoE候補
- [Pinned Qwen3.8-27B repository](https://huggingface.co/Qwen/Qwen3.8-27B/tree/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0): scale-up候補
- [Qwen3.8 official repository](https://github.com/QwenLM/Qwen3.8): official familyと実行方法
- [MMLU dataset repository](https://huggingface.co/datasets/cais/mmlu/tree/c30699e8356da336a370243923dbaf21066bb9fe): MIT、固定revision
- [EC2 G6 specifications](https://aws.amazon.com/ec2/instance-types/g6/): L4 GPUとmemory
- [EC2 accelerated instance specifications](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html): `g6.2xlarge`のhost、GPU、NVMe
- [EC2 On-Demand](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-on-demand-instances.html): 秒課金、60秒最低、前払いなし
- [EC2 On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/): 実行前に再確認する単価
- [EC2 Spot best practices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-best-practices.html): 中断特性
