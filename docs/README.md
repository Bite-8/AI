# docs

このディレクトリは、AI実験プロジェクトの設計メモ、実装記録、学習ログをまとめる場所です。

コードだけでは追いにくい「何を作るのか」「なぜその設計にしたのか」「実装して何が分かったのか」を残します。

## 基本方針

- [`research/`](./research/) — 現在進行中の研究の計画・進行状況・実行手順（Mark2 LLM実行の方法など）
- [`experiments/`](./experiments/) — 実験テンプレートと個別実験の計画・証跡（`evidence/` に生データを保存）
- [`decisions/`](./decisions/) — baseline選定など、根拠付きの意思決定記録
- [`reference/`](./reference/) — 特定の研究フェーズに紐付かない技術解説（Transformerの内部構造など）
- [`memo/`](./memo/) — 整理前のメモや作業中の考え

現在完了している世代はMark1のみです。当時の計画・進捗・完了レポートはgit tag `mark1` とそのGitHub Releaseを参照してください。今も参照価値のある実装とドキュメントは [`prototypes/numpy_transformer/`](../prototypes/numpy_transformer/) と [`reference/`](./reference/) に移してあります。
