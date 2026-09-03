# Baseline survey

## 選定ルール

候補名を先に固定せず、一次資料と実行結果で比較する。最大性能だけではなく、介入可能性と実験再現性を重視する。

### 必須条件

- アーキテクチャと推論コードを確認できる
- 研究目的に適合するライセンス条件を確認できる
- 固定条件でbaseline評価を再実行できる
- 変更対象を局所化し、無変更版と比較できる

### 比較項目

| 候補 | 正確な版・commit | 一次資料 | コード | 重み | ライセンス | 推論資源 | 学習/finetune資源 | 評価再現性 | 介入しやすさ | 状態 |
|---|---|---|---|---|---|---:|---:|---|---|---|
| DeepSeek系 | 未調査 | — | — | — | — | — | — | — | — | backlog |
| Qwen系 | 未調査 | — | — | — | — | — | — | — | — | backlog |
| Kimi系 | 未調査 | — | — | — | — | — | — | — | — | backlog |

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

- **Primary baseline**: 未決定
- **Small proxy**: 未決定
- **決定日**: —
- **根拠**: —
- **不採用候補と理由**: —
