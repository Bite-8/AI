# Baseline survey

## 選定ルール

候補名を先に固定せず、一次資料と実行結果で比較する。最大性能だけではなく、介入可能性と実験再現性を重視する。

### 必須条件

- アーキテクチャと推論コードを確認できる
- 研究目的に適合するライセンス条件を確認できる
- 固定条件でbaseline評価を再実行できる
- 変更対象を局所化し、無変更版と比較できる

### 初回候補の比較（2026-09-08）

モデル公式の設定とライセンス、Transformers実装を読み取りで確認した。重みのダウンロード・推論・学習は未実施。初回の実装コストを抑えるため、今回は小型Qwen候補を比較した。DeepSeek・Kimiを含む全モデルの網羅調査や、世界最高性能の選定ではない。

| 候補 | コードから確認した構造 | 研究上の役割 | 推論の試行案 | 学習資源・再現性 | 状態 |
|---|---|---|---|---|---|
| Qwen3-0.6B | 28層、GQA、RoPE、RMSNorm、gated MLP | Mark1からの構造理解が容易な代替候補 | T4 / FP16、短文・batch 1 | 未測定 | 保留 |
| Qwen3.5-0.8B | 24層、linear attention 18層とfull attention 6層、vision encoderあり | ハイブリッド構造と内部状態を調べる初回候補 | L4 / BF16、テキストのみ・短文・batch 1 | 未測定 | 初回の第一候補 |
| Qwen3.5-4B | 32層、linear attention 24層とfull attention 8層、vision encoderあり | 小型実験後の拡張候補 | L4候補、実メモリは要検証 | 未測定。全体学習が同じGPUで可能とはしない | 後続候補 |

0.8B/4BのFFNは確認した実装ではdense gated MLP。モデル系列全般のMoEという説明を、これらの個別モデルに当てはめない。推論状態の更新を学習済み重みの更新とも同一視しない。

### 固定したモデルrevisionと公開範囲

3候補ともモデルカードとLICENSE本文でApache-2.0を確認した。再配布・派生物の公開時には原文の条件を満たす。コード・重みの公開は、学習データと学習工程の完全公開を意味しない。

- **Qwen/Qwen3-0.6B**: `c1899de289a04d12100db370d81485cdf75e47ca` — [モデルカード](https://huggingface.co/Qwen/Qwen3-0.6B/blob/c1899de289a04d12100db370d81485cdf75e47ca/README.md)、[config](https://huggingface.co/Qwen/Qwen3-0.6B/resolve/c1899de289a04d12100db370d81485cdf75e47ca/config.json)、[LICENSE](https://huggingface.co/Qwen/Qwen3-0.6B/resolve/c1899de289a04d12100db370d81485cdf75e47ca/LICENSE)。
- **Qwen/Qwen3.5-0.8B**: `2fc06364715b967f1860aea9cf38778875588b17` — [モデルカード](https://huggingface.co/Qwen/Qwen3.5-0.8B/blob/2fc06364715b967f1860aea9cf38778875588b17/README.md)、[config](https://huggingface.co/Qwen/Qwen3.5-0.8B/resolve/2fc06364715b967f1860aea9cf38778875588b17/config.json)、[LICENSE](https://huggingface.co/Qwen/Qwen3.5-0.8B/resolve/2fc06364715b967f1860aea9cf38778875588b17/LICENSE)。
- **Qwen/Qwen3.5-4B**: `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` — [モデルカード](https://huggingface.co/Qwen/Qwen3.5-4B/blob/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/README.md)、[config](https://huggingface.co/Qwen/Qwen3.5-4B/resolve/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/config.json)、[LICENSE](https://huggingface.co/Qwen/Qwen3.5-4B/resolve/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/LICENSE)。

公開メタデータ・configの取得結果は [調査記録](./evidence/models-2026-09-08.json) に保存した。名前に含まれるパラメーター数を、そのまま必要VRAMと扱わない。読込対象、共有重み、vision encoder、キャッシュ、活性値、precisionによって変わる。

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

## Decision

- **Primary baseline**: 研究用の正式採用は未決定。初回実行はQwen3.5-0.8Bを第一候補とする
- **Small proxy**: Qwen3-0.6Bは構造理解用の代替候補。Qwen3.5の同等proxyとは扱わない
- **提案日**: 2026-09-08（実行後に採否を更新）
- **根拠**: 小さい公開モデルで最近のハイブリッド構造を理解し、状態の扱いを含む比較研究の入口を作る。予算条件は [初回実行計画](./FIRST_RUN_PLAN.md) を参照
- **保留理由**: 4Bは実行基盤の確認後へ回す。Qwen3は初回に複数モデルを持ち込む工数を避けるため代替に留める。品質と費用の優劣は未測定
