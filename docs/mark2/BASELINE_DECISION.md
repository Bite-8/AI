# Mark2 primary baseline decision

- Status: **採用（実機再現性は未検証）**
- Decision date: 2026-09-13
- Primary baseline: `Qwen/Qwen3.8-27B`
- Immutable revision: `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`
- Scope: text-only, post-trained model, non-thinking mode, unquantized BF16

## 結論

`Qwen/Qwen3.8-27B` をprimary baselineに採用する。27B denseモデルで公開重みと設定があり、Apache-2.0で変更可能である。公式Hub APIが示す27,781,427,952 parametersとrepository file sizeから、BF16重みだけで約55.6GBを必要とする。実行時にはKV cache・activation・framework overheadも必要なため、初回候補は80GB級GPU 1基または同等以上とし、実測前に費用承認を得る。

本決定は「既存の高性能LLMを上回った」という結果ではない。モデル提供者の公表値、当リポジトリでの実測値、未検証事項は [`RESULTS.md`](RESULTS.md) で分離する。

## 候補比較

| 候補 | 公開構造・規模 | ライセンス | 介入可能性 | 初回primaryとしての判断 |
|---|---|---|---|---|
| Qwen3.8-27B | dense 27B、BF16 files 55.6GB | Apache-2.0 | 重み・設定公開、Transformers対応 | **採用**。単一80GB級GPUを第一候補にでき、他候補より検証可能性が高い |
| DeepSeek-V3 | MoE 671B total / 37B active、公式例は16 GPU・2 node | codeはMIT、weightsは独自Model License | 重み・推論code公開 | 必要な総weight容量と分散構成が大きいため見送り |
| Kimi-K2-Base | MoE 1T total / 32B active、checkpointはblock-FP8 | Modified MIT | base weights・推奨engine公開 | 大規模分散・FP8が前提となり、無量子化BF16契約との比較が困難なため見送り |

parameter数が近くても、MoEのactive parametersは保存・配置する総weight量を減らさない。このため「1 tokenあたりのactive parameters」だけでは実行可能性を判断していない。

## 固定した一次情報

- [Qwen3.8-27B model repository](https://huggingface.co/Qwen/Qwen3.8-27B/tree/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0): model card、設定、重み、Apache-2.0 license
- [Qwen3.8 official repository](https://github.com/QwenLM/Qwen3.8): model familyと公式実行方法
- [DeepSeek-V3 official repository](https://github.com/deepseek-ai/DeepSeek-V3): 671B/37B構造と分散実行例
- [Kimi-K2 official repository](https://github.com/MoonshotAI/Kimi-K2): 1T/32B構造、block-FP8、Modified MIT
- [MMLU dataset repository](https://huggingface.co/datasets/cais/mmlu/tree/c30699e8356da336a370243923dbaf21066bb9fe): MIT、固定dataset revision

## 判断上の制約と代替案

推奨案はunquantized BF16を80GB級GPUで動かすこと。これなら後続variantと同じ数値形式を保ちやすい。代替案は複数GPUへの自動配置であり、通信時間とGPU topologyを追加の固定条件にする必要がある。

4-bit/8-bit量子化は費用を下げるが、別baseline契約になるため自動fallbackしない。80GB級構成でもOOMまたは許容時間超過なら、Issueへ実測失敗manifestを提示し、(1) 複数GPU、(2) 固定方式の量子化、(3) 別primary候補、の順にHuman判断を求める。
