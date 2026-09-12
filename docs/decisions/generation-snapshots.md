# Generation snapshot management

## Decision

- 過去に完成した世代（`mark{n}`）のスナップショットは、`mark{n}/` ディレクトリとしてmainに残さない。完了時点のcommitへのgit tagとGitHub Releaseで管理する。
- mainは常に現在の研究コードだけを表す。
- 世代の中で今も参照・教育価値があるものだけを、意味ベースの場所（`prototypes/`, `docs/reference/` など）に移す。

## 根拠

- 世代が増えるたびに`mark{n}/`が並存すると、mainを読む人が「今どれが現役か」を都度判断する必要が生まれる。tag/Releaseで過去を切り離せば、mainは常に現在の研究コードだけになる。
- 完了した世代の計画・進捗・完了報告は、完了時点の記録として価値があるが、現在の作業には不要。git historyとして残しつつmainから外すことで、両方を満たせる。
- 実装やドキュメントの中には世代を越えて参照される教育的価値があるものもある（例: Transformerの実装解説）。これらは役割ベースの場所に個別に救い出す。

## 適用例

- **Mark1**: 実装は[`prototypes/numpy_transformer/`](../../prototypes/numpy_transformer/)へ、Transformer解説は[`docs/reference/`](../reference/)へ移動。計画・進捗・完了報告は`mark1` tagとそのGitHub Releaseにのみ残す。
