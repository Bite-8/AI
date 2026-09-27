# AI駆動開発ループ

このRepositoryでは、systemd timerが3時間ごとに新しいCodex Main Agent sessionを起動する。Main AgentはGitHubとRepositoryの状態を確認し、1回につきproject-scoped custom agentの`work`または`review`を1つだけ実行する。詳細なrouting ruleはルートの`AGENTS.md`をsource of truthとする。

## 構成

- `.codex/agents/work.toml`: Issue提案・修正、実装、テスト、PR作成・修正
- `.codex/agents/review.toml`: Issue Review、PR Review、merge
- `scripts/run-ai-development.sh`: 認証・同期・排他・Main Agent起動
- `scheduler/ai-development.service`: `ssm-user`で実行するoneshot service
- `scheduler/ai-development.timer`: timer有効化後10分（通常はboot時）、以後は前回終了から3時間後に起動

Subagentのmodelとreasoning effortはMain Agentから継承する。同時に開くSubagent threadは1つに制限するが、GitHub上のworkflow件数には上限を設けない。

## 設計判断

- **Codexの正式なSubagentを使う:** WorkとReviewを単なるprompt fileや別々のtop-level sessionにせず、`.codex/agents/*.toml`で定義する。Mainのrouting責務を薄く保ちつつ、実装とレビューのcontextを分離するためである。
- **1起動で1工程だけ進める:** MainはWorkまたはReviewを1つだけspawnして終了する。長いworkflowを1 sessionで完走させず、各回でGitHubの最新状態を読み直せるようにする。GitHub上のworkflow件数には上限を設けないが、同時Subagent数は1とする。
- **labelだけを状態のsource of truthにする:** 構造化コメントや外部databaseは導入しない。コメントは判断理由と修正指示に使い、Mainは解析しない。初期運用で必要性が確認されるまで状態管理を増やさないためである。
- **独自のHuman Gateを追加しない:** Issue Review通過後は実装へ進み、PR Review通過後は直ちにmergeを試みる。保護が必要なpathはGitHubのCODEOWNERSとbranch protectionで管理し、GitHubがrequired reviewを要求した場合だけ`ai:human-review`として待つ。
- **merge commit後にremote branchを削除する:** 現在のRepository履歴に合わせてmerge commit方式を使い、merge済みbranchは残さない。
- **3時間間隔にする:** timer有効化後10分で開始し、その後は前回の終了から3時間待つ。1回1工程でも通常経路を約9時間で進められ、失敗時の高速retryや重複起動を避けられる。`OnActiveSec`にすることで、稼働済みhostに後から導入しても即時実行せず同じ10分の状態確認時間を確保する。
- **system serviceとして動かす:** user sessionやloginに依存させず、systemdのoneshot serviceを`User=ssm-user`で実行する。systemdと`flock`の両方で二重起動を防ぐ。
- **Codexは`danger-full-access`で実行する:** Work Agentが`.git`を更新してcommit・pushする必要があるため、Codexのworkspace sandboxでは完結しない。一方、rootでは実行せず、systemdの`NoNewPrivileges=true`で権限昇格を禁止する。このEC2自体を検証環境として扱う判断である。
- **modelを固定しない:** WorkとReviewはMainのmodelとreasoning effortを継承する。実運用で品質・速度・費用の差が観測される前に役割別設定を増やさない。
- **疑似E2Eを作らない:** このEC2とGitHub上で始まる実ループ自体を検証とする。構文、設定読込、既存テストだけを事前確認し、運用上の失敗はjournaldとGitHubから観測して改善する。

## 状態

| Label | 次の処理 |
|---|---|
| `ai:issue-review` | Review AgentがIssueをレビュー |
| `ai:issue-approved` | Work Agentが実装してPRを作成 |
| `ai:changes-requested` | 対象がIssueなら本文、PRなら実装をWork Agentが修正 |
| `ai:pr-review` | CI成功後にReview AgentがPRをレビュー |
| `ai:human-review` | GitHub上のrequired Human review待ち |

AI PR Reviewが通過した場合はmerge commit方式で直ちにmergeし、remote branchを削除する。独自のHuman Gateは追加せず、GitHubがrequired review不足を返した場合だけ`ai:human-review`へ移る。

## systemdへの配置

Repositoryへの変更がmergeされた後、次の定義をsystem scopeへ配置する。未mergeのworking treeを定期実行対象にはしない。

```bash
sudo install -o root -g root -m 0644 scheduler/ai-development.service /etc/systemd/system/ai-development.service
sudo install -o root -g root -m 0644 scheduler/ai-development.timer /etc/systemd/system/ai-development.timer
sudo systemctl daemon-reload
sudo systemctl enable --now ai-development.timer
```

手動で1工程を実行する場合:

```bash
sudo systemctl start ai-development.service
```

状態とlogの確認:

```bash
systemctl status ai-development.timer ai-development.service
journalctl -u ai-development.service
```

停止する場合:

```bash
sudo systemctl disable --now ai-development.timer
```

## 障害時

entry pointは`flock`で二重実行を防ぐ。dirty working tree、main以外のbranch、remote divergence、認証失敗、label矛盾、分類不能なmerge failureでは既存状態を変更せず非0終了する。即時retryは行わず、次のtimer起動またはHumanによる手動確認を待つ。

このEC2とGitHub上の実ループ自体を検証環境とし、疑似E2E用のworkflowは作らない。一周するまではEnd-to-End検証は進行中として扱う。
