# L4 autonomous development workflow proposal

Status: Draft for review

Tracking issue: [#37](https://github.com/Bite-8/AI/issues/37)

## 1. この文書の目的

この文書は、Humanを通常のIssue作成、実装承認、PR review、修正確認、mergeから外し、AIが`GOAL.md`へ向かう開発loopを継続するための初期設計案である。

ここでいうL4は製品一般の自律化levelではなく、このrepositoryにおけるAI駆動開発の自律化levelを表す便宜上の呼称とする。

このPRでは方針を提案するだけで、Human gateの解除、GitHub ruleset変更、自動merge、有料resourceの操作は行わない。

## 2. 背景と問題

現在の定期実行promptは、次の2つのHuman gateを必須にしている。

1. Issueの実装承認
2. PRのApprove reviewとmerge

この方式は誤った変更を止めやすい一方、すべての通常作業でHumanの応答を必要とするため、Humanが開発速度の上限になる。

一方で、Human gateを単純に削除してGoalだけを渡しても自律開発にはならない。過去の運用では、Goalから次の作業を一意に決められず、各Agentが「まだ検討されていないため実装できない」と判断して停止した。

原因はGoalの不足というより、Humanが暗黙に担っていた次の機能が開発systemへ移されていなかったことにある。

- 現在地点とGoalの差分を特定する
- 候補作業を生成し、優先順位を付ける
- 不明点を調査、実験、判断、escalationへ分類する
- 作業開始条件と完了条件を定める
- riskを分類する
- review、修正、mergeの状態遷移を制御する

L4化の中心は、Human reviewをAI reviewへ置換することではなく、これらの制御を明示的な契約と検証可能な状態遷移へ移すことである。

## 3. 現在のrepository状態

2026-09-25の調査時点では次の状態である。

- Open Issueは#30、#33、tracking用の#37の3件
- Open PRは#34の1件
- PR #34にはHumanの`LGTM!`コメントがあるが、formal reviewは0件
- PR #34にはstatus checkがなく、repositoryにもGitHub Actions workflowがない
- `main`のrulesetはPR経由、branch削除禁止、non-fast-forward禁止を設定している
- required status checkは設定されていない
- `GOAL.md`は研究の方向を示すが、現在地点、優先順位、作業選択規則、検証可能な完了条件までは定義していない
- PR #34のbranchと`main`は分岐しており、`main`側にだけ6 commits、PR側にだけ3 commitsある
- 実機baselineは未実行であり、Qwen3.5-9BのNVIDIA L4 GPU上でのload、実行時間、peak memory、独立2 runの一致は未検証

したがって、現在はHuman gateをそのまま解除できる状態ではない。先にAIが担う判断契約と、決定論的なmerge gateを作る必要がある。

## 4. 設計原則

### 4.1 Humanは通常loopではなくpolicyを所有する

Humanの主な責務を次に限定する。

- Project Goalと方向性の決定
- 成功条件、non-goal、risk policyの決定
- AIへ委譲する権限、費用、時間の上限設定
- 技術的証拠だけでは決められない価値判断
- 不可逆または高riskな例外判断

安全で可逆なrepository内の通常作業はAIへ委譲する。

### 4.2 未知であること自体をblockerにしない

「何をしたらよいか」「どれが正解か」が不明な場合、すぐHumanへ質問せず、事実調査、比較実験、可逆な推奨案の採用の順で解消する。

### 4.3 LLMで判定する必要がないものはCIへ移す

Test、format、schema、artifact整合、SHA一致など、決定論的に検証できる条件をReview Agentへ判断させない。

### 4.4 Reviewとmerge制御を分離する

Review Agentは問題の検出と判定を行う。retry回数、SHA binding、CI状態、risk policy、merge可否は決定論的なworkflowが管理する。

### 4.5 失敗した研究も成果物にする

期待した改善が出なかった仮説も、条件、artifact、結果、棄却判断を再利用可能な形で残せば完了として扱える。成功した仮説だけをmergeする運用にはしない。

## 5. 初期Agent構成

### 5.1 Main Agent

責務はGoalへ向かって開発を前進させることである。

- Repository、Issue、PR、test、artifactから現在状態を確認する
- Goalとの差分から候補作業を生成する
- 次のTask Contractを選択・作成する
- 探索、計画、実装、検証、PR更新を行う
- Review Agentの`FAIL`を修正する
- merge後の状態を確認する

Main Agentは、次の作業が明記されていないことだけを理由に停止しない。

### 5.2 Review Agent

責務はMain Agentによる誤った前進を検出することである。

Main Agentの会話履歴を引き継がない新しいcontextで、repositoryと成果物を直接確認する。Review Agentはコードや文書を変更しない。

Reviewは2回行う。

1. Plan review: Task Contract、候補比較、Goalへの寄与、risk分類を確認する
2. Diff review: 実装、test、scope、回帰risk、受け入れ条件を確認する

出力は次のいずれかとする。

- `PASS`: blocking findingがない
- `FAIL`: repository内の修正で解消できるblocking findingがある
- `ESCALATE`: Human専用判断が必要、または安全な修正方針を選べない

各判定には、対象head SHA、blocking finding、non-blocking note、確認した検証を含める。

### 5.3 決定論的Controller

3人目のAgentは初期構成へ追加しない。代わりに、Main AgentとReview Agentが従う状態遷移をworkflowとして定義する。

```text
candidate
  -> task-ready
  -> plan-reviewed
  -> implementing
  -> local-verified
  -> PR
  -> diff-reviewed
  -> CI-passed
  -> policy-passed
  -> mergeable
  -> merged
  -> post-merge-verified
```

Agentは必要な証拠がない状態を飛ばして次へ進めない。

Controllerは概念上の手順だけでなく、Phase 3までにMain/Reviewから分離した実行主体として実装する。権限境界は次のとおりとする。

| 主体 | Repository read | Branch/PR write | Review判定 | Required check発行 | Merge | Ruleset/secret変更 |
|---|---:|---:|---:|---:|---:|---:|
| Main Agent | yes | local workspaceのみ。GitHub更新はControllerへ依頼 | no | no | no | no |
| Review Agent | yes、read-only | no | yes | Controller経由 | no | no |
| Controller | evidenceのみ | 限定writer経由でbranch/PR/stateを更新 | no | yes | yes | no |
| Human administrator | yes | yes | 監査 | 設定 | 例外時 | yes |

Main AgentとReview AgentへGitHub write credentialを渡さない。Main Agentはlocal workspaceでpatchとcommit候補を作り、Controllerが公開する限定operationを通じてwriterへbranch、PR、commentの更新を依頼する。Controllerは任意のshellや汎用GitHub tokenをMainへ公開しない。

同一repositoryでは、branchへのpushに必要な`Contents: write`がPR mergeにも利用できるため、「Mainは直接pushできるがmergeできない」というcredential設計にはしない。Controllerだけがwrite credentialを保持し、通常のbranch/PR更新とmergeを別のoperationとしてpolicy検証する。Merge operationはGitHub上のrequired checkとpolicyを再取得し、対象head SHAが一致する場合だけ実行する。

Shadow期間は現在の実行環境のcredential制約上この分離を完全には強制できないため、Controllerはmerge判定だけを出し、実際のmergeはHumanが行う。Phase 3は限定writerとcredential分離の実装完了を前提とする。

## 6. Task Contract

IssueのHuman承認を、AIが作成しReview Agentが検証するTask Contractへ置き換える。

Task Contractは最低限次を含む。

- Goal trace: `GOAL.md`のどの差分を縮めるか
- Current evidence: 現在何が確認済みか
- Question or hypothesis: 今回解決する問い
- Candidate tasks: 検討した候補
- Selection rationale: なぜこの作業を先に行うか
- Outcome: この作業で真にする状態
- Scope / out of scope
- Acceptance criteria
- Verification method
- Failure or rejection condition
- Risk class
- Time and cost budget
- Rollback method
- Assumptions and unresolved questions

CanonicalなTask Contractは、version管理された機械可読fileとしてbranchへ置く。想定配置は`automation/tasks/<task-id>.json`、schemaは`automation/schemas/task-contract.schema.json`とする。IssueやPR本文は人間向けprojectionであり、source of truthにはしない。

Controllerはcanonical JSONからSHA-256 digestを計算する。Plan review結果は少なくとも次を含む機械可読artifactとする。

- Contract ID
- Contract schema version
- Contract digest
- Reviewed contract commit SHA
- Reviewer run ID
- Verdict
- Findings
- Timestamp

Contractを変更するとdigestが変わり、以前のPlan reviewは自動的に無効になる。Diff reviewもhead SHAへ結び付け、head更新後の以前の`PASS`を使用できないようにする。

Workflowの状態は、Git commit上のTask Contractと、head SHAへ結び付いたGitHub Check Runをsource of truthとする。Label、Issue本文、PR本文、commentだけから状態を進めない。

### 6.1 AI-maintained portfolio

Human所有の長期Goalとは別に、AIが更新できる現在状態のportfolioを`automation/portfolio.json`へ置き、schemaで検査する。

Portfolioは次を含む。

- Current milestoneと検証可能な完了条件
- Goalとのgap
- Candidate task
- Dependency
- `candidate` / `active` / `blocked` / `rejected` / `done`の状態
- 優先順位と根拠
- 根拠となるcommit、Issue、PR、artifact
- 棄却理由と再検討条件

Main AgentはTask Contractを作る前にportfolioを更新し、Review Agentは候補漏れと優先順位を確認する。これにより、各実行が候補検討を最初からやり直したり、棄却済み案を理由なく再提案したりすることを防ぐ。

`active`と`done`の実効状態はJSONの手動更新だけで決めず、Task IDに対応するopen PRと`main`へのmerge記録からControllerが導出する。Merge成功時にControllerはtask completion eventを記録してactive leaseを解放し、次のportfolio reconciliationで永続fileを`done`へ更新する。したがって、merge直後にportfolio fileの表示が一時的に`active`でも次の作業開始を妨げず、同じTaskの二重開始も許さない。

現在の`GOAL.md`にはMark2全体の検証可能な完了条件が不足しているため、L4 loop開始前にHumanがGoal completion contractを承認する必要がある。AIはその範囲内でmilestoneとportfolioを更新できるが、Goal completion contract自体の変更は`R2`とする。

## 7. 作業選択規則

新しい作業を始める前に、次の順で既存作業を処理する。

1. Open PRのfailed CIまたはblocking review
2. Merge条件を満たしたopen PR
3. 進行中のTask Contract
4. Goal達成を妨げる最も近いgap

候補作業が複数ある場合は、次の順で選ぶ。

1. Goalとの差分を直接縮める
2. 後続作業のblockerを解消する
3. 情報利得が大きい
4. 客観的に検証できる
5. 小さくrollbackできる
6. 費用と所要時間が小さい

候補が存在する限り、Main Agentは1件を選ぶ。選択不能な場合も「未検討」とだけ報告せず、比較した候補、判断不能な一点、推奨案を含むdecision packetを作成する。

## 8. 曖昧さの処理

### 8.1 事実不足

Repository、Issue、PR、実行結果、一次資料から調査する。

### 8.2 技術的不確実性

Test、benchmark、小さなprototypeで比較する。比較可能な問題を好みや印象だけで決めない。

### 8.3 複数案があるが安全かつ可逆

Goalへの寄与と作業選択規則からMain Agentが推奨案を選び、仮定、代替案、rollback方法を記録して進む。

### 8.4 技術的証拠だけでは決められない

Humanへescalateする。質問には事実、試したこと、2〜3個の選択肢、推奨案、各案の影響、回答によって解禁される操作を含める。

## 9. Risk class案

### `R0`: 読み取り・分析

Repositoryや公開資料の調査、local test、既存artifactの分析。Main Agentが自律的に実行できる。

### `R1`: 可逆なrepository変更

Branch上のコード、test、文書、設定、CI変更。後述のmerge contractをすべて満たせばHuman承認なしでmergeできる。

初期のauto-merge対象候補は次とする。

- Test追加
- 内部refactor
- 文書間の整合修正
- 決定論的な検査tool
- 外部副作用のないbug fix

次のtrusted computing baseはrepository内の変更でも`R2`とし、通常のauto-merge対象にしない。

- GitHub Actions workflowとrequired check設定
- Controllerとmerge処理
- Risk classifier
- Task Contract、portfolio、review resultのschemaとvalidator
- Main/Review Agentの権限・指示・prompt
- Controller配下の限定writer operation
- Review check発行処理
- `AGENTS.md`とこのworkflowのnormativeな規則
- Testやgateを削除・緩和する変更

### `R2`: Human専用判断

初期案では次をHumanへ残す。

- `GOAL.md`の目的、成功条件、non-goalの実質的変更
- このrisk policyとAgent権限の変更
- Baseline、評価metric、成功閾値の実質的変更
- 結果確認後の実験条件変更など、controlled experimentの妥当性を損なう判断
- Secret、credential、IAM、network公開範囲、GitHub rulesetの変更
- 新しい有料resource、購入、契約、承認済み予算の超過
- 本番または外部systemの変更、一般公開、第三者への送信
- 回復手段を確認できない削除、履歴改変、data migration
- 法務、license、安全、倫理、privacyの判断
- 同じblocking findingが規定回数続いた場合
- 複数案が同程度で、選択が後続研究を大きく拘束する場合

将来は、Humanがregion、resource、上限費用、上限時間、停止条件をまとめて承認するbudget envelopeを定義し、その範囲内の反復実験を`R1`相当へ移すことを検討する。

## 10. Review contract

Review AgentへMain Agentの会話履歴や結論は渡さない。一方、責務を果たすために次のread-only accessを許可する。

- `GOAL.md`
- このworkflowとrisk policy
- Task Contract
- Base SHAとhead SHA
- Diff
- Test、CI、benchmarkの結果
- 関連artifact
- Repository全体
- Open Issue/PRとそのreview・CI状態
- Current portfolio

Controllerは取得時点、base/head SHA、Issue/PR一覧、artifact inventoryを含むstate snapshotを作り、review resultとともに保存する。Review Agentはsnapshotに限定されず、read-only toolで一次状態を再確認できる。

Review Agentは最低限次を確認する。

- Goalに寄与する作業か
- より優先すべき明白なblockerを無視していないか
- 受け入れ条件が検証可能か
- Scope外の変更がないか
- 仮定と未検証事項が明示されているか
- 必要なtestがあるか
- Risk classが過小評価されていないか
- Controlled experimentの比較条件を壊していないか
- Rollback可能か

Review Agentの`PASS`はCIの代用ではなく、CIもReview Agentの代用ではない。

## 11. Deterministic gate

Human review requirementを外す前に、最低限次を自動検査へ移す。

- Clean checkout上のunit test
- `check-config`
- Offline/mockの独立2 runと比較
- Python compileまたは静的検査
- Diff whitespace check
- Task Contractの必須項目とGoal trace
- Task Contract schema、digest、Plan review対象digestの一致
- Portfolio schemaとactive taskの一意性
- Review対象SHAと最新head SHAの一致
- Base branch最新化とconflictなし
- Unresolved blocking threadなし
- 変更対象に応じたrisk classification
- Artifactとmanifest schema
- 失敗時artifactの保持
- Controllerがrequired checkをGitHubから再取得したこと
- Main/Reviewにmerge権限がないこと

Dependency lock、secret scan、依存脆弱性検査、post-merge smoke、rollback自動化は、変更範囲とriskに応じて段階的に追加する。

Merge条件は論理的に次とする。

```text
Plan review PASS
AND Diff review PASS for current head SHA
AND Required CI PASS for current head SHA
AND Policy PASS
AND Mergeable with current base
```

## 12. GitHub上のReview Agent表現

Subagentを別contextで実行しても、Main Agentと同じGitHub App credentialを使う場合、GitHub上では独立したreviewer identityにならない。

初期案には次の選択肢がある。

### 案A: Review結果をPR commentとして記録

- 実装が簡単
- 現在のCodex実行環境で開始しやすい
- 独立性はworkflow規約に依存し、GitHub rulesetでは強制できない

### 案B: Review結果をrequired status checkとして発行

- Head SHAとの一致をGitHub rulesetで強制できる
- Review実行service、GitHub App権限、status check発行処理が必要

### 案C: Review専用GitHub identityを用意

- GitHub上のreviewerを分離できる
- Credential、権限、運用管理が増える

案Aはshadow運用だけに限定する。Phase 3のauto-mergeを開始する前に案Bを実装し、Plan review、Diff review、policyをhead SHAとcontract digestへ結び付いたrequired checkにする。案Aだけでauto-mergeすることは認めない。

## 13. Retryと停止条件

Reviewの無限loopを防ぐ。

- `FAIL`後はMain Agentが修正し、新しいcontextのReview Agentが最新headをreviewする
- 同じ原因のblocking findingが2回続いた場合は、修正案を再計画する
- 同じ原因が3回続き、追加の証拠や別案がなければHumanへescalateする

通常loopを停止できるのは次の場合だけとする。

- `R2`判断なしでは安全に進められる作業がない
- 認証、権限、外部service障害に対する安全な代替経路がない
- Retry上限へ到達した
- 事前に定めた時間、token、費用budgetへ到達した
- Goalの完了条件を証拠付きで満たした

停止は完了を意味しない。Blockerと解除条件を残す。

## 14. 開発loop案

```text
GOAL / main / GitHub / artifacts
              ↓
         Main Agent
              ↓
   Candidate tasks / Task Contract
              ↓
     Review Agent: Plan review
       FAIL ↙           ↘ PASS
      修正               実装
                         ↓
                    Local checks
                         ↓
                         PR
                         ↓
     Review Agent: Diff review
       FAIL ↙           ↘ PASS
      修正               CI / policy
       ↑                    ↓
       └──────────────── FAIL
                            ↓ PASS
                          Merge
                            ↓
                  Post-merge verification
                            ↓
                       Repo state更新
                            ↺
```

同時に扱うagent作成のopen PRは原則1件とする。1回の定期実行でmergeするPRも最大1件とし、blast radiusを制限する。

Issueは次の場合に使用する。

- 複数PRにまたがる作業
- 長期間残す研究課題
- Human decisionが必要な事項
- 外部resourceや他systemとの調整

1 PRで完結する通常作業に、着手承認用Issueを必須としない。

## 15. 段階移行案

### Phase 1: 制御面の実装

- Goal completion contractとportfolio schema
- Task Contract schema、digest、validator
- Baseline CI
- Main/Reviewの入出力とreview result schema
- Risk policyとtrusted computing base
- SHA binding、retry、escalation条件
- Review/Policy required check
- Controllerとauthority分離
- Shadow telemetry

### Phase 2: Shadow mode

最低5件の対象PRで、AIがTask選択、Plan review、Diff review、merge判定まで行う。Humanは各工程の承認者ではなく、最終判定の監査者とする。Merge操作はHumanが行う。

次を記録する。

- AIが見逃したblocking finding
- 不必要なescalation
- 誤った作業選択
- 同じ指摘の反復回数
- Humanが修正したrisk分類
- Merge後のfailure

Phase 3への卒業条件は次のすべてとする。

- 対象となる新規PRが5件以上。PR #34はmechanicsのdry runには使うが、既にHuman review済みのためこの5件には数えない
- Human監査でblocking findingの見逃し0件
- `R2`を`R1`と判定した事例0件
- Contract digestまたはhead SHAの不一致0件
- 必須状態遷移の証拠欠落0件
- Merge判定後またはmerge後のrequired check failure 0件
- 同一原因のReview FAILが3回に達した事例0件

Shadow卒業はrisk policyの変更に当たるため、上記証拠をまとめた1回のHuman判断を必要とする。個々のPR承認へ戻すものではない。

### Phase 3: 限定auto-merge

Shadow卒業条件をすべて満たし、Review/Policy checkがGitHub rulesetで強制され、Controllerのcredential分離が実行環境のsecret/IAM境界で強制された場合に限り、`R1`の一部について自律mergeを許可する。

次は対象外から開始する。

- `GOAL.md`
- Agent指示とrisk policy
- Baselineと評価契約
- Dependencyとsupply chain
- IAM、費用、network、外部resource
- GitHub rulesetとworkflow権限
- Controller、validator、risk classifier、review prompt

### Phase 4: 研究loopへの拡張

固定されたbaseline、metric、budget、resourceの範囲内で、仮説選択、実装、比較実験、結果記録、採用・修正・棄却まで自律化する。

必要であればbudget envelopeを導入し、個別の有料実行承認を減らす。

## 16. 現在のPR #34への適用案

PR #34をworkflow mechanicsのdry run対象とする。既にHumanの内容reviewを受けているため、Review Agentの独立精度を測るshadow sampleには数えない。

1. `main`との差分を整理し、最新baseへ更新する
2. PR #34のTask Contractを復元する
3. 新しいCIをclean checkoutで実行する
4. Review AgentがPlanと最新diffを独立reviewする
5. AIがmerge可否を判定する
6. Shadow期間中のため、最終mergeだけHumanが行う
7. Merge後に#33のcloseと、#30に残る実機2 runの作業を確認する

これにより、抽象的なworkflowだけでなく、実在する停滞中PRで状態遷移を検証できる。

## 17. Skillの位置づけ

初期段階ではL4 loop全体をSkillにしない。

- `AGENTS.md`: 常に適用するrepository固有の不変条件
- Development workflow: Risk、状態遷移、merge条件
- 定期実行prompt: Loopを開始する短い指示
- CI: 決定論的な検証
- Skill: 繰り返し利用する専門的な手順

実運用で繰り返し必要になった場合、次のSkillを個別に検討する。

- 次のTask Contractを生成・比較するSkill
- Research planをreviewするSkill
- PRのGoal整合性と研究妥当性をreviewするSkill
- Experiment artifactを検査するSkill

Skillはworkflowを教える層であり、永続状態、権限、merge gateを管理するControllerの代わりにはしない。

## 18. 今回レビューしてほしい点

### Decision 1: Shadow期間

推奨: 上記の客観条件を満たす新規5 PR。

代替: 対象PRを10件に増やす、または期間条件も追加する。Required checkと権限分離を省略した即時auto-mergeは選択肢に含めない。

### Decision 2: Baseline・評価metricの扱い

推奨: 初期は`R2`とし、Human判断を必要とする。

代替: 事前に選定rubricと変更条件を固定し、条件内の変更を`R1`へ移す。

### Decision 3: Review結果のGitHub上の表現

提案上の必須条件: Shadow期間はPR commentを許可するが、auto-merge開始前にrequired status check化する。

代替: Shadow開始時点からreview service/checkを実装する、またはReview専用identityも併用する。

### Decision 4: Retry上限

推奨: 同じ原因が2回続いたら再計画、3回でescalate。

代替: 2回でescalateし、tokenと手戻りを抑える。

### Decision 5: 有料resource

推奨: 初期は個別Human判断を維持し、運用安定後にbudget envelopeを導入する。

代替: 最初から月額、1 run、region、instance type、停止条件を固定したenvelopeを作る。

## 19. 実装Issue分割案

方針承認後は、次の依存順で実装Issueへ分割する。各Issueは前段の成果物を入力とする。

### I1. Goal completion contractとportfolio

成果物:

- 検証可能なGoal completion contract
- `automation/portfolio.json`
- Portfolio schemaとvalidator

受け入れ条件:

- Current milestone、candidate、dependency、evidence、状態を機械的に検査できる
- Active taskが最大1件である
- Goal completion contractの変更が`R2`として検出される

### I2. Task Contractとpolicy schema

依存: I1

成果物:

- Task Contract JSON schema
- Risk policy
- Trusted computing baseのpath rule
- Contract digestとvalidator

受け入れ条件:

- 必須項目不足、未知のrisk class、portfolioにないtaskを拒否する
- Contract変更でdigestが変わり、以前のPlan PASSを再利用できない
- Trusted computing base変更を`R2`として分類する

### I3. Baseline CI

依存: I1

成果物:

- Clean checkout上のtest、`check-config`、mock比較、compile、diff check
- Artifact/manifest schema check

受け入れ条件:

- PRの最新head SHAに対してrequired checkが実行される
- Test削除やcheck失敗時にmerge可能状態にならない
- Failure artifactを取得できる

### I4. Review resultとrequired check

依存: I2、I3

成果物:

- Plan/Diff review result schema
- Read-only state snapshot
- Review実行とCheck Run発行処理

受け入れ条件:

- Plan resultがContract digestへ結び付く
- Diff resultがhead SHAへ結び付く
- Contract/head更新で以前のPASSが無効になる
- Review Agentにbranch writeとmerge権限がない

### I5. Controllerと権限分離

依存: I3、I4

成果物:

- State machine
- Merge前のrequired check再取得
- Authority matrixに沿ったGitHub Appまたはtoken権限
- Mainのpatch/commit候補を受け取り、許可されたbranch/PR操作だけを行う限定writer
- Retry、lease、idempotency、post-merge verification

受け入れ条件:

- Main/ReviewへGitHub write credentialが公開されず、GitHub mutationは限定writer経由でしか実行できない
- Mainが任意のGitHub API、`git push`、merge APIを直接実行できない
- Controllerは最新headの全gate成功時だけmergeできる
- Duplicate invocationで二重mergeや二重PRを起こさない
- Post-merge failureを記録し、自動停止またはrollback判断へ遷移する

### I6. Shadow telemetryと卒業監査

依存: I1〜I5

成果物:

- 5件以上の対象PRのtransition log
- 見逃し、誤分類、SHA/digest不一致、evidence欠落の集計
- Phase 3移行decision packet

受け入れ条件:

- Phase 2の全卒業条件を機械集計できる
- 未達の場合はauto-mergeを有効化できない
- Humanが1回のpolicy判断でPhase 3移行可否を決められる

## 20. L4移行の合格条件案

- AgentがGoalと証拠からTask Contractを生成できる
- AI-maintained portfolioが候補、依存関係、棄却理由、現在のmilestoneを保持する
- 候補がある限り1件を選び、選べない場合はdecision packetを作る
- PlanとDiffがMain Agentとは別contextでreviewされる
- Task Contract digestとPlan reviewが一致する
- Review対象SHAとmerge対象SHAが一致する
- Required CIとpolicy checkなしではmergeできない
- Main/Reviewにはmerge権限がなく、Controllerだけがmergeできる
- Main/ReviewにGitHub write credentialが公開されず、限定writerとmerge operationが分離されている
- Retry上限とescalation条件がある
- 費用、権限、破壊的操作がpolicyで拒否される
- Shadow期間中に重大な誤merge判定がない
- Merge後failureを検出し、停止、rollbackまたはescalationできる
- 失敗・棄却された研究結果もartifactとして残る

## 21. 参考資料

- [OpenAI: Using Goals in Codex](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)
- [OpenAI: Multi-agent](https://developers.openai.com/api/docs/guides/responses-multi-agent)
- [OpenAI: Skills](https://developers.openai.com/plugins/concepts/skills)
