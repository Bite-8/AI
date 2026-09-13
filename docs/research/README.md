# Mark2: brain-inspired AI architecture research

Mark2の目的は、ルートの [`GOAL.md`](../../GOAL.md) をSingle Source of Truthとする。この文書は、その目的を実証するための研究ループ、stage gate、到達判定、現在の証拠と未達部分を記録する。Goalにない条件を、この文書だけで目的や完了条件として追加しない。

## Research loop

1. **現代AIを理解する** — DeepSeek、Qwen、Kimiなど、構造・コード・重み・技術情報の公開範囲を確認し、実際に動かして学習・推論処理を追う。
2. **脳の計算原理を調査する** — 可塑性、複数時間スケール、樹状突起計算、neuromodulation、sparsity、population dynamicsなどを継続的に調べる。SNNやSTDPだけに限定しない。
3. **比較して仮説を立てる** — AIに既に存在する対応物、不足している原理、期待する効果、反証条件を明文化する。
4. **最小単位で実装する** — 一度に一原理・一変更とし、元モデルを常にbaselineとして再実行可能に保つ。
5. **評価する** — 精度・推論能力に加え、仮説に応じて学習効率、継続学習、適応能力、計算量、メモリ使用量を測る。
6. **反復する** — 採用、修正、棄却を根拠とともに記録し、次の仮説につなげる。

## Stage gates

Mark2は、以下の順に進める。未達のgateを飛ばして大規模実装に進まない。

### M2.0 — Research foundation（現在）

EC2 `t2.micro` の環境調査と、追加依存なしの `python3 -m ai_research.environment` を実装済み。開発用proxy候補である固定版Qwen3.5-0.8Bの推論・記録コマンドも実装済み。設定と記録処理を検証したが、GPU実機でのモデル導入・推論は未実施。高性能reference baselineは未決定で、実験用資源の起動も未実施。詳細は [`ENVIRONMENT.md`](./ENVIRONMENT.md) を参照する。

- [x] Goalの研究目的を確認する
- [ ] 「高性能」と「上回る」を判定するモデル・課題・指標・許容差を固定する
- [x] baseline候補の比較項目を定義する
- [x] 脳原理と現代AIの対応を記録する表を用意する
- [x] 一仮説・一変更の実験記録テンプレートを用意する
- [ ] 実行環境、利用可能な計算資源、再現性要件を記録する

### M2.1 — Baseline selection and reproduction

- [x] 候補を一次資料と実コードで調査する
- [ ] ライセンス、依存関係、必要計算資源を確認する
- [ ] 公開された高性能LLMからreference baselineを一つ選ぶ
- [ ] 継続的に改変する小型proxyを選び、reference baselineとの関係と外挿しない範囲を決める
- [ ] 固定データ・固定seedで推論と評価を再現する
- [ ] baselineの重要なデータフローをコード位置とともに説明する

### M2.2 — Hypothesis backlog

- [ ] 少なくとも3つの脳計算原理を一次文献から整理する
- [ ] 各原理について現代AIの対応物と差分を記録する
- [ ] 効果、介入箇所、反証条件、コストから最初の仮説を選ぶ

### M2.3 — First controlled experiment

- [ ] baselineを変更せず再実行できる状態を保つ
- [ ] 一つの独立変数だけを変更する
- [ ] 同じ評価条件で複数seedを比較する
- [ ] 精度だけでなく計算量・メモリ・実行時間を記録する
- [ ] 採用・修正・棄却の判断と次の実験を記録する

## Working documents

- [`RUNNING.md`](./RUNNING.md) — 推論コマンド、GPU環境の準備、結果の読み方と検証範囲
- [`WORKFLOW.md`](./WORKFLOW.md) — 現在のコードを起点とする作業順と到達条件
- [`ENVIRONMENT.md`](./ENVIRONMENT.md) — 実測環境、未決定の予算、環境確認コマンド
- [`PRINCIPLE_MATRIX.md`](./PRINCIPLE_MATRIX.md) — 脳の計算原理と現代AIの対応・差分
- [`baseline-selection.md`](../decisions/baseline-selection.md) — 公開モデル候補の選定表と採否
- [`FIRST_RUN_PLAN.md`](../experiments/FIRST_RUN_PLAN.md) — development proxy初回候補、東京リージョンの費用試算、起動前の準備
- [`EXPERIMENT_TEMPLATE.md`](../experiments/EXPERIMENT_TEMPLATE.md) — 仮説ごとの実験計画・結果・判断

調査中の断片は`docs/memo/`に置き、根拠と判断が揃った時点でこのディレクトリへ移す。モデル本体やデータセットはライセンスと容量を確認し、原則としてリポジトリへ直接コミットしない。

## Current goal audit

Goalの各主張を、実証に必要な証拠へ分解して監査する。状態は `Achieved`、`Partially achieved`、`Not achieved`、`Evidence insufficient` のいずれかで記録する。小型proxyだけの結果を、高性能reference baselineでの改善証拠へ外挿しない。実装やテンプレートだけがあり実測証拠がない場合も達成済みにしない。

| Goal evidence | Status | Current evidence and gap |
|---|---|---|
| 公開された高性能LLMをreference baselineとして固定し再現する | Not achieved | Qwen3.8-27Bを推奨候補として調査したが未決定・未実行。Qwen3.5-0.8B用コードはproxyの疎通準備に限られる |
| 比較に使う能力指標と評価条件を固定する | Partially achieved | smoke testの固定入力・生成条件はある。研究判断用のdataset、split、品質指標、評価コードはない |
| 脳科学・計算論的神経科学の原理から反証可能な仮説を立てる | Partially achieved | [`EXPERIMENT_TEMPLATE.md`](../experiments/EXPERIMENT_TEMPLATE.md) はある。一次文献で埋めた原理候補、介入箇所、数値的な反証条件はない |
| 一つの独立変数だけを変えたcontrolled experimentを再現する | Not achieved | intervention、variant切替、複数seed比較、実測artifactはない |
| 高性能reference baselineを上回る改善を実証する | Not achieved | proxy・referenceのいずれにも比較結果がない。最終主張には同一評価条件でのreference上の改善と追加コストが必要 |
| 有効な原理を特定し統合する | Not achieved | 採用済みの原理はなく、統合実験もない |

この表は進捗の要約であり、詳細な実行順と各gateの成果物は [`WORKFLOW.md`](./WORKFLOW.md)、個別実験の条件と結果は `docs/experiments/`、確定した判断は `docs/decisions/` を参照する。Mark2の到達は、最後の2行を含むGoal全体に実測証拠が揃った場合にのみ判断する。
