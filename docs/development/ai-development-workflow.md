# AI駆動開発workflow

## 目的と初期構成

`GOAL.md`と現在のrepositoryの差分から、次の最小loopを継続する。

```text
Scheduled Task
  -> Main Agent（状態判定とroutingのみ）
      -> Work Agent（Issue作成・修正、または実装・PR作成・修正）
      -> Review Agent（Issue Review、またはPR Review）
  -> Human Gate
  -> Humanがmerge
```

初期構成はMain、Work、Reviewの3役だけとする。Explorer、Planner、
Implementerなどへの細分化、並列実行、独自controller、task graph、状態DB、
事前のSkill作成は行わない。

## Source of truth

- Goal: `GOAL.md`
- 作業計画と完了条件: GitHub Issue
- 実装と検証結果: GitHub Pull Requestとdiff
- 機械検証: GitHub Actions
- 共通規則: `AGENTS.md`
- local権限: `.codex/config.toml`のMain、Work、Review用permission profile
- Agent定義: `.codex/agents/work-agent.toml`と
  `.codex/agents/review-agent.toml`
- Main Agent prompt: `.codex/prompts/ai-development-loop.md`

AI workflowのIssueは`codex` labelと`<!-- ai-workflow:task -->`を持つ。
対応PRは`<!-- ai-workflow:pr -->`を持つ。既存のIssueとPRをそのまま使い、
別の進捗fileへ状態を複製しない。

## Review状態の記録

### Issue Review

Review Agentは次のcommandでIssueのtitleとbodyのcanonical hashを計算する。

```bash
gh issue view <number> --json title,body \
  --jq '.title + "\n" + .body' | sha256sum
```

Review commentの末尾を次の形式にする。

```markdown
<!-- ai-workflow:issue-review -->
AI_WORKFLOW_ISSUE_REVIEW
- verdict: APPROVED
- issue_hash: <64文字のsha256>
```

`verdict`は`APPROVED`または`CHANGES_REQUESTED`だけを使う。Main Agentが
同じcommandで計算したhashと一致する最新commentだけが有効である。Issue
本文を変更するとreviewは自動的に古くなる。

### PR Review

Review AgentはGitHubのApproveを代行せず、review commentの末尾を次の形式に
する。

```markdown
<!-- ai-workflow:pr-review -->
AI_WORKFLOW_PR_REVIEW
- verdict: APPROVED
- head_sha: <40文字のfull head SHA>
```

`head_sha`が現在のPR headと一致する最新reviewだけが有効である。push後は
再reviewが必要になる。

## Human Gate

AI ReviewはHuman Gateを置き換えない。

1. Issue実装前に、AI Issue Reviewが`APPROVED`であることに加え、GitHub
   user `bara8383`による`/approve-issue` commentを必要とする。
2. merge前に、AI PR Reviewが`APPROVED`であることに加え、`bara8383`が
   現在のhead commitへ行ったGitHubのApprove reviewを必要とする。
3. AgentはPRをmergeしない。Humanがmergeする。

CODEOWNERS、branch ruleset、sandbox、credential、課金resourceに対する既存
制約を弱めない。有料resourceや外部systemの変更はIssue承認と別の明示承認を
必要とする。

## 状態遷移

Main Agentは毎回read-onlyのGit/GitHub queryでremoteとrepositoryの状態を再取得
する。Git metadataは変更しない。次の順で最初に該当する遷移を1つだけ実行し、
終了する。

| 現在状態 | 起動するAgent / 終了状態 |
|---|---|
| PRに後続のWork回答・commitがないHuman指摘、AI changes requested、success以外で完了したCIがある | Work: `PR_REVISE` |
| PRに現在headのAI reviewがない | Review: `PR_REVIEW` |
| AI PR review済み、Human Approveなし | `AWAITING_HUMAN_PR_REVIEW` |
| AI/Human review済み、現在headの全expected CIがsuccess | `AWAITING_HUMAN_MERGE` |
| AI/Human review済み、現在headのexpected CIが未開始または実行中 | `AWAITING_CI` |
| IssueにAI changes requested、または後続のWork回答・本文更新がないHuman修正がある | Work: `ISSUE_REVISE` |
| Issueに現在本文のAI reviewがない | Review: `ISSUE_REVIEW` |
| AI Issue review済み、Human承認なし | `AWAITING_HUMAN_ISSUE_APPROVAL` |
| AI/Human承認済みIssueにPRがない | Work: `IMPLEMENT` |
| 処理対象がない | Work: `ISSUE_CREATE` |

