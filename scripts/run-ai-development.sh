#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=${AI_DEVELOPMENT_REPO:-"$(dirname -- "$script_dir")"}
prompt_file="$repo_dir/.codex/prompts/ai-development-loop.md"

command -v codex >/dev/null 2>&1 || {
    echo "codex command not found" >&2
    exit 127
}
command -v flock >/dev/null 2>&1 || {
    echo "flock command not found" >&2
    exit 127
}
git -C "$repo_dir" rev-parse --is-inside-work-tree >/dev/null
test -f "$prompt_file" || {
    echo "Main Agent prompt not found: $prompt_file" >&2
    exit 66
}

git_dir=$(git -C "$repo_dir" rev-parse --absolute-git-dir)
state_dir="$git_dir/ai-development"
log_dir=${AI_DEVELOPMENT_LOG_DIR:-"$state_dir/logs"}
mkdir -p "$state_dir" "$log_dir"

exec 9>"$state_dir/run.lock"
if ! flock -n 9; then
    echo "AI development loop is already running" >&2
    exit 75
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
log_file="$log_dir/$timestamp.log"

cd "$repo_dir"
codex exec --strict-config -C "$repo_dir" - <"$prompt_file" >>"$log_file" 2>&1
