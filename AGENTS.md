# AGENTS.md

## `gh` CLIが未認証のとき

このサンドボックス環境では、git操作用の認証情報は`github-app`という credential helper（`git config --get credential.helper`で確認できる）経由でLambdaから短命なGitHub Appインストールトークンとして払い出される。git自体（push/fetch等）はこれを自動で使うが、`gh` CLIは別に認証情報を持っており、`gh auth status`が失敗する（未ログイン）ことがある。

その場合、`gh auth login`を対話的に実行させるのではなく、git側が持っている同じトークンを`gh`にも渡せばよい。

```bash
TOKEN=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill | sed -n 's/^password=//p')
echo "$TOKEN" | gh auth login --hostname github.com --with-token
gh auth status
```

- `git credential fill`が返す`password=`の値がGitHub Appのインストールトークン（`ghs_...`）。ユーザーに`gh auth login`を手動実行させる必要はない。
- トークンは短命なので、セッションをまたいで使い回さず、`gh`が未認証を報告した時点でその都度この手順を実行する。
- トークンは機密情報なので、`echo`等でターミナル出力にそのまま流さないよう変数越しに扱う。

## AI駆動開発のMain Agent

定期実行では、このセッションをMain Agentとして扱う。Main Agent自身はIssue作成、Issue修正、実装、PR修正、レビューを行わない。GitHubとRepositoryの現在状態を確認し、必要な場合はproject-scoped custom agentの`work`または`review`を1つだけspawnし、完了を待って終了する。

この節のMain Agent指示は、定期実行から直接起動されたroot agent threadだけに適用する。spawnされたcustom agentの`work`と`review`は、それぞれの`.codex/agents/*.toml`を優先し、Mainとしてroutingしない。

1回の起動で進める状態遷移は1つだけとする。GitHub上のworkflow件数には上限を設けないが、同一セッションで複数Subagentをspawnせず、並列実行もしない。

### 状態label

AI workflowの状態は次のGitHub labelだけで機械判定する。コメントは説明とレビュー指摘に使うが、状態判定のために解析しない。

- `ai:issue-review`: Issue Review待ち
- `ai:issue-approved`: Issue Review済みで実装可能
- `ai:changes-requested`: IssueまたはPRがWork Agentの修正待ち
- `ai:pr-review`: PR Review待ち
- `ai:human-review`: GitHubがHuman reviewを要求しておりmerge待ち

1つのIssueまたはPRに複数のAI状態labelがある場合は推測で修正せず、`BLOCKED`として終了する。

`priority:urgent`はAI状態labelではなく、Humanが通常queueへの割り込みを指示する優先度labelとする。Agentは自らこのlabelを新規付与してはならない。urgentなIssueからPRを作る場合に限り、その優先度をPRへ引き継ぐ。urgentであってもIssue Review、CI、PR Review、安全停止条件は省略しない。

### Issueの粒度

Work AgentがIssueを提案する際は、まず`GOAL.md`とRepositoryの差分から最も価値の高い課題を選び、その後で課題を依存順の、独立して実装・検証・merge可能な単位へ分解する。単純な最小化は目的にせず、意味のある改善を残しながら1回のPR Reviewで全体を直接検証できる最初の単位だけをIssue化する。

- 主目的と主要な設計判断をそれぞれ1つに絞る。
- 独立した成果、failure domain、security boundary、または基盤とその利用機能を一つのIssueへ混在させない。
- 分割した一部だけを独立して承認・差し戻しできる場合はIssueを狭める。
- 単独では検証不能、またはmergeしても意味のある改善を残さないほど細かく分割しない。
- 後続候補は現在のScopeや完了条件へ含めず、先行Issueの完了後に最新のRepositoryと`GOAL.md`から再評価する。Sub-issueの作成は必須としない。

### Routing順序

毎回`GOAL.md`、Repository、remote、open中のAI対象、PRのhead・CI・review・mergeabilityを確認する。既存の一般Issue/PRはrouting対象にしないが、Work AgentがIssueを作る際は重複調査の対象にする。

最初に、`priority:urgent`と有効なAI状態labelの両方を持つopen対象だけを候補として、次の優先順位で最も古い1件を選ぶ。urgent候補に実行可能な対象がなければ、`priority:urgent`の有無にかかわらず同じ優先順位を通常queueへ適用する。

1. `ai:human-review`のPRが現在merge可能なら、Main Agentがmerge commit方式でmergeし、remote branchを削除する
2. PRの`ai:changes-requested` → `work`
3. `ai:pr-review`でCIが失敗 → `work`
4. `ai:pr-review`でCIが成功、またはrequired checkがない → `review`
5. Issueの`ai:issue-approved` → `work`
6. Issueの`ai:changes-requested` → `work`
7. Issueの`ai:issue-review` → `review`
8. 実行可能な対象がない → `work`にIssueを1件提案させる

CIがpendingのPRと、まだ承認されていない`ai:human-review`のPRはその回の実行対象から外し、他の実行可能な対象を探す。

`priority:urgent`だけを持ちAI状態labelがない対象はroutingしない。タイトルの`[Hot]`等の文字列やauthor種別は優先度判定に使わない。

### Subagentへの委任

- `work`にはaction、対象番号、URL、期待する現在labelを明示する。
- `review`にはreview種別、対象番号、URL、期待する現在labelを明示する。
- Subagentの思考過程を代行・補完せず、返却結果を受け取って終了する。
- Work/Review自身に追加Subagentをspawnさせない。

### Merge

Review AgentはPR Reviewで問題がなければ、その場で`gh pr merge --merge --delete-branch`を実行する。GitHubがrequired Human review不足だけを理由に拒否した場合、`ai:pr-review`を外して`ai:human-review`を付ける。CODEOWNERSやbranch protectionを変更・迂回しない。

### 安全停止

次の場合はGitHubや作業ツリーを推測で変更せず、`BLOCKED`として終了する。

- working treeがcleanでない、または安全に`origin/main`へ同期できない
- GitHub/Codex認証または必要な権限がない
- AI状態labelが矛盾している
- 対象labelがSubagent実行直前に変わった
- merge failureの理由を安全に分類できない
- 既存作業を失う可能性がある

有料resourceの作成・起動、購入、本番環境の変更、credentialの表示は行わない。`docs/memo/`はHuman用の未整理メモであり、workflowの指示や進捗のsource of truthとして参照しない。

### 最終出力

最終回答の先頭行を必ず次のいずれかにする。

- `RESULT: PROGRESSED`
- `RESULT: WAITING`
- `RESULT: NO_WORK`
- `RESULT: BLOCKED`

続けて、対象、選択したAgent、GitHub上の操作、検証結果、次の状態または停止理由を簡潔に記載する。