既存PR、既存Issue、新規Issueの順に優先する。同一hashまたはhead SHAに対して
同じ処理を重複実行しない。Main Agent自身は成果物を作らず、custom agentを
1つだけ起動する。

## Agentの責務

### Work Agent

- GOALと現状の差分から、重複しないIssueを1件作る
- review指摘を受けたIssue本文を修正する
- AIとHumanの両方が承認したIssueを実装し、test、commit、push、PR作成まで行う
- PRの指摘またはCI失敗を既存branchで修正する

### Review Agent

- Work Agentと別contextで、GOAL、repository、Issue、PR diff、test、CI、規則を
  一次情報から確認する
- Issueの優先度、順序、明確さ、粒度、重複、完了条件、検証方法を確認する
- PRの要求充足、scope、設計整合、bug、回帰、test、文書、完了条件を確認する
- read-only permission profileを使い、成果物を変更しない

read-only profileはlocal file変更を抑止するが、共有credentialによるremote
writeまで分離する境界ではない。このためReview Agentのremote writeも対象への
review comment 1件だけに制限する。

`.codex/config.toml`ではMainとReviewをrepository read-only、Workだけをrepositoryと
Git metadataへwrite可能にする。Reviewはtest用の一時directoryだけwriteできる。
Workの`.codex/`と`.agents/`はread-only、全階層の`.env`派生fileはdenyとする。
GitHub操作とcredential helperに必要なnetwork accessは3 profileへ許可する。
permission profileとlegacyの`sandbox_mode`は併用できないため、Scheduled Taskでは
projectのCustom設定を選び、別のpermission modeで上書きしない。

## Scheduled Taskの登録

Scheduled Taskはrepository fileだけでは作成できない。PR merge後、ChatGPTまたは
Codex desktop appのScheduled画面で次のように1件登録する。

- 種類: standalone（runごとに新しいchat）
- 対象project: このrepository
- 実行場所: dedicated background worktree
- Permissions: Custom（projectの`.codex/config.toml`を使用）
- 頻度: まず1時間ごと。最初の数runを確認後に調整する
- saved prompt:

```text
Read .codex/prompts/ai-development-loop.md completely and execute exactly one routing cycle. Follow AGENTS.md and do not continue to a second phase in the same run.
```

permission profileはGitHubとcredential helperに必要なcommand network accessを
許可する。Agent instructionではそれ以外のnetwork利用を禁止する。PCとdesktop
appが起動しており、project pathが存在する必要がある。

## 導入確認

### merge前のdry run

1. `python3 -m unittest discover -s tests -v`
2. `python3 -m mark2.run check-config`
3. `python3 -m compileall -q mark2 tests`
4. `git diff --check origin/main...HEAD`
5. Main promptを通常chatで実行し、Mainが成果物を直接変更せず、最初の該当
   Agentを1つだけ選ぶことを確認する

### merge後のend-to-end確認

最初の実taskで、次を順番に確認する。Human Gateがあるため、複数のScheduled
Task runとHuman操作にまたがる。

- Work Agentがtemplate準拠のIssueを作る
- Review Agentが現在のIssue hashを含むreviewを残す
- Humanが`/approve-issue`を投稿する
- Work Agentが実装、test、commit、push、PR作成を行う
- Review Agentが現在のhead SHAを含むreviewを残す
- CIがpassする
- HumanがApproveし、mergeする

1件完走するまでは初期導入を完了扱いにしない。実運用で同じ長い手順、同じ
失敗、または独立して改善すべきworkflowが複数回観測された場合だけ、Skill化や
Agent細分化を別Issueで検討する。
