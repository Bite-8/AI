# AI駆動開発workflow

## 目的

GOAL.mdと現在のrepositoryの差分から、次の最小loopを継続する。

    systemd timer
      -> scripts/run-ai-development.sh
        -> Main Agent（状態判定とroutingのみ）
          -> Work Agent（Issue作成・修正、実装・PR作成・修正）
          -> Review Agent（Issue ReviewまたはPR Review）
      -> 既存のbranch protection / CODEOWNERS
      -> Humanがmerge

Main、Work、Reviewの3役だけを使う。ExplorerやPlannerへの細分化、並列実行、
独自controller、task graph、状態DB、事前のSkill作成は行わない。

## 構成file

| file | 役割 |
|---|---|
| .codex/prompts/ai-development-loop.md | Main Agentのstate machineとrouting rule |
| .codex/agents/work-agent.toml | Issue作成・修正、承認済みIssueの実装、PR作成・修正 |
| .codex/agents/review-agent.toml | 独立contextでのIssue ReviewとPR Review |
| .github/ISSUE_TEMPLATE/autonomous-development.yml | AI開発Issue Form |
| .github/pull_request_template.md | 実装PRの説明項目 |
| scripts/run-ai-development.sh | Codexを1回起動するentry point |
| scheduler/systemd/ai-development.service | entry pointを起動するuser service |
| scheduler/systemd/ai-development.timer | 起動5分後と毎正時にserviceを起動するscheduler |
| .codex/config.toml | Main、Work、Reviewのlocal permission profile |

GitHub IssueとPRをsource of truthとし、別の進捗fileへ状態を複製しない。
AI workflowのIssueはcodex labelと <!-- ai-workflow:task -->、PRは
<!-- ai-workflow:pr --> を持つ。

## Agentの責務

### Main Agent

GitHubとrepositoryの状態をread-onlyで再取得し、優先順位表の最初に該当する
phaseへWork AgentまたはReview Agentを1つだけ起動する。Main Agent自身は
Issue作成、review、実装、commit、pushを行わない。起動したAgentが終了したら
成果物を確認してrunを終了し、同じrunで次のphaseへ進まない。

### Work Agent

- ISSUE_CREATE: GOALと現状の最小の差分をIssue 1件にする
- ISSUE_REVISE: review指摘をIssueへ反映する
- IMPLEMENT: AI Reviewで承認済みのIssueを専用branchで実装し、検証、commit、
  push、PR作成まで行う
- PR_REVISE: 既存PR branchで指摘を修正し、検証、commit、push、Markdownでの
  対応報告まで行う

Work Agentはmainへ直接pushせず、PRをmergeしない。

### Review Agent

Work Agentと別contextで、GOAL、repository、Issue、PR diff、検証結果、規則を
一次情報から確認する。

- ISSUE_REVIEW: 優先度、順序、明確さ、粒度、重複、完了条件、検証方法を確認
- PR_REVIEW: 要求充足、scope、設計整合、bug、回帰、test、文書を確認

成果物は編集せず、指定された対象へのreview comment 1件だけを投稿する。

## Review状態

Issue Reviewはtitleとbodyのhashへ結び付ける。

    gh issue view <number> --json title,body \
      --jq '.title + "\n" + .body' | sha256sum

comment末尾は次の形式とする。

    <!-- ai-workflow:issue-review -->
    AI_WORKFLOW_ISSUE_REVIEW
    - verdict: APPROVED
    - issue_hash: <64文字のsha256>

PR Reviewは現在のhead SHAへ結び付ける。

    <!-- ai-workflow:pr-review -->
    AI_WORKFLOW_PR_REVIEW
    - verdict: APPROVED
    - head_sha: <40文字のfull head SHA>

verdictはAPPROVEDまたはCHANGES_REQUESTEDだけを使う。Issue本文の変更または
PRへのpush後は、以前のreviewを無効として再reviewする。

## 状態遷移

Main Agentは既存PR、既存Issue、新規Issueの順に優先し、次の最初の1件だけを
実行する。

| 現在状態 | 次の処理 |
|---|---|
| PRに未対応のHuman指摘、または現在headのAI CHANGES_REQUESTEDがある | Work: PR_REVISE |
| PRに現在headのAI reviewがない | Review: PR_REVIEW |
| PRに現在headのAI APPROVEDがある | AWAITING_HUMAN_MERGE |
| Issueに未対応のHuman指摘、または現在本文のAI CHANGES_REQUESTEDがある | Work: ISSUE_REVISE |
| Issueに現在本文のAI reviewがない | Review: ISSUE_REVIEW |
| AI APPROVEDのIssueに関連open PRがない | Work: IMPLEMENT |
| 処理対象がない | Work: ISSUE_CREATE |

同じIssue hashまたはPR head SHAに同じphaseを重複実行しない。
AWAITING_HUMAN_MERGEでは何も変更しない。merge可否はrepositoryに既に設定された
branch protectionとCODEOWNERSへ委ねる。このworkflow独自のHuman承認commentや
CI gateは追加しない。

## 自動実行entry point

scripts/run-ai-development.shはschedulerとCodex CLIの間の固定入口である。

- scriptの配置からrepositoryを解決する。別checkoutでは
  AI_DEVELOPMENT_REPOで明示できる
- git directory配下のai-development/run.lockをflockで確保し、重複runを止める
- AI_DEVELOPMENT_LOG_DIR、未指定時はgit directory配下へrunごとのlogを保存する
- repository rootをworking directoryにしてcodex execを新規sessionで起動する
- .codex/config.tomlのpermission profileを使い、legacy sandbox optionで上書きしない
- Main prompt全体を標準入力から渡し、1 routing cycleで終了する

手動dry run:

    scripts/run-ai-development.sh

同じrepositoryで既にrun中ならexit 75を返す。codexが失敗した場合は、そのexit
statusを維持する。

## Scheduler

初期schedulerはsystemd user timerを採用する。対象machine内で完結し、
再起動後のcatch-upとjournalを利用できるためである。

scheduler/systemd/ai-development.serviceは %h/project/AI を標準配置としている。
repository pathが異なる場合は、serviceのWorkingDirectory、Environment、
ExecStartを実際のpathへ変更してから登録する。
Codex CLIを別のdirectoryへinstallしている場合はEnvironmentのPATHも変更する。

    mkdir -p ~/.config/systemd/user
    cp scheduler/systemd/ai-development.service ~/.config/systemd/user/
    cp scheduler/systemd/ai-development.timer ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now ai-development.timer
    systemctl --user list-timers ai-development.timer

timerはmachine起動5分後と毎正時に実行する。頻度は最初の数runの所要時間とlogを
確認してから調整する。repositoryをmergeしただけではschedulerは登録されない。
上記のmachine設定はHumanが行う。

状態確認:

    systemctl --user status ai-development.timer
    journalctl --user -u ai-development.service

## 導入確認

merge前:

1. python3 -m unittest discover -s tests -v
2. python3 -m mark2.run check-config
3. python3 -m compileall -q mark2 tests
4. sh -n scripts/run-ai-development.sh
5. systemd-analyze --user verify scheduler/systemd/ai-development.service
   scheduler/systemd/ai-development.timer
6. git diff --check origin/main...HEAD

merge後はtimerを登録し、Issue作成、Issue Review、実装・PR作成、PR Review、
既存branch protectionを経たHuman mergeまでを実task 1件で確認する。1件完走する
までは初期導入完了と扱わない。繰り返し発生する手順や失敗を観測してから、
Skill化やAgent細分化を別Issueで検討する。
