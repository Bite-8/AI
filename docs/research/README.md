# Mark2: brain-inspired AI architecture research

この文書は、Mark2のGoal、Success Criteria、Non-goals、完了条件、承認フローの **Single Source of Truth (SSoT)** である。ほかの文書やGitHub Issueに要約を置く場合も、この文書と矛盾させず、完了判定はこの文書を基準にする。

## Goal

公開された高性能LLMを再現可能なbaselineとして扱い、脳科学・計算論的神経科学から得た計算原理をcontrolled experimentによって検証できる研究基盤を作る。少なくとも一つの仮説についてbaselineとの比較結果を実測し、採用・修正・棄却の判断を根拠付きで行う。

## Success Criteria

1. baselineを固定条件で再現できる。
2. 評価条件を固定できる。
3. 仮説と反証条件を事前に記述できる。
4. 一つの独立変数のみを変更した比較実験ができる。
5. 複数seedで結果を比較できる。
6. 性能・計算量・メモリ・時間を記録できる。
7. 結果から採用・修正・棄却を判断できる。

## Non-goals

- 脳をそのまま再現すること。
- SNNやSTDPに最初から限定すること。
- 大規模モデルを一から学習すること。
- 脳らしいという理由だけで変更を採用すること。

## Completion condition

上記Success Criteriaを満たす最初のcontrolled experimentが完了した時点でMark2を完了とする。性能改善そのものは完了の必須条件ではない。悪化、無効果、不確実な結果も、固定条件で再現し、事前の反証条件と照合して修正または棄却を判断できれば研究結果として扱う。

文書に「実装済み」「完了」と書かれているだけでは達成済みと判断しない。コード、テスト、固定設定、実測結果などの証拠と照合し、すべてのSuccess Criteriaに証拠が揃った場合のみHumanがMark2の完了を決定する。

## Success principle

脳に近づけること自体を成功条件にしない。採用判断は、事前に決めた指標でbaselineに対する効果を測定して行う。改善しない結果も、条件と結果を再現できれば研究成果として残す。

## Level 2 Human-in-the-loop workflow

1. HumanがGoalまたは改善方向を定義する。
2. AIがrepositoryを調査する。
3. AIがIssue候補を提案する。
4. HumanがIssue候補を承認・修正・却下する。
5. AIは承認されたIssueのみ実装する。
6. AIが実装・テスト・実験・評価を行い、PRを作成する。
7. AIが結果と推奨を整理する。
8. Humanがmergeまたはrejectを決定する。

Goal、Success Criteria、Non-goals、完了条件の変更はHumanの明示的な承認を必要とする。AIは独断で変更または緩和しない。有料資源の起動など追加費用を伴う操作は、該当Issueの承認だけで許可されたとみなさず、実行条件と費用に対するHumanの承認を得る。

GitHub Issueは、Humanが承認した作業のScope、Acceptance Criteria、依存関係、進捗を管理するために使う。Goalや研究証跡のSSoTにはしない。GitHub Milestoneを使う場合も補助的な進捗表示に限定し、Issueのclose数をMark2の完了判定に使わない。

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

EC2 `t2.micro` の環境調査と、追加依存なしの `python3 -m ai_research.environment` を実装済み。固定版Qwen3.5-0.8Bの推論・記録コマンドも実装済み。設定と記録処理を検証したが、GPU実機でのモデル導入・推論は未実施。実験用資源の起動は未実施。詳細は [`ENVIRONMENT.md`](./ENVIRONMENT.md) を参照する。

- [x] 目的、非目的、成功原則を固定する
- [x] baseline候補の比較項目を定義する
- [x] 脳原理と現代AIの対応を記録する表を用意する
- [x] 一仮説・一変更の実験記録テンプレートを用意する
- [ ] 実行環境、利用可能な計算資源、再現性要件を記録する

### M2.1 — Baseline selection and reproduction

- [x] 候補を一次資料と実コードで調査する
- [ ] ライセンス、依存関係、必要計算資源を確認する
- [ ] 主baselineを一つ、必要なら小型proxyを一つ選ぶ
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
- [`FIRST_RUN_PLAN.md`](../experiments/FIRST_RUN_PLAN.md) — 初回モデル候補、東京リージョンの費用試算、起動前の準備
- [`EXPERIMENT_TEMPLATE.md`](../experiments/EXPERIMENT_TEMPLATE.md) — 仮説ごとの実験計画・結果・判断

調査中の断片は`docs/memo/`に置き、根拠と判断が揃った時点でこのディレクトリへ移す。モデル本体やデータセットはライセンスと容量を確認し、原則としてリポジトリへ直接コミットしない。

## Current Success Criteria audit

状態は `Achieved`、`Partially achieved`、`Not achieved`、`Evidence insufficient` のいずれかで記録する。実装やテンプレートだけがあり実測証拠がない場合は、達成済みにしない。

| Success Criterion | Status | Current evidence and gap |
|---|---|---|
| baselineを固定条件で再現できる | Partially achieved | 固定revision、設定、推論・記録コードはある。GPU実機でのモデル読込と独立した再実行のartifactはない |
| 評価条件を固定できる | Partially achieved | smoke testの固定入力・生成条件はある。研究判断用のdataset、split、品質指標、評価コードはない |
| 仮説と反証条件を事前に記述できる | Partially achieved | [`EXPERIMENT_TEMPLATE.md`](../experiments/EXPERIMENT_TEMPLATE.md) はある。記入済みの仮説と数値的な反証条件はない |
| 一つの独立変数のみを変更した比較実験ができる | Not achieved | intervention、variant切替、比較実験は未実装 |
| 複数seedで結果を比較できる | Not achieved | 現設定は単一seed。同一seedのrepeatは複数seed比較ではない |
| 性能・計算量・メモリ・時間を記録できる | Partially achieved | 推論時間とCUDAメモリの記録コードはある。品質指標、計算量、実測結果はない |
| 結果から採用・修正・棄却を判断できる | Not achieved | 判断テンプレートはあるが、完了した比較結果と判断記録はない |

この表は進捗の要約であり、詳細な実行順と各gateの成果物は [`WORKFLOW.md`](./WORKFLOW.md)、個別実験の条件と結果は `docs/experiments/`、確定した判断は `docs/decisions/` を参照する。
