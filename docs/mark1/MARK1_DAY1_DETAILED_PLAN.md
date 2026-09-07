# MARK1 Day1 詳細実行プラン（環境準備 + I/O設計）

## 0. 目的（Day1のゴール）
Day1は、以降の実装で迷わないために「実装の土台」を固定する日です。  
この日に **入力→token id→出力text** の最小経路と、**shape追跡ログの仕様** を確定させます。

**Day1完了条件**
- CLIで `--prompt` を受け取り、tokenize結果を出力できる
- token id列をdecodeして元テキストに戻せる（完全一致または仕様通り）
- JSONLログが1実行1行以上出る
- ログに最低限のshape/長さ情報を残せる

---

## 1. スコープ（Day1でやる / やらない）

### やること
1. Python + NumPyの最小環境を準備
2. ディレクトリ構成の雛形作成
3. tokenizerの試作（文字ベースで可）
4. CLI入口 `mark1/main.py` の最小実装
5. JSONLログ仕様の確定と出力実装
6. 動作確認用の最小テスト（手動コマンドベース）

### やらないこと
- Attention本実装（Day2）
- Multi-head/FFN実装（Day3）
- 学習ループ（Day5）

---

## 2. 期待アウトプット（成果物）
- `mark1/main.py`（CLI入口）
- `mark1/tokenizer.py`（encode/decode）
- `logs/` ディレクトリ + JSONLログ出力
- `README_day1.md` または本書に準ずる運用メモ

---

## 3. 推奨ディレクトリ構成（Day1時点）
```text
project_root/
  mark1/
    main.py
    tokenizer.py
    decode.py         # Day4で実装、先に空ファイルでも可
    model.py          # Day3で実装、先に空ファイルでも可
    train_min.py      # Day5で実装、任意
  logs/
    run_YYYYMMDD.jsonl
  data/
    sample_corpus.txt # 任意（tokenizer検証用）
```

---

## 4. 実行手順（タイムボックス）

### Task 1: 環境準備（目安 45分）
- Pythonバージョン確認
- 仮想環境作成
- NumPy導入
- 実行確認

**チェックコマンド例**
```bash
python --version
python -m venv .venv
source .venv/bin/activate
pip install numpy
python -c "import numpy as np; print(np.__version__)"
```

**完了判定**
- NumPy import成功
- 依存ライブラリを最小に保てている

---

### Task 2: I/O仕様の固定（目安 60分）
以下を先に決め、後続実装のブレを防ぐ。

1. **入力仕様**
   - CLI引数 `--prompt` で1文を受ける
   - 文字コードはUTF-8

2. **内部表現仕様**
   - `tokens: List[str]`
   - `token_ids: List[int]`
   - バッチ化前の基本shapeを `seq_len` として扱う

3. **出力仕様**
   - 標準出力: 入力、token列、id列、復元テキスト
   - ログ出力: JSONL 1行/ステップ

**完了判定**
- 仕様を文章で明文化済み
- main/tokenizerで同じ用語を使用

---

### Task 3: tokenizer試作（目安 90分）
初日は理解優先のため、まずは文字単位tokenizerで実装。

**必要関数（最小）**
- `build_vocab(texts)`
- `encode(text)`
- `decode(token_ids)`

**設計ポイント**
- `PAD`, `UNK`, `BOS`, `EOS` など特殊トークンの有無を先に決める
- 未知文字の扱い（UNKへのフォールバック）を明記
- reversible（可能な限りdecodeで戻る）を優先

**完了判定**
- encode/decode往復が成立
- 短文3例で想定どおりの挙動を確認

---

### Task 4: ログ仕様策定と実装（目安 60分）
Day2以降でshape追跡できるよう、Day1でログを固定する。

**JSONLフォーマット例**
```json
{
  "ts": "2026-04-06T10:00:00Z",
  "run_id": "day1_trial_001",
  "stage": "tokenize",
  "input_text": "hello",
  "seq_len": 5,
  "token_count": 5,
  "token_ids": [12, 4, 7, 7, 9],
  "notes": "char-level tokenizer"
}
```

**最低限残す項目**
- `ts`, `run_id`, `stage`
- `seq_len` / `token_count`
- `token_ids`（長すぎる場合は先頭N件）

**完了判定**
- 1回のCLI実行でログが追記される
- JSONとしてパース可能

---

### Task 5: CLI雛形実装と疎通確認（目安 45分）
`python -m mark1 --prompt "テスト"` で一連の流れが通ることを確認。

**CLIの最小要件**
- 引数未指定時にヘルプ表示
- `--prompt` を受け取りtokenize実行
- encode結果とdecode結果を表示
- ログを1行追加

**完了判定**
- エラーなく実行完了
- 標準出力とログが整合

---

## 5. Day1受け入れチェックリスト
- [ ] `.venv` + NumPy環境が用意できた
- [ ] `mark1/main.py` から `mark1/tokenizer.py` を呼び出せる
- [ ] encode/decodeが最低3ケースで動作
- [ ] JSONLログを保存できる
- [ ] 用語（token/token_id/seq_len）が文書とコードで一致

---

## 6. 想定リスクと回避策
1. **tokenizer仕様を凝りすぎる**
   - 回避: Day1は文字単位で固定、BPEは14日版検討に回す

2. **ログ項目が未確定で後工程が混乱**
   - 回避: `stage` と `seq_len` を必須化

3. **CLIの入出力仕様が毎日変わる**
   - 回避: Day1終了時に引数名と出力フォーマットを凍結

---

## 7. Day2への引き継ぎ項目
- tokenizer出力（token_ids）をAttention入力shapeにどう載せるか
- ログに `stage=attention` を追加する拡張方針
- 因果マスク適用時のshape記録ルール（`[seq, seq]` など）

---

## 8. 1日終了時の報告テンプレート（コピペ用）
```md
# Day1 Report
- 実施日:
- 実装内容:
  - 環境構築:
  - tokenizer:
  - CLI:
  - ログ:
- 動作確認コマンド:
- 結果:
- 課題:
- Day2へ持ち越し:
```
