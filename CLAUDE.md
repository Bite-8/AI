# Claude Code向けリポジトリメモ

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
