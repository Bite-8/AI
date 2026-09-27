# AGENTS.md

## `gh` CLIが未認証のとき

このサンドボックス環境では、git操作用の認証情報は`github-app`という credential helper（`git config --get credential.helper`で確認できる）経由でLambdaから短命なGitHub Appインストールトークンとして払い出される。git自体（push/fetch等）はこれを自動で使うが、`gh` CLIは別に認証情報を持っており、`gh auth status`が失敗する（未ログイン）ことがある。

その場合、`gh auth login`を対話的に実行させるのではなく、git側が持っている同じトークンを`gh`にも渡せばよい。

```bash
TOKEN=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill | sed -n 's/^password=//p')
printf '%s\n' "$TOKEN" | gh auth login --hostname github.com --with-token
unset TOKEN
gh api user --jq .login
```

- `git credential fill`が返す`password=`の値がGitHub Appのインストールトークン（`ghs_...`）。ユーザーに`gh auth login`を手動実行させる必要はない。
- トークンは短命なので、セッションをまたいで使い回さず、`gh`が未認証を報告した時点でその都度この手順を実行する。
- トークンは機密情報なので、`echo`等でターミナル出力にそのまま流さないよう変数越しに扱う。
- `gh auth status`はトークンの一部を表示する場合があるため、認証確認には`gh api user --jq .login`を使う。

## AI開発workflow

定期実行のMain Agent、Work Agent、Review Agentは
`.codex/prompts/ai-development-loop.md`と
[`docs/development/ai-development-workflow.md`](docs/development/ai-development-workflow.md)
に従う。

- Main AgentはGitHubとrepositoryの状態を判定し、1回の実行でWork AgentまたはReview Agentのどちらか1つだけを起動する。Main Agent自身はIssue作成、実装、reviewを行わない。
- Work AgentはIssue作成・修正、実装、test、commit、push、PR作成・修正を担当する。
- Review AgentはWork Agentと別contextで一次情報を確認し、IssueまたはPRをreviewする。実装やIssue本文の編集は行わない。
- Main/Work/Reviewのlocal file・network権限は`.codex/config.toml`のpermission profileで分離する。Scheduled Taskではlegacyの`sandbox_mode`で上書きせず、projectのCustom設定を使う。
- AI開発対象のIssueには`codex` labelと`<!-- ai-workflow:task -->` markerを付ける。PRには`<!-- ai-workflow:pr -->` markerを付ける。
- AI reviewの状態はrunbookで定めた構造化commentで記録する。Issue reviewは現在のIssue本文hash、PR reviewは現在のhead SHAと一致する場合だけ有効とする。
- AI reviewを通過しても、既存のbranch protectionとCODEOWNERSを変更・迂回しない。AgentはPRをmergeせず、`main`へ直接pushしない。
- 有料resource、secret、credential、GitHub ruleset、外部systemは変更しない。
- 新しいSkillや専門Agentは先に追加しない。同じ手順や失敗が複数回観測され、独立して改善する価値が確認できた場合に別Issueで検討する。
