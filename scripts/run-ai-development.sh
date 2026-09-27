#!/bin/sh
set -eu

repository=/home/ssm-user/project/AI
lock_file=/tmp/ai-development.lock
result_file=

cleanup() {
    if [ -n "$result_file" ] && [ -f "$result_file" ]; then
        rm -f -- "$result_file"
    fi
}
trap cleanup EXIT HUP INT TERM

exec 9>"$lock_file"
if ! flock -n 9; then
    echo "AI development run is already active; skipping."
    exit 0
fi

cd "$repository"

if [ -n "$(git status --porcelain)" ]; then
    echo "Repository working tree is not clean; refusing to start." >&2
    exit 1
fi

if [ "$(git branch --show-current)" != "main" ]; then
    echo "Repository is not on main; refusing to start." >&2
    exit 1
fi

git fetch --prune origin
set -- $(git rev-list --left-right --count HEAD...origin/main)
ahead=$1
behind=$2
if [ "$ahead" -ne 0 ]; then
    echo "Local main is ahead of or diverged from origin/main; refusing to start." >&2
    exit 1
fi
if [ "$behind" -ne 0 ]; then
    git merge --ff-only origin/main
fi

credential=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill)
github_token=$(printf '%s\n' "$credential" | sed -n 's/^password=//p')
unset credential
if [ -z "$github_token" ]; then
    echo "Git credential helper did not return a GitHub token." >&2
    exit 1
fi
export GH_TOKEN=$github_token
unset github_token

# Installation tokens authenticate as an app installation and cannot call /user.
# Probe the repository endpoint that this workflow actually needs instead.
gh api repos/Bite-8/AI --jq .full_name >/dev/null
codex login status >/dev/null

result_file=$(mktemp /tmp/ai-development-result.XXXXXX)

set +e
codex exec \
    --strict-config \
    --sandbox danger-full-access \
    -c 'approval_policy="never"' \
    -C "$repository" \
    --output-last-message "$result_file" \
    - <<'EOF'
Run one iteration of the AI development Main Agent defined in AGENTS.md.

Inspect the current repository and GitHub state, choose at most one state transition, and use exactly one project custom subagent named `work` or `review` when the routing rules require delegated work. Wait for that subagent and do not perform its development or review work yourself. A direct, mechanical merge retry for an already Human-approved `ai:human-review` PR is the only GitHub mutation the Main Agent may perform without a subagent.

Do not simulate the workflow. Operate on the real repository and GitHub state. End with the required RESULT line and concise summary.

The entry point already supplied a fresh GH_TOKEN. Do not run `gh auth status`, print environment variables, or otherwise display credentials. Verify GitHub access only through the repository queries needed for routing.
EOF
codex_status=$?
set -e

if [ "$codex_status" -ne 0 ]; then
    echo "Codex Main Agent failed with exit code $codex_status." >&2
    exit "$codex_status"
fi

if grep -qx 'RESULT: BLOCKED' "$result_file"; then
    exit 1
fi
if ! grep -Eq '^RESULT: (PROGRESSED|WAITING|NO_WORK)$' "$result_file"; then
    echo "Codex Main Agent did not return the required RESULT status." >&2
    exit 1
fi
