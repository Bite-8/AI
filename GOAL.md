# Project Goal

このファイルは、現在のプロジェクトのGoal、Success Criteria、Non-goals、完了条件の **Single Source of Truth (SSoT)** である。AIは作業を始める前にこのファイルとリポジトリの現状を照合し、Goal達成に残っている差分を基準に作業を提案・実装する。

## Current goal: Mark2

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

文書に「実装済み」「完了」と書かれているだけでは達成済みと判断しない。コード、テスト、固定設定、実測結果などの証拠と照合し、すべてのSuccess Criteriaに証拠が揃った場合のみユーザーがMark2の完了を決定する。

## Success principle

脳に近づけること自体を成功条件にしない。採用判断は、事前に決めた指標でbaselineに対する効果を測定して行う。改善しない結果も、条件と結果を再現できれば研究成果として残す。

## Goal-driven workflow

1. AIはこのファイルを読み、コード、テスト、設定、実測証拠とSuccess Criteriaの差分を確認する。
2. AIはGoalへ寄与する、レビュー可能な大きさの作業を一つ選ぶ。安全かつ可逆な範囲は、個別の着手承認を待たずに調査・実装・検証する。
3. AIは変更をbranchにまとめ、テストと根拠を添えてPRを作成する。安全かつ可逆な作業に、別途の事前承認を求めない。
4. ユーザーの判断が必要なら、AIは推奨案をPRの差分に反映したうえで、PR本文の `Human decisions required` に質問、推奨理由、代替案と影響を書く。
5. ユーザーはPRのreviewまたはcommentで承認・変更・却下を伝える。AIは回答を差分へ反映し、未解決の判断がなくなってからmerge可能な状態にする。
6. ユーザーがPRをmergeまたはrejectする。mergeはPRに含まれるリポジトリ変更への承認であり、有料資源の起動や外部システムの変更まで自動的に許可するものではない。
7. merge後は、次の作業で再びGoalとの差分を確認する。PR番号やclose数をGoal達成の判定には使わない。

## Decision boundaries

判断事項は、その状態と用途に応じて次の場所に置く。

| 内容 | 置き場所 | 扱い |
|---|---|---|
| レビュー中の質問、選択肢、推奨 | PR本文の `Human decisions required` | ユーザーはreview/commentで回答する |
| 選択によって変わる値 | コードまたは`configs/` | 推奨値を実際の差分として提示する |
| 長期的に参照する確定判断と根拠 | `docs/decisions/` | 合意内容を反映してからmergeする |
| 実験条件、結果、採否 | `docs/experiments/` | 実行前の条件と実行後の証拠を残す |
| 未整理の着想 | `docs/memo/` | Goalや着手済み作業とはみなさない |

質問だけを確定文書へ保存しない。PR上で判断が確定したら、将来の再現や説明に必要な内容だけを設定、実験記録、またはdecision documentへ反映する。PRの会話だけに、実行条件や重要な設計判断を残さない。

有料計算資源の起動、課金増加、外部公開、データ削除など、リポジトリ外に副作用を起こす操作には別途明示的な承認を必要とする。AIはPR本文に対象、構成、上限費用、上限時間、停止・復旧方法を示し、ユーザーがその実行を明示的に承認するまで操作しない。

## Supporting documents

- [`docs/research/README.md`](./docs/research/README.md) — 現在地とSuccess Criteriaの証拠監査
- [`docs/research/WORKFLOW.md`](./docs/research/WORKFLOW.md) — Mark2の研究上の実行順とstage gate
- [`docs/research/ENVIRONMENT.md`](./docs/research/ENVIRONMENT.md) — 実行環境、資源、費用条件
- [`docs/decisions/`](./docs/decisions/) — 確定した重要判断
- [`docs/experiments/`](./docs/experiments/) — 実験計画、結果、証拠
