# L4 autonomous development workflow proposal

Status: Draft for review

Tracking issue: [#37](https://github.com/Bite-8/AI/issues/37)

## 1. この文書の目的

この文書は、Humanを通常のIssue作成、実装承認、PR review、修正確認、mergeから外し、AIが`GOAL.md`へ向かう開発loopを継続するための初期設計案である。

ここでいうL4は製品一般の自律化levelではなく、このrepositoryにおけるAI駆動開発の自律化levelを表す便宜上の呼称とする。

このPRでは方針を提案するだけで、Human gateの解除、GitHub ruleset変更、自動merge、有料resourceの操作は行わない。

具体的にどのファイルをどう変更し、1回の定期実行がどう動くかは15章にまとめる。Shadow modeとportfolioは、15章の最小構成が実Taskで動いた後に具体化する。

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

### 3.1 前提条件: CODEOWNERSとruleset

`.github/CODEOWNERS`と`main-protect` ruleset（`require_code_owner_review: true`）により、次のpathを変更するPRはcode owner（`@bara8383`）のreviewが必須である。

- `/GOAL.md`
- `/.github/`（workflow、CODEOWNERS、PR templateを含む）
- `/.claude/`、`/.codex/`（Agent設定・prompt）
- `**/CLAUDE.md`、`**/AGENTS.md`

つまり、GitHub周りの設定とAI周りの設定はcode owner reviewを必須とする。この前提を設計へ次のように反映する。

1. GitHub設定とAI設定の変更は、L4移行後も常に`R2`であり、自律mergeの対象にしない。Risk classifierはこの一覧を別に持たず、`.github/CODEOWNERS`を直接読んで判定する（15.3）。
2. L4 workflow本体（CI、定期実行prompt、Review Agent定義、`AGENTS.md`）はほぼすべてこのpathに入るため、workflowの実装PRはすべてcode owner reviewを経る。
3. Controllerやvalidatorを置く`automation/`は現在のCODEOWNERSでは保護されない。Gateを緩める変更が`R1`として通らないよう、`/automation/l4/`と`/automation/policy.json`をCODEOWNERSへ追加する（15.2）。
4. 現在のrulesetは`required_approving_review_count: 0`であり、CODEOWNERS対象外のpath（`mark2/`、`tests/`、`docs/`等）だけを変えるPRは、GitHub上はreviewなしでmergeできる。現在のHuman gateは定期実行promptの規約で成立しており、GitHub側では強制されていない。L4で自律merge対象にするのはこの範囲なので、ここはrequired status checkで決定論的に保護する必要がある。

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

CanonicalなTask Contractは、version管理された機械可読fileとしてbranchへ置く。想定配置は`automation/tasks/<task-id>.json`とする。新しい依存を増やさないため、schemaはJSON Schema fileではなく`automation/l4/contract.py`のvalidatorとして実装する（15.4）。IssueやPR本文は人間向けprojectionであり、source of truthにはしない。

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

Workflowの状態は、Git commit上のTask Contractと、head SHAへ結び付いたGitHub Check Runをsource of truthとする。Label、Issue本文、PR本文、commentだけから状態を進めない。ただしCheck Run発行を実装するまでのPhase 1では、review結果だけはmarker付きPR commentに記録し、`gate`がcontract digestとhead SHAの一致を検査したものに限って使う（15.5）。

### 6.1 AI-maintained portfolio

> 導入時期: 15章のPhase 1構成が実Taskで動いた後に、具体的なfile形式と更新手順を別PRで提案する。以下は方向性だけを示す。

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

CODEOWNERS対象path（3.1）を変更するPRは常に`R2`とする。加えて、次のtrusted computing baseはrepository内の変更でも`R2`とし、通常のauto-merge対象にしない。15.2のCODEOWNERS追加により、これらの多くはcode owner reviewで保護される。

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

## 15. 具体化: どのファイルをどう変更し、どう動かすか

この節は、Shadow modeやportfolioより前に実装する最小構成（Phase 1）を、変更するファイル、コマンド、1回の定期実行の手順まで具体化する。

Phase 1ではHuman gate（作業開始の承認、PRのApprove、merge）は現状どおり維持する。変えるのは、Humanが承認する対象をIssue本文から機械検査可能なTask Contractへ移すことと、AIの判断を決定論的なtoolとCIで検査できるようにすることである。Shadow modeは、この仕組みが実際のTaskで動いてから、同じartifactに対するAI判定とHuman判定を比較する形で設計する。

### 15.1 Phase 1完了時点でできること

- `python3 -m automation.l4 status`が、GitHubとrepositoryの状態から次に行う作業を1つ返す。現在の定期実行promptに文章で書かれている「作業の選択順序」を、LLMの解釈ではなくコードで決める
- Task ContractをJSON fileとして作成し、`validate`と`digest`で機械的に検査できる
- PRごとにCIが自動実行され、test、`check-config`、mock 2 run比較、Task Contract検査、risk分類の結果がhead SHAに結び付いたcheckとして残る
- Review Agentが別contextでPlanとDiffをreviewし、決まった形式でPRへ記録する
- `python3 -m automation.l4 gate --pr <N>`がmerge条件を評価して判定を出す。Mergeは引き続きHumanが行う

### 15.2 変更・追加するファイル

| Path | 種別 | 内容 | Code owner review |
|---|---|---|---|
| `.github/CODEOWNERS` | 変更 | `/automation/l4/`と`/automation/policy.json`を追加 | 必須 |
| `.github/workflows/ci.yml` | 新規 | PR時のdeterministic check（15.6） | 必須 |
| `.github/pull_request_template.md` | 新規 | Task ID、Goal trace、検証結果、未検証事項の欄 | 必須 |
| `automation/__init__.py` | 新規 | package化のみ | 不要 |
| `automation/l4/__main__.py` | 新規 | CLI entry。`status` / `validate` / `digest` / `classify` / `gate` | 必須（CODEOWNERS変更後） |
| `automation/l4/contract.py` | 新規 | Task Contract validatorとdigest。canonical JSONは`mark2.config.sha256_json`と同じ規則を使う | 必須 |
| `automation/l4/policy.py` | 新規 | 変更pathからrisk classを判定する。`.github/CODEOWNERS`と`automation/policy.json`を読む | 必須 |
| `automation/l4/state.py` | 新規 | `gh`経由でopen PR、review、comment、check、head SHAを取得し、次の作業を決める | 必須 |
| `automation/l4/gate.py` | 新規 | Merge条件の評価 | 必須 |
| `automation/policy.json` | 新規 | R2 path rule、WIP上限、retry上限 | 必須 |
| `automation/tasks/<task-id>.json` | 作業ごとに新規 | Task Contract本体。Main Agentが作成する | 不要（validatorとReview Agentで検査） |
| `tests/test_l4.py` | 新規 | validator、digest、classify、status判定のunit test。`gh`の出力はfixtureで与える | 不要（test削除は`R2`） |
| `.codex/prompts/l4-loop.md` | 新規 | 定期実行prompt。現在の自立開発promptを置き換える | 必須 |
| `.codex/prompts/l4-review.md` | 新規 | Review Agent prompt。Plan/Diff共通で出力形式を固定する | 必須 |
| `.claude/agents/l4-reviewer.md` | 新規 | Claude Codeで実行する場合のReview Agent定義。書き込み系toolを持たせない | 必須 |
| `AGENTS.md` | 変更 | Task Contract必須、状態遷移、禁止操作などの不変条件を短く追記 | 必須 |
| `GOAL.md` | 変更 | Mark2の検証可能な完了条件（Goal completion contract） | 必須 |

`automation/l4`はPython標準libraryだけで実装し、新しい依存を追加しない。`mark2`の`check-config`とmock runもML依存なしで動くため、CIは`requirements.txt`をinstallせずに実行できる。

`.codex/`と`.claude/`の両方を用意するかはDecision 6で決める。どちらの場合もnormativeな規則は`AGENTS.md`に置き、promptとAgent定義は手順と出力形式だけを持つ。

### 15.3 Risk分類の実装

`python3 -m automation.l4 classify --base origin/main --head HEAD`は次の順で判定する。

1. `git diff --name-status <base>...<head>`で変更pathを取得する
2. `.github/CODEOWNERS`のいずれかのpatternに一致するpathがあれば`R2`
3. `automation/policy.json`の`r2_paths`に一致するpathがあれば`R2`
4. `r2_if_deleted`に一致するfileの削除があれば`R2`
5. それ以外は`R1`

```json
{
  "schema_version": 1,
  "codeowners_file": ".github/CODEOWNERS",
  "r2_paths": ["mark2/configs/**", "mark2/requirements.txt"],
  "r2_if_deleted": ["tests/**"],
  "max_open_agent_prs": 1,
  "max_merges_per_run": 1,
  "retry": {"replan_after": 2, "escalate_after": 3}
}
```

`mark2/configs/**`はbaselineと評価契約を含むため、Decision 2の推奨に従い`R2`とする。

出力例:

```json
{"risk_class": "R2", "reasons": [{"path": ".github/workflows/ci.yml", "rule": "CODEOWNERS: /.github/"}]}
```

Task Contractに宣言された`risk_class`より判定結果が高い場合、`validate`は失敗する。

### 15.4 Task Contractの具体例

`automation/tasks/T-0001.json`の例を示す。内容は形式を示すためのもので、この作業を実施することを提案するものではない。

```json
{
  "schema_version": 1,
  "id": "T-0001",
  "title": "mock backendの独立2 run一致をunit testで固定する",
  "goal_trace": "GOAL.md Mark2: baselineの無変更再現 (#30)",
  "current_evidence": [
    "python3 -m unittest discover -s tests: 8 tests OK (main d8d9cd9)",
    "mock 2 runの比較手順はdocs/mark2/README.mdにだけあり、testでは検査していない"
  ],
  "question": "run IDだけが異なる2回のmock runでcompareがreproducibleを返し続けるか",
  "candidates": [
    {"id": "A", "summary": "unit testでmock 2 runとcompareを実行する"},
    {"id": "B", "summary": "CI stepだけで比較する", "rejected_reason": ".github変更でR2になり、local testで再現できない"}
  ],
  "selection_rationale": "R1で完結し、#30の再現性検査の前提を固定できる",
  "outcome": "mock 2 runの一致が壊れたらtestが失敗する",
  "scope": ["tests/test_mark2.py"],
  "out_of_scope": ["mark2/configs/**", "実機GPU run"],
  "acceptance_criteria": ["追加testがmainで成功する", "予測を1件変えるとtestが失敗する"],
  "verification": ["python3 -m unittest discover -s tests -v"],
  "rejection_condition": "mock runが非決定的で、test化にmark2本体の変更が必要な場合",
  "risk_class": "R1",
  "budget": {"max_minutes": 60, "paid_resources": false},
  "rollback": "PRをrevertする",
  "assumptions": []
}
```

`validate`が決定論的に検査する項目:

- 必須fieldの有無と型、`id`とfile名の一致
- `risk_class`が`classify`の結果以上であること
- 変更されたfileがすべて`scope`のpatternに含まれ、`out_of_scope`に含まれないこと。Scope外の変更はReview Agentに頼らずCIで検出する
- `budget.paid_resources`が`true`の場合は`R2`であること
- Contract file自身（`automation/tasks/<id>.json`）はscope検査の対象外とする

`digest`は`sha256:<hex>`を出力する。Plan review結果はこの値を記録し、Contractを1文字でも変えると以前のPlan reviewは無効になる。

### 15.5 Review結果の記録形式

Phase 1では案AとしてPR commentに記録する。Review結果をbranchへcommitすると、head SHAが変わってDiff reviewが無効になるため、repository fileにはしない。

```text
<!-- l4-review:v1 -->
{"kind": "diff", "task_id": "T-0001", "contract_digest": "sha256:…", "head_sha": "<40桁>", "verdict": "PASS", "blocking": [], "notes": [], "checked": ["unittest", "scope"], "reviewer_run": "<実行ID>"}
```

`gate`はmarker付きの最新commentを種類ごとに読み、`contract_digest`と`head_sha`が現在値と一致する場合だけ有効とする。Main Agentと同じGitHub identityで投稿されるため、Reviewの独立性はGitHub上では強制されない。Phase 1ではHumanがmergeするためこの制約を許容し、auto-merge前に案Bへ移行する（12章）。

### 15.6 CI

```yaml
name: ci
on:
  pull_request:
permissions:
  contents: read
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m unittest discover -s tests -v
      - run: python -m compileall -q mark2 automation tests
      - run: python -m mark2.run check-config
      - name: mock 2 run comparison
        run: |
          python -m mark2.run run --backend mock --run-id ci-1 --output-root "$RUNNER_TEMP/m2"
          python -m mark2.run run --backend mock --run-id ci-2 --output-root "$RUNNER_TEMP/m2"
          python -m mark2.run compare "$RUNNER_TEMP/m2/ci-1" "$RUNNER_TEMP/m2/ci-2"
      - run: git diff --check "origin/${{ github.base_ref }}...HEAD"
      - run: python -m automation.l4 validate --base "origin/${{ github.base_ref }}" --head HEAD
```

- `pull_request` triggerと`contents: read`だけを使い、secretとwrite権限をCIへ渡さない
- `validate`は、変更に`automation/tasks/*.json`が含まれないPR（Human作成のPRなど）では`task: none`としてscopeとrisk検査だけを行う
- `checks`をrequired status checkにするのはruleset変更であり、HumanがGitHubの設定画面で行う（15.8）

### 15.7 1回の定期実行の流れ

定期実行promptは`.codex/prompts/l4-loop.md`の短い指示だけにし、作業の選択はtoolに任せる。

1. `AGENTS.md`を読み、`git fetch`と作業ツリーの確認を行う。Dirtyな場合は`BLOCKED`で終了する
2. `python3 -m automation.l4 status`を実行する
3. 返された`next_action`だけを1件実行し、終了状態を出力して終了する

`status`の出力例:

```json
{"next_action": "run_plan_review", "pr": 41, "task": "T-0001", "contract_digest": "sha256:…", "reason": "draft PR has no plan review for current digest"}
```

`next_action`は上から順に評価し、最初に該当したものを返す。

| `next_action` | 条件 | Main Agentの動作 | 終了状態 |
|---|---|---|---|
| `blocked` | 認証失敗、未同期、conflict | 理由を出力 | `BLOCKED` |
| `address_feedback` | Agent PRにfailed CI、changes requested、未回答のHuman comment、Review `FAIL`がある | 同じbranchで修正してpush | `UPDATED_PR` |
| `run_plan_review` | 現在のcontract digestに対するPlan reviewがない | Review Agentを起動し、結果をcommentする | `UPDATED_PR` |
| `await_plan_approval` | Plan `PASS`で、Humanの`/approve-plan`がない | 何もしない | `AWAITING_PLAN_APPROVAL` |
| `implement` | `/approve-plan`済みで、実装commitがない | Contractの範囲で実装してpushし、draftを解除する | `UPDATED_PR` |
| `run_diff_review` | 現在のhead SHAに対するDiff reviewがなく、CIが完了している | Review Agentを起動し、結果をcommentする | `UPDATED_PR` |
| `report_gate` | Diff `PASS`でgate判定が未投稿 | `gate --pr <N>`の結果をcommentする | `AWAITING_PR_REVIEW` |
| `await_human` | Gate判定済みでHumanのApproveまたはmerge待ち | 何もしない | `AWAITING_PR_REVIEW` / `AWAITING_HUMAN_MERGE` |
| `propose_task` | 上記のいずれにも該当しない | 候補を比較してTask Contractを書き、そのfileだけを含むdraft PRを作る | `CREATED_PR` |

この表により、現在のIssue中心の流れは次のように置き換わる。

| 現在 | Phase 1 |
|---|---|
| Agentが提案Issueを作る | Agentが`automation/tasks/<id>.json`だけを含むdraft PRを作る |
| Humanが`/approve-issue`する | Review AgentのPlan `PASS`後、Humanが同じdraft PRで`/approve-plan`する |
| Agentが別branchで実装し、PRを作る | 同じPRへ実装commitを追加する。Contractを変更すると承認とPlan reviewは無効になる |
| HumanがApproveしてmergeする | CI、Diff review、`gate`の判定が揃った後、HumanがApproveしてmergeする |

Humanの承認対象がTask Contractとgate判定になるため、Phase 2ではHumanの判断を記録したまま、同じartifactに対するAI判定との一致を測定できる。

Review Agentの起動方法:

- Main Agentとは別process・別contextで起動し、入力はPR番号、review種別、contract digest、head SHAだけにする
- Review Agentは`gh pr view`、`gh pr diff`、`git show`、test実行などのread操作で一次情報を確認する
- Review Agentの出力はmarker付きJSONだけとし、Main Agentがそのままcommentする。Main Agentが内容を書き換えたかは、`reviewer_run`とReview Agentの実行logで監査する

`gate --pr 41`の出力例:

```json
{"pr": 41, "head_sha": "<40桁>", "plan_review": "PASS (digest match)", "diff_review": "PASS (head match)", "ci": "success", "risk_class": "R1", "mergeable": "CLEAN", "verdict": "MERGEABLE"}
```

`verdict`は`MERGEABLE`、`NOT_READY`（不足している条件を列挙）、`REQUIRES_CODE_OWNER`（`R2`）のいずれかとする。

### 15.8 実装の順序

各PRは前のPRがmergeされてから作る。15.2のとおり、どのPRもCODEOWNERS対象pathを含むためcode owner reviewを経る。

1. **PR-1**: `.github/CODEOWNERS`へ`/automation/l4/`と`/automation/policy.json`を追加し、`automation/policy.json`を置く
2. **PR-2**: `automation/l4`の`contract` / `digest` / `classify` / `validate`と`tests/test_l4.py`
3. **PR-3**: `.github/workflows/ci.yml`とPR template。Merge後、Humanが`checks`をrequired status checkへ追加する
4. **PR-4**: `automation/l4`の`status`と`gate`、fixtureを使ったtest
5. **PR-5**: `.codex/prompts/l4-loop.md`、`l4-review.md`（または`.claude/agents/l4-reviewer.md`）、`AGENTS.md`への追記。Merge後、Humanが定期実行の参照先をこのpromptへ切り替える
6. **PR-6**: `GOAL.md`へGoal completion contractを追加する。内容はHumanが決め、AIは下書きだけを作る

PR-5のmerge後、最低1件の実Taskで15.7の流れを最後まで通す。そこで得たcommentやcheckの記録をもとに、portfolio（6.1）とShadow mode（Phase 2）の具体的な設計を別PRで提案する。

### 15.9 Humanが行う操作

| タイミング | 操作 |
|---|---|
| PR-1〜PR-6 | Code owner review |
| PR-3のmerge後 | `main-protect` rulesetへ`checks`をrequired status checkとして追加 |
| PR-5のmerge後 | 定期実行の参照promptを`.codex/prompts/l4-loop.md`へ切り替え |
| PR-6 | Goal completion contractの内容決定 |
| 各Task | draft PRでの`/approve-plan`、最終Approveとmerge |

## 16. 段階移行案

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

> 具体化の時期: 15.8の実装順序を終え、最低1件の実Taskで15.7の流れを通した後に、記録方法と集計手順を具体化する。以下は卒業条件の方向性を示す。

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

## 17. 現在のPR #34への適用案

PR #34をworkflow mechanicsのdry run対象とする。既にHumanの内容reviewを受けているため、Review Agentの独立精度を測るshadow sampleには数えない。

1. `main`との差分を整理し、最新baseへ更新する
2. PR #34のTask Contractを復元する
3. 新しいCIをclean checkoutで実行する
4. Review AgentがPlanと最新diffを独立reviewする
5. AIがmerge可否を判定する
6. Shadow期間中のため、最終mergeだけHumanが行う
7. Merge後に#33のcloseと、#30に残る実機2 runの作業を確認する

これにより、抽象的なworkflowだけでなく、実在する停滞中PRで状態遷移を検証できる。

## 18. Skillの位置づけ

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

## 19. 今回レビューしてほしい点

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

### Decision 6: Agent実行環境の設定置き場

推奨: 現在の定期実行環境に合わせて`.codex/`だけで開始し、`.claude/agents/l4-reviewer.md`は必要になった時点で追加する。

代替: 最初から`.codex/`と`.claude/`の両方を用意する。二重管理を避けるため、どちらの場合もnormativeな規則は`AGENTS.md`だけに置く。

### Decision 7: `automation/`のCODEOWNERS追加

推奨: `/automation/l4/`と`/automation/policy.json`をCODEOWNERSへ追加し、gate本体をcode owner review必須にする。`automation/tasks/`はAIが書けるように対象外とする。

代替: Controllerとpolicyを`.github/`配下へ置き、既存のCODEOWNERSで保護する。CODEOWNERSの変更は不要になるが、Python packageとしての配置が不自然になる。

## 20. 実装Issue分割案

方針承認後は、次の依存順で実装Issueへ分割する。各Issueは前段の成果物を入力とする。

15.8のPRとの対応は次のとおり。I1のportfolio部分とI6は、Phase 1が実Taskで動いた後に具体化する。

| Issue | 15.8のPR |
|---|---|
| I1 | PR-6（Goal completion contract）。Portfolioは後続 |
| I2 | PR-1、PR-2 |
| I3 | PR-3 |
| I4 | PR-5（Phase 1はPR comment。Check Run発行は後続） |
| I5 | PR-4（`status`と`gate`）。限定writerとcredential分離は後続 |
| I6 | 後続 |

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

## 21. L4移行の合格条件案

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

## 22. 参考資料

- [OpenAI: Using Goals in Codex](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)
- [OpenAI: Multi-agent](https://developers.openai.com/api/docs/guides/responses-multi-agent)
- [OpenAI: Skills](https://developers.openai.com/plugins/concepts/skills)
