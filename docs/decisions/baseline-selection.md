# Baseline survey

## 選定ルール

候補名を先に固定せず、一次資料と実行結果で比較する。最大性能だけではなく、介入可能性と実験再現性を重視する。

### 必須条件

- アーキテクチャと推論コードを確認できる
- 研究目的に適合するライセンス条件を確認できる
- 固定条件でbaseline評価を再実行できる
- 変更対象を局所化し、無変更版と比較できる
- 公開情報と固定評価に基づき「高性能LLM」を比較対象として説明できる

Goalに対する比較対象を **reference baseline**、反復開発に使う小型モデルを **development proxy** と呼ぶ。reference baselineは最終的な改善主張の比較対象であり、proxyは実装・デバッグ・仮説の早期棄却に使う。proxy上の改善をreference baseline上の改善へ外挿しない。

### 高性能reference候補の追加調査（2026-09-13）

2026-09-08の小型候補調査後にGoalが「既存の高性能LLMを上回る改善」へ更新されたため、公開された高性能モデルを追加調査した。以下の性能値はモデル提供者の公表値であり、このリポジトリでは未再現である。

| 候補 | 公開情報から確認した位置付け | 介入可能性 | 資源上の影響 | 状態 |
|---|---|---|---|---|
| Qwen3.8-27B | Qwenが公開モデル系列で最も高性能な世代と説明。公表値はGPQA Diamond 89.2、LiveCodeBench v6 90.3など | Apache-2.0の重みを取得可能。Qwen3.5系のGated DeltaNet / full attention構成を引き継ぐため、proxyとの介入概念を対応付けやすい | 27B denseのBF16重みだけで概算54 GB。現在のL4 22 GiB単機案では無量子化読込を見込めず、別構成の見積もりが必要 | **reference推奨案、未決定・未実行** |
| Qwen3.5-35B-A3B | 35B total / 3B activeの公開MoE。Qwen3.5-Flashに対応する公開重みと説明される | Apache-2.0の重みを取得可能。0.8Bと同世代だが、dense FFNからMoEへ変わるため介入の同一性に注意が必要 | 配布物は約72 GB。active parameter数が小さくても全weightの保存・読込費用は小さくならない | 代替案、未実行 |

Qwen3.8-27Bの固定候補revisionは `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`、Qwen3.5-35B-A3Bは `59d61f3ce65a6d9863b86d2e96597125219dc754`。いずれも2026-09-13にGitの`HEAD`参照を確認した固定点であり、採用決定ではない。

