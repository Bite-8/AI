# L4 autonomous development workflow proposal

Status: Draft for review

Tracking issue: [#37](https://github.com/Bite-8/AI/issues/37)

## 1. この文書の目的

この文書は、Humanを通常のIssue作成、実装承認、PR review、修正確認、mergeから外し、AIが`GOAL.md`へ向かう開発loopを継続するための**開発フロー案**である。

ここでいうL4は製品一般の自律化levelではなく、このrepositoryにおけるAI駆動開発の自律化levelを表す便宜上の呼称とする。

このPRで行うのは案の合意までである。Human gateの解除、GitHub ruleset変更、自動merge、有料resourceの操作は行わない。

この文書では混同を避けるため、記述を次の3種類に分ける。

- **現状**: 現在すでに存在する仕組み
- **提案**: この文書で新しく導入を提案する仕組み
- **将来候補**: 初期運用の結果を見て別途判断する仕組み

## 2. 背景と問題

### 現状

現在の定期実行promptは、次の2つのHuman gateを必須にしている。

1. Issueの実装承認
2. PRのApprove reviewとmerge

この方式は誤った変更を止めやすい一方、すべての通常作業でHumanの応答を必要とするため、Humanが開発速度の上限になる。

過去にHuman gateを外して`GOAL.md`だけを渡した運用では、Goalから次の作業を一意に決められず、Agentが「まだ検討されていないため実装できない」と判断して停止した。

不足していたのは新しい管理systemではなく、Humanが暗黙に行っていた次の判断をAgentの手順へ移すことである。

- 現在地点とGoalの差分を確認する
- 候補作業を比較し、次の1件を選ぶ
- Issueへ目的、範囲、完了条件を書く
- 実装とreviewを分離する
- 通常変更とHuman判断が必要な変更を分ける
- Issue、PR、CIの状態から次の行動を決める

### 提案の中心

既存のIssueとPRをそのまま作業記録と状態管理に使う。Task Contract用JSON、portfolio、独自Controller、独自policy fileは初期構成へ追加しない。

## 3. 現在のrepository状態と制約

2026-09-25の調査時点では次の状態である。

- `docs/memo/prompt.md`に定期実行の作業選択順序がある
- Issueに背景、目的、scope、完了条件、検証方法を書く運用がある
- PRに変更内容と検証結果を書き、Humanがmergeする運用がある
- GitHub Actions workflowとrequired status checkはない
- `.github/CODEOWNERS`はGitHub設定、AI設定、`GOAL.md`を`@bara8383`のreview対象にしている
- `GOAL.md`は研究の方向を示すが、現在地点から次の作業を選ぶ規則までは持たない

### 3.1 変更してもHuman reviewが必須の範囲

`.github/CODEOWNERS`と`main-protect` rulesetの`require_code_owner_review`により、次のpathは引き続きcode owner reviewを必須とする。

- `/GOAL.md`
- `/.github/`
- `/.claude/`
- `/.codex/`
- `**/CLAUDE.md`
- `**/AGENTS.md`

これはL4 workflowの例外ではなく外側の制約である。Agentが独自に同じ規則を再実装する必要はない。GitHub設定とAI設定を変更するPRは、通常コードのPRと同じ自律merge対象に含めない。

### 3.2 安全性を置く場所

提案では安全性を1個の`policy.json`へ集約しない。

| 制約 | 強制する場所 |
|---|---|
| GitHub・AI設定のowner review | `CODEOWNERS`とruleset |
| Test、format、再現性検査 | GitHub Actions |
| Secret、credential、課金resourceへの権限 | 実行環境の権限・sandbox |
| Agentの作業順序と禁止事項 | `AGENTS.md`と定期実行prompt |
| 作業の目的、scope、完了条件 | Issue |
| 実装差分、検証結果、未解決事項 | PR |

`AGENTS.md`は指示であり、権限境界の代わりではない。禁止操作は可能な限り実行環境とGitHub側でも実行不能にする。

## 4. 設計原則

### 4.1 Humanを通常loopの待ち状態にしない

通常の可逆なコード・test・文書変更は、Issue作成、実装、独立review、CI、mergeまでAgentが進める。HumanはGitHub・AI設定、Goal、費用、外部systemなど、あらかじめowner判断とした変更だけをreviewする。

### 4.2 IssueとPRをsource of truthにする

計画はIssue、実装はPR、機械検証はCIへ置く。同じ内容を別のJSONやportfolioへ複製しない。

### 4.3 未知を次の作業へ変換する

不明点が事実なら調査、技術的な選択なら小さい比較実験、安全に決められない価値判断ならHuman escalationへ変換する。「未検討」で停止しない。

### 4.4 独立reviewと決定論的検査を分ける

Review subagentはGoal整合性、設計、回帰risk、test不足を確認する。Test、format、artifact整合など機械判定できるものはCIで確認する。

### 4.5 WIPを1件に制限する

Agentが進行させるopen PRは原則1件とする。定期実行は既存PRの修正・review・mergeを、新しいIssue作成より優先する。

## 5. 提案する開発フロー

### 5.1 全体像

```text
GOAL.mdとGitHubの現状を確認
          ↓
候補を比較し、Issueを1件作成
          ↓
Plan review subagent
   FAIL ─→ Issueを修正 ─┐
          ↓ PASS         │
Issue番号からbranch作成  │
          ↓              │
実装・local test         │
          ↓              │
PR作成（Closes #N）      │
          ↓              │
CI + Diff review subagent
   FAIL ─→ 同じPRを修正 ─┘
          ↓ PASS
CODEOWNERS対象か？
  yes → Human review・merge待ち
  no  → Agentがmerge
          ↓
Issueが自動close、次回runで次のgapを選ぶ
```

IssueはAgent同士のメモではない。Humanも含めて「なぜこの作業をするか」をreviewできる計画である。PRはそのIssueを実現した証拠である。

### 5.2 Issueの内容

Agentが作るIssueには次を必須とする。

- 背景と確認した現状
- `GOAL.md`のどの差分を縮めるか
- 候補として比較した作業と、この作業を先にする理由
- 目的
- Scope / out of scope
- 完了条件
- 検証方法
- 既知のrisk、未解決事項
- Human判断が必要な場合は、選択肢、推奨案、各案の影響

初期導入では`.github/ISSUE_TEMPLATE/autonomous-task.yml`を追加し、この項目をIssue formとして固定する。Task Contractの役割はこのIssue本文が担う。

### 5.3 Issueの状態

状態はIssueとPRから読み取る。別fileへ状態を保存しない。

| 状態 | GitHub上の表現 | 次の行動 |
|---|---|---|
| 計画中 | open Issue、対応PRなし、Plan review未完了 | Plan reviewを行う |
| 実装可能 | IssueへPlan review `PASS` commentあり | branchを作り実装する |
| 実装中 | `Closes #N`を含むdraft PRあり | 実装を完了する |
| review中 | ready for reviewのPRあり | CIとDiff reviewを行う |
| 修正中 | failed CIまたはReview `FAIL`あり | 同じPRを修正する |
| owner待ち | CODEOWNERS対象でchecks成功 | Human reviewを待つ |
| merge可能 | CODEOWNERS対象外でchecks成功、Review `PASS` | Agentがmergeする |
| 完了 | PR merge済み、Issue close済み | 次のgapを選ぶ |
| blocked | Issueへ`BLOCKED` commentあり | 解除条件を確認する |

Labelは一覧性のために使ってよいが、正しさの判定をlabelだけに依存しない。PR、review、checkの実状態を毎回確認する。

### 5.4 PRの内容

`.github/pull_request_template.md`には次を置く。

- `Closes #<Issue番号>`
- Goalとの関係
- 変更内容
- Scope外の変更がないこと
- 実行した検証と結果
- 未検証事項、既知のrisk
- CODEOWNERS対象pathの有無
- Review subagentに特に確認してほしい点

新しいcommitをpushしたら、以前のDiff reviewは無効とし、最新headをreviewし直す。

## 6. 1回の定期実行で行うこと

### 6.1 起動方法

定期実行serviceは、repositoryの最新`main`をcheckoutし、`.codex/prompts/l4-loop.md`をtask promptとしてCodexを1回起動する。実行間の専用memoryは持たせず、Issue、PR、comment、commit、checkを次回runの入力にする。

概念上の起動commandは次の形とする。実際のscheduler固有設定とcredential設定はrepository外で管理する。

```sh
git fetch origin
git switch main
git pull --ff-only origin main
codex exec --full-auto ".codex/prompts/l4-loop.mdを読み、定期開発workflowを1工程進めてください"
```

実行環境はGitHub Appの短命credentialを使い、repository外のsecret、課金resource作成権限、ruleset変更権限を渡さない。自動mergeを有効にする段階では、対象repositoryのPR mergeに必要な最小権限だけを与える。

### 6.2 毎回の作業選択順序

Root Agentは次の上から最初に該当するものを1件だけ完了し、終了する。

1. Agent作成PRのHuman feedback、Review `FAIL`、failed CIへ対応する
2. Review待ちのPRを独立reviewする
3. Merge条件を満たしたPRをmergeする。CODEOWNERS対象ならHuman待ちを報告する
4. Plan review済みIssueを実装してPRを作る
5. Plan review前のIssueをreviewし、結果をIssueへ残す
6. Blocked Issueの解除条件が満たされたか確認する
7. Goalとの差分から候補を比較し、Issueを1件作る

これにより、通常の作業はHuman responseを挟まず、複数回の定期実行で次のように進む。

| 定期実行 | GitHubへの結果 |
|---|---|
| Run 1 | Issue作成 |
| Run 2 | Plan review comment |
| Run 3 | 実装branchとdraft PR作成 |
| Run 4 | CI確認、Diff review comment、必要なら修正 |
| Run 5 | 最新headのchecksを再確認してmerge |

1回のrunで1工程に限定するのは、途中失敗から再開しやすくし、重複PRや同時編集を避けるためである。操作前に既存Issue、PR、commentを検索し、同じ入力状態に対する操作を繰り返さない。

### 6.3 Merge条件

CODEOWNERS対象外の通常PRは、次をすべて満たした場合だけAgentがmergeする。

- 関連IssueのPlan reviewが`PASS`
- 最新head SHAに対するDiff reviewが`PASS`
- Required checksがすべて成功
- PRがdraftではなく、conflictがない
- 未解決のHuman comment、changes requested、blocking threadがない
- IssueのscopeとPR差分が一致する

CODEOWNERS対象pathを含むPRは、上記に加えて`@bara8383`のApproveを必要とし、AgentはHuman review前にmergeしない。

Phase 1ではすべてHumanがmergeし、この判定をshadow運用する。Phase 2でrulesetとCIを整備した後、CODEOWNERS対象外だけAgent mergeへ切り替える。

## 7. Subagentsの使い方

### 7.1 Root Agent

Root Agentだけがworkflowを進行し、GitHubへのcomment、branch作成、commit、push、PR作成、許可されたmergeを行う。複数subagentの結論が競合する場合もRoot Agentが一次情報を確認して統合する。

### 7.2 Plan reviewer

Issue作成後、別contextのsubagentへ次だけを依頼する。

```text
GOAL.md、repository、open Issue/PR、Issue #Nを読み取り専用で確認する。
このIssueが次の1件として妥当か、scopeと完了条件が検証可能かをreviewする。
変更は行わず、PASSまたはFAIL、blocking findings、確認した根拠を返す。
```

Root Agentは結果をIssue commentへ記録する。Commentには`<!-- l4-plan-review -->`、Issue本文のSHA-256、`PASS`または`FAIL`、blocking findingsを含める。Issue本文を変更すると以前の`PASS`は無効になる。`FAIL`ならIssueを修正し、新しいsubagentで再reviewする。

### 7.3 Diff reviewer

PRのCI完了後、Plan reviewerとは別の新しいcontextで次を依頼する。

```text
Issue #N、PR #M、base、最新head SHA、diff、test結果を読み取り専用で確認する。
correctness、scope、回帰、test不足、Goalとの不整合をreviewする。
変更は行わず、対象head SHA、PASSまたはFAIL、blocking findingsを返す。
```

Review結果は`<!-- l4-diff-review -->`、head SHA、`PASS`または`FAIL`、blocking findingsを含むPR commentとして残す。Headが変わったら以前の`PASS`は無効になり、再reviewする。

### 7.4 使わない場面

短い逐次作業や、同じfileを編集する実装を複数subagentへ分割しない。Subagentは独立調査、候補比較、read-only reviewに使う。共有worktreeへの書き込みはRoot Agentへ集約する。

## 8. `AGENTS.md`、`CLAUDE.md`、prompt、Skillsの分担

### 8.1 `AGENTS.md`

Repository全体で常に守る短い不変条件だけを書く。

- `GOAL.md`を変える作業と、Goalへ向かう通常作業を区別する
- GitHub・AI設定はcode owner review必須とする
- 有料resource、secret、外部公開、破壊的操作を自律実行しない
- Issue/PR/CIをsource of truthとし、既存作業を優先する
- Review subagentはread-only、GitHub writeはRoot Agentへ集約する
- Repository固有のtest command

作業選択順序やIssue template全文は書かない。それらは変更頻度が高く、定期実行promptとtemplateに置く。

### 8.2 `CLAUDE.md`

Claude Codeを使う場合の薄い入口にする。`AGENTS.md`と同じ規則を複製せず、最初にrootの`AGENTS.md`を読むこと、repository固有の追加事項がある場合だけ記載する。

初期の定期実行環境がCodexだけなら、`CLAUDE.md`は現在のcredential案内以外を変更しない。Claude用の独立agent定義も先に作らず、実際にClaudeを定期実行へ追加するとき別PRで提案する。

### 8.3 `.codex/prompts/l4-loop.md`

定期実行ごとに何を1件進めるかを書く。具体的には6.2の優先順位、reviewの起動条件、merge条件、終了状態を持つ。現在`docs/memo/prompt.md`にあるpromptをここへ移し、`/approve-issue`必須と全PRのHuman merge必須を段階移行に合わせて変更する。`.codex/`配下なので、変更には常にcode owner reviewが必要になる。

### 8.4 Skills

初期導入ではL4 loop全体をSkillにしない。Loopはscheduled prompt、状態はGitHub、常時規則は`AGENTS.md`に置く。

Skillは、実運用で繰り返しが確認できた専門手順だけに使う。最初の候補は次である。

- `review-research-plan`: 研究Issueの仮説、比較条件、metricをreviewする
- `review-pr`: Issueに対するdiff、test、回帰riskをreviewする
- `inspect-experiment-artifact`: Mark2 artifactの整合性を検査する

各Skillは`SKILL.md`へ発火条件と手順を書き、必要なchecklistやscriptだけを同梱する。Skillに権限、workflow状態、merge可否を保存しない。配置とruntimeへの登録方法は、実際に使う実行環境を確定した実装PRで決める。

## 9. 変更するファイル

初期導入に必要な変更を次に限定する。

| PR | Path | 変更内容 | Human reviewが必要な理由 |
|---|---|---|---|
| PR-1 | `.github/ISSUE_TEMPLATE/autonomous-task.yml` | 5.2のIssue form | `.github/`はCODEOWNERS対象 |
| PR-1 | `.github/pull_request_template.md` | 5.4のPR template | `.github/`はCODEOWNERS対象 |
| PR-2 | `.github/workflows/ci.yml` | Unit test、compile、`check-config`、mock 2 run、`git diff --check` | `.github/`はCODEOWNERS対象 |
| PR-3 | `AGENTS.md` | 8.1の不変条件 | `AGENTS.md`はCODEOWNERS対象 |
| PR-3 | `.codex/prompts/l4-loop.md` | 現行promptを移し、6.2の状態遷移とsubagent reviewを追加 | `.codex/`はCODEOWNERS対象 |
| PR-3 | `docs/memo/prompt.md` | 新しいpromptへの移行案内に置き換える | 同じPRの`.codex/`変更にowner reviewが必要 |

`CLAUDE.md`、`.claude/agents/`、Skillは初期導入では変更しない。必要性が実運用で確認された時点で、小さい別PRとして追加する。

追加しないもの:

- `automation/tasks/*.json`: Issueと重複するため
- `automation/portfolio.json`: Issue/PR一覧と重複するため
- `automation/policy.json`: CODEOWNERS、ruleset、実行環境の権限と重複するため
- `automation/l4/`: 初期flowはGitHub状態とpromptで実行できるため
- 独自Controller: scheduler、GitHub、CIで必要な状態遷移を表現できるため

## 10. CIの最小構成

PR作成時に次を実行する。

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
      - run: python -m compileall -q mark2 tests
      - run: python -m mark2.run check-config
      - name: mock 2 run comparison
        run: |
          python -m mark2.run run --backend mock --run-id ci-1 --output-root "$RUNNER_TEMP/m2"
          python -m mark2.run run --backend mock --run-id ci-2 --output-root "$RUNNER_TEMP/m2"
          python -m mark2.run compare "$RUNNER_TEMP/m2/ci-1" "$RUNNER_TEMP/m2/ci-2"
      - run: git diff --check "origin/${{ github.base_ref }}...HEAD"
```

Workflowにはwrite権限やsecretを渡さない。PR-2 merge後、Humanが`checks`をrequired status checkへ設定する。

## 11. Humanへescalateする条件

次の場合だけ通常loopを止め、既存Issueへ判断材料をまとめる。

- CODEOWNERS対象pathの変更
- `GOAL.md`の目的や成功条件の変更
- Baseline、評価metric、成功閾値の実質的変更
- Secret、credential、IAM、network、GitHub rulesetの変更
- 有料resource、購入、契約、承認済み上限を超える操作
- 外部system、本番、一般公開、第三者への送信
- 回復方法を確認できない削除やdata migration
- License、privacy、安全、倫理の判断
- 同じblocking findingを2回修正しても解消できない場合
- 複数案が同程度で、選択が後続研究を大きく拘束する場合

Escalation commentには、確認した事実、試したこと、2〜3個の選択肢、推奨案、各案の影響、Human回答後に行う操作を書く。新しいpolicy fileの作成依頼にはしない。継続的に必要な判断基準だとHumanが判断した場合だけ、code owner review対象の文書または`AGENTS.md`へ追加する。

## 12. 段階導入

### Phase 1: Human mergeのままflowを検証

PR-1〜PR-3を導入し、最低3件の通常TaskでIssue作成、Plan review、実装、Diff review、CI、Human mergeまで通す。

確認する項目:

- 同じIssueやPRを重複作成しない
- Review subagentが実装Agentの結論を追認するだけになっていない
- Issueの完了条件だけでDiffを判定できる
- CODEOWNERS対象を正しくHumanへ回せる
- Agentのmerge判定とHuman判断が一致する

### Phase 2: 通常PRのAgent merge

Phase 1でblocking findingの見逃しと誤ったmerge判定がなく、required checkが有効になったら、CODEOWNERS対象外の通常PRだけAgent mergeを許可する。

Humanは各PRの承認者ではなく、GitHub・AI設定、Goal、費用、例外判断のownerになる。

### 将来候補

運用上必要だと分かってから、次を個別に検討する。

- 定型reviewをSkill化する
- Review結果をPR commentから専用required checkへ移す
- 承認済みの費用上限内で実験を反復する
- 複数の独立実験を並列化する

Portfolio、独自Task JSON、独自policy engineは、Issue/PR運用で具体的な不足が確認されるまで導入しない。

## 13. 実装Issueの分割

方針承認後、次の3件だけを作る。

### I1. Issue・PR template

成果物:

- `.github/ISSUE_TEMPLATE/autonomous-task.yml`
- `.github/pull_request_template.md`

完了条件:

- IssueだけでGoal trace、候補比較、scope、完了条件、検証方法をreviewできる
- PRだけで対応Issue、変更内容、検証結果、未解決事項をreviewできる

### I2. Baseline CI

成果物:

- `.github/workflows/ci.yml`
- Required checkの設定手順

完了条件:

- Clean checkoutでunit test、compile、`check-config`、mock比較、diff checkが成功する
- 失敗したPRはmerge可能にならない

### I3. 定期実行promptとrepository instructions

成果物:

- `.codex/prompts/l4-loop.md`
- 新しいpromptへの移行案内にした`docs/memo/prompt.md`
- 更新した`AGENTS.md`

完了条件:

- GitHubの状態だけから6.2の次の工程を選べる
- Plan/Diff reviewを別contextのsubagentへ委譲する
- CODEOWNERS対象外のmerge条件とHuman escalation条件が明確である
- 同じ入力状態に対して操作を重複しない

## 14. 今回レビューしてほしい判断

1. 通常作業では`/approve-issue`を廃止し、Plan review subagentの`PASS`で実装へ進んでよいか
2. Phase 1を通常Task 3件のshadow運用とし、その後CODEOWNERS対象外だけAgent mergeへ移してよいか
3. SubagentはPlan/Diffのread-only reviewに限定し、repositoryとGitHubへのwriteをRoot Agentへ集約してよいか
4. 初期実装をtemplate、CI、`AGENTS.md`、定期実行promptの3 PRに限定してよいか
5. SkillとClaude用agent定義は必要性が確認されるまで追加しない方針でよいか

## 15. 参考資料

- [OpenAI: Multi-agent](https://developers.openai.com/api/docs/guides/responses-multi-agent)
- [OpenAI: Skills](https://developers.openai.com/plugins/concepts/skills)
