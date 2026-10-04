# AI駆動開発ループ

このRepositoryでは、systemd timerが毎日00:00と12:00 UTCに新しいCodex Main Agent sessionを起動する。Main AgentはGitHubとRepositoryの状態を確認し、1回につきproject-scoped custom agentの`work`または`review`を1つだけ実行する。詳細なrouting ruleはルートの`AGENTS.md`をsource of truthとする。

## 構成

- `.codex/agents/work.toml`: Issue提案・修正、実装、テスト、PR作成・修正
- `.codex/agents/review.toml`: Issue Review、PR Review、merge
- `scripts/run-ai-development.sh`: 認証・同期・排他・Main Agent起動
- `scheduler/ai-development.service`: `ssm-user`で実行するoneshot service
- `scheduler/ai-development.timer`: hostのlocal timezoneに依存せず、毎日00:00と12:00 UTCに起動

Subagentのmodelとreasoning effortはMain Agentから継承する。同時に開くSubagent threadは1つに制限するが、GitHub上のworkflow件数には上限を設けない。

## 設計判断

- **Codexの正式なSubagentを使う:** WorkとReviewを単なるprompt fileや別々のtop-level sessionにせず、`.codex/agents/*.toml`で定義する。Mainのrouting責務を薄く保ちつつ、実装とレビューのcontextを分離するためである。
- **1起動で1工程だけ進める:** MainはWorkまたはReviewを1つだけspawnして終了する。長いworkflowを1 sessionで完走させず、各回でGitHubの最新状態を読み直せるようにする。GitHub上のworkflow件数には上限を設けないが、同時Subagent数は1とする。
- **価値選択後にIssueを細分化する:** Workは`GOAL.md`との差分から最も価値の高い課題を先に選び、その後で依存順の、独立して実装・検証・merge可能な単位へ分解する。単純な最小化は行わず、意味のある改善を残しながら1回のPR Reviewで直接検証できる最初の単位だけをIssue化する。後続候補は先行作業の完了後に再評価し、Sub-issue化は必須としない。
- **labelだけを状態のsource of truthにする:** 構造化コメントや外部databaseは導入しない。コメントは判断理由と修正指示に使い、Mainは解析しない。初期運用で必要性が確認されるまで状態管理を増やさないためである。
- **Humanがurgent queueを明示する:** `priority:urgent`はHumanが通常queueへの割り込みを指示するためだけに使う。Agentはurgencyを新規判断せず、urgent Issueから作るPRへ既存labelを引き継ぐ場合に限って付与する。urgentでもReview、CI、安全停止条件を省略しない。
- **独自のHuman Gateを追加しない:** Issue Review通過後は実装へ進み、PR Review通過後は直ちにmergeを試みる。保護が必要なpathはGitHubのCODEOWNERSとbranch protectionで管理し、GitHubがrequired reviewを要求した場合だけ`ai:human-review`として待つ。
- **merge commit後にremote branchを削除する:** 現在のRepository履歴に合わせてmerge commit方式を使い、merge済みbranchは残さない。
- **UTCの固定時刻に1日2回起動する:** `OnCalendar`にtimezoneを含め、hostのlocal timezoneや前回の終了時刻に左右されず毎日00:00と12:00 UTCに起動する。`Persistent=false`によりhost停止中に逃した定刻分は起動時にcatch-upせず、次の定刻まで待つ。固定時刻以外の追加activationは設定しない。
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

`priority:urgent`は上表の状態とは独立した優先度labelである。Humanだけが新たなurgencyを指定できる。Mainはまず`priority:urgent`とAI状態labelの両方を持つ実行可能な対象へ通常の状態優先順位を適用し、該当がなければ通常queueを処理する。タイトルの`[Hot]`やauthor種別は優先度判定に使用しない。

例として、通常PRが`ai:changes-requested`であっても、`priority:urgent`と`ai:issue-review`を持つIssueがあればurgent Issueを先にレビューする。これはqueueの順序だけを変更し、Issue ReviewやPR Reviewを迂回しない。

## Issueの細分化

Issue提案では、最も価値の高いGoal gapを選んだ後に粒度を決める。主目的、主要な設計判断、主要なfailure domainをそれぞれ1つに絞り、分割した一部だけを独立して承認・差し戻しできる場合はScopeを狭める。一方、単独では検証できない、またはmergeしても意味のある改善を残さない単位までは分割しない。

後続作業が想定できても現在の完了条件には含めず、必要なら非拘束的な候補として記録する。先行Issueのmerge後に最新のRepositoryと`GOAL.md`を比較し、依然として価値があれば改めてIssue化する。計画保存のためだけに親Issue、Sub-issue、依存待ちlabelを増やさない。

## systemdへの配置

Repositoryへの変更と実ホストへの反映は別の操作であり、mergeだけで反映済みとはみなさない。定期実行のMain Agent、Work Agent、Review Agentは実ホストを変更しない。

実ホストへの反映は、Humanが明示的に指示した場合に、その指示を直接受けたroot agentが担当する。関連変更が`origin/main`へmerge済みで、working treeがcleanかつlocal `main`が`origin/main`と一致していることを確認し、原則として次回の対象unit発火前、またはHumanが指定したmaintenance windowに実施する。未mergeのworking treeを定期実行対象にはしない。

`scheduler/`配下または実ホスト反映を必要とする設定を変更するPRは、PR本文に反映要否、対象unit、merge後の操作、想定する再起動影響を記載する。

反映前にRepository内のunitを検証し、installed unitとの差分と対象を確認する。

```bash
systemd-analyze verify scheduler/ai-development.timer scheduler/ai-development.service
diff -u /etc/systemd/system/ai-development.timer scheduler/ai-development.timer
diff -u /etc/systemd/system/ai-development.service scheduler/ai-development.service
```

確認後、対象の定義だけをsystem scopeへ配置する。

```bash
sudo install -o root -g root -m 0644 scheduler/ai-development.service /etc/systemd/system/ai-development.service
sudo install -o root -g root -m 0644 scheduler/ai-development.timer /etc/systemd/system/ai-development.timer
sudo systemctl daemon-reload
sudo systemctl enable --now ai-development.timer
```

変更していないunitは再配置・restartしない。timerだけを変更した場合は、関連serviceを手動起動せずtimerだけをrestartする。

```bash
sudo systemctl restart ai-development.timer
cmp scheduler/ai-development.timer /etc/systemd/system/ai-development.timer
systemctl status ai-development.timer --no-pager
systemctl list-timers ai-development.timer --all --no-pager
```

反映後は、実施者、実施時刻、配置・reload・restartの対象、Repository版との一致、active状態、次回発火時刻をHumanへ報告する。

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

entry pointは`flock`で二重実行を防ぐ。dirty working tree、main以外のbranch、remote divergence、認証失敗、label矛盾、分類不能なmerge failureでは既存状態を変更せず非0終了する。即時retryやcatch-upは行わず、次の00:00または12:00 UTCのtimer起動、あるいはHumanによる手動確認を待つ。host停止中に定刻を逃した場合も、起動直後には実行せず次の定刻まで待つ。

このEC2とGitHub上の実ループ自体を検証環境とし、疑似E2E用のworkflowは作らない。一周するまではEnd-to-End検証は進行中として扱う。