- [Qwen3.8-27B model card](https://huggingface.co/Qwen/Qwen3.8-27B/blob/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/README.md) / [config](https://huggingface.co/Qwen/Qwen3.8-27B/resolve/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/config.json) / [LICENSE](https://huggingface.co/Qwen/Qwen3.8-27B/resolve/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/LICENSE)
- [Qwen3.5-35B-A3B model card](https://huggingface.co/Qwen/Qwen3.5-35B-A3B/blob/59d61f3ce65a6d9863b86d2e96597125219dc754/README.md) / [config](https://huggingface.co/Qwen/Qwen3.5-35B-A3B/resolve/59d61f3ce65a6d9863b86d2e96597125219dc754/config.json) / [LICENSE](https://huggingface.co/Qwen/Qwen3.5-35B-A3B/resolve/59d61f3ce65a6d9863b86d2e96597125219dc754/LICENSE)

### development proxy候補の比較（2026-09-08）

モデル公式の設定とライセンス、Transformers実装を読み取りで確認した。重みのダウンロード・推論・学習は未実施。初回の実装コストを抑えるため、今回は小型Qwen候補を比較した。DeepSeek・Kimiを含む全モデルの網羅調査や、世界最高性能の選定ではない。

| 候補 | コードから確認した構造 | 研究上の役割 | 推論の試行案 | 学習資源・再現性 | 状態 |
|---|---|---|---|---|---|
| Qwen3-0.6B | 28層、GQA、RoPE、RMSNorm、gated MLP | Mark1からの構造理解が容易な代替候補 | T4 / FP16、短文・batch 1 | 未測定 | 保留 |
| Qwen3.5-0.8B | 24層、linear attention 18層とfull attention 6層、vision encoderあり | ハイブリッド構造と内部状態を調べるdevelopment proxy | L4 / BF16、テキストのみ・短文・batch 1 | 未測定 | proxy第一候補 |
| Qwen3.5-4B | 32層、linear attention 24層とfull attention 8層、vision encoderあり | 小型実験後の拡張候補 | L4候補、実メモリは要検証 | 未測定。全体学習が同じGPUで可能とはしない | 後続候補 |

0.8B/4BのFFNは確認した実装ではdense gated MLP。モデル系列全般のMoEという説明を、これらの個別モデルに当てはめない。推論状態の更新を学習済み重みの更新とも同一視しない。

### 固定したモデルrevisionと公開範囲

3候補ともモデルカードとLICENSE本文でApache-2.0を確認した。再配布・派生物の公開時には原文の条件を満たす。コード・重みの公開は、学習データと学習工程の完全公開を意味しない。

- **Qwen/Qwen3-0.6B**: `c1899de289a04d12100db370d81485cdf75e47ca` — [モデルカード](https://huggingface.co/Qwen/Qwen3-0.6B/blob/c1899de289a04d12100db370d81485cdf75e47ca/README.md)、[config](https://huggingface.co/Qwen/Qwen3-0.6B/resolve/c1899de289a04d12100db370d81485cdf75e47ca/config.json)、[LICENSE](https://huggingface.co/Qwen/Qwen3-0.6B/resolve/c1899de289a04d12100db370d81485cdf75e47ca/LICENSE)。
- **Qwen/Qwen3.5-0.8B**: `2fc06364715b967f1860aea9cf38778875588b17` — [モデルカード](https://huggingface.co/Qwen/Qwen3.5-0.8B/blob/2fc06364715b967f1860aea9cf38778875588b17/README.md)、[config](https://huggingface.co/Qwen/Qwen3.5-0.8B/resolve/2fc06364715b967f1860aea9cf38778875588b17/config.json)、[LICENSE](https://huggingface.co/Qwen/Qwen3.5-0.8B/resolve/2fc06364715b967f1860aea9cf38778875588b17/LICENSE)。
- **Qwen/Qwen3.5-4B**: `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` — [モデルカード](https://huggingface.co/Qwen/Qwen3.5-4B/blob/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/README.md)、[config](https://huggingface.co/Qwen/Qwen3.5-4B/resolve/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/config.json)、[LICENSE](https://huggingface.co/Qwen/Qwen3.5-4B/resolve/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/LICENSE)。

公開メタデータ・configの取得結果は [調査記録](../experiments/evidence/models-2026-09-08.json) に保存した。名前に含まれるパラメーター数を、そのまま必要VRAMと扱わない。読込対象、共有重み、vision encoder、キャッシュ、活性値、precisionによって変わる。

### 読んだ実装と介入可能性

Transformers調査commit: `0a959de1d2dd0c981f1f732dbd0fc31192bbfa66`。これはコード読解の固定点であり、実行環境の動作検証済みバージョンではない。

- [Qwen3実装](https://github.com/huggingface/transformers/blob/0a959de1d2dd0c981f1f732dbd0fc31192bbfa66/src/transformers/models/qwen3/modeling_qwen3.py): `Qwen3DecoderLayer.forward` は正規化 → Attention → 残差 → 正規化 → MLP → 残差。`Qwen3MLP.forward` はgate/up/downの射影を持ち、処理単位を追いやすい。
- [Qwen3.5実装](https://github.com/huggingface/transformers/blob/0a959de1d2dd0c981f1f732dbd0fc31192bbfa66/src/transformers/models/qwen3_5/modeling_qwen3_5.py): `Qwen3_5DecoderLayer` が層種別を切り替え、`Qwen3_5GatedDeltaNet.forward` はconv/recurrent stateを扱う。`torch_chunk_gated_delta_rule` と `torch_recurrent_gated_delta_rule` があり、まとまった入力と逐次生成の経路の理解が必要。MLPだけでなく状態更新の介入も検討できるが、変更方針はまだ選ばない。

公式カードのconfigにある `transformers_version` は、現在の実行に必要な最小版の保証と解釈しない。実行依存は次の実装段階で固定・検証する。

## Reproduction record

選定したbaselineについて、次を固定して記録する。

- repository URL / commit SHA / model revision
- ライセンスと利用上の制約
- Python、accelerator、driver、主要依存関係の版
- ハードウェア、precision、seed、入力長、batch size
- データセット名・版・split・取得方法
- 実行コマンド、設定ファイル、出力artifactの場所
- 品質指標、wall-clock time、peak memory、演算量の推定方法

## Proposed decision

- **Reference baseline推奨案**: Qwen3.8-27B。公開された高性能モデルであり、Qwen3.5-0.8Bと介入概念を対応付けやすい。評価軸と実行費用を確認してから正式採用する
- **Development proxy推奨案**: Qwen3.5-0.8B。既存の固定設定とrunnerを活用する。proxy初回計画は [FIRST_RUN_PLAN.md](../experiments/FIRST_RUN_PLAN.md) を参照
- **Proxy代替**: Qwen3-0.6BはAttention中心の構造理解用。Qwen3.8のGated DeltaNet介入を先行検証するproxyにはならない
- **Reference代替**: Qwen3.5-35B-A3B。0.8Bと同世代だがMoE差分と配布サイズがあり、現時点ではQwen3.8-27Bより優先しない
- **提案更新日**: 2026-09-13（正式採用、実行構成、評価軸は未決定）
- **未解決事項**: Qwen3.8-27Bの無変更実行と改変後評価に必要なGPU構成・費用、採用する公開benchmark、proxyからreferenceへ移植して同一介入とみなす条件

現在の`ai_research/run.py`はQwen3.5-0.8B専用であり、reference baselineを実行できない。referenceの実行コードを先に推測で追加せず、モデル・評価軸・予算の決定後に、固定revision、依存版、precision、推論方式を別設定として実装する。
