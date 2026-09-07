# Mark1 データフロー解説

## このファイルの目的

この文書は、Mark1 を実際に動かした結果をもとに、プログラムとして何をしているのかをデータフロー中心で説明する。

Mark1 は NumPy だけで実装された最小構成の Decoder-only Transformer 言語モデルである。学習済みの実用モデルではなく、Transformer の内部処理を追うための教育用・実験用プログラムである。

## 実行したコマンド

この環境では `python` ではなく、リポジトリ内の仮想環境を使って実行した。

```bash
.venv/bin/python -m mark1 --prompt "Mark1のtransformer確認" --max-new-tokens 8 --temperature 0 --seed 42
```

実行結果の要点:

```text
input_text        : Mark1のtransformer確認
prompt_token_ids  : [2, 6, 7, 21, 15, 5, 26, 23, 21, 7, 18, 22, 11, 19, 21, 17, 10, 21, 27, 28, 3]
prompt_seq_len    : 21
forward_logits    : [1, 21, 29]
generated_text    : Mark1のtransformer確認oMMooooo
log_file          : logs/run_20260607.jsonl
```

この出力から、入力文字列は 21 個のトークン ID に変換され、最終的に `[1, 21, 29]` の logits が得られていることがわかる。

- `1`: batch size。今回は入力文が 1 件だけ。
- `21`: sequence length。BOS/EOS を含む入力トークン数。
- `29`: vocabulary size。今回のプロンプトと固定コーパスから作られた文字語彙数。

## 対象プログラム

Mark1 の主なプログラムは以下である。

| ファイル | 役割 |
|---|---|
| `mark1/main.py` | CLI の入口。プロンプトを受け取り、トークナイズ、モデル実行、生成、ログ保存を行う。 |
| `mark1/tokenizer.py` | 文字単位 tokenizer。文字列を token id に変換し、token id を文字列へ戻す。 |
| `mark1/model.py` | NumPy Transformer 本体。Embedding、Self-Attention、FFN、LayerNorm、LM Head を実行する。 |
| `mark1/decode.py` | 生成処理。最後の logits から次トークンを選び、逐次的に文章を伸ばす。 |
| `mark1/train_min.py` | 最小学習デモ。Transformer 全体ではなく LM head の bias のみを更新する。 |

## 全体データフロー

Mark1 の推論時の流れは次の通り。

```text
ユーザー入力文字列
  ↓
main.py
  ↓
CharTokenizer.build_vocab()
  ↓
CharTokenizer.encode()
  ↓
prompt_ids: List[int]
  ↓
np.array([prompt_ids])
  ↓
input_ids: [B, T]
  ↓
NumpyTransformerLM.forward()
  ↓
token embedding + positional embedding
  ↓
Transformer layer 0
  ↓
Transformer layer 1
  ↓
LayerNorm
  ↓
LM Head
  ↓
logits: [B, T, V]
  ↓
decode.generate()
  ↓
次トークンを選択
  ↓
generated_ids
  ↓
CharTokenizer.decode()
  ↓
生成テキスト
```

今回の実行では、データ形状は以下のように変化した。

```text
input_ids        : [1, 21]
embedding output : [1, 21, 64]
layer_0 output   : [1, 21, 64]
layer_1 output   : [1, 21, 64]
logits           : [1, 21, 29]
```

## 1. `mark1/main.py`: 実行全体の制御

`mark1/main.py` は Mark1 の入口である。大きくは以下の処理を行う。

```python
args = parser.parse_args()

base_corpus = [
    args.prompt,
    "transformer attention residual layernorm",
    "mark1 numpy implementation",
    "shape tracing is important",
]
tokenizer = CharTokenizer.build_vocab(base_corpus)

prompt_ids = tokenizer.encode(args.prompt, add_bos_eos=True)

cfg = TransformerConfig(...)
model = NumpyTransformerLM(cfg, seed=args.seed)

input_ids = np.array([prompt_ids], dtype=np.int64)
logits, trace = model.forward(input_ids, return_trace=True)

generated_ids = generate(...)
decoded_generated = tokenizer.decode(generated_ids, skip_special_tokens=True)
```

ポイントは、語彙を外部ファイルから読むのではなく、実行時の `base_corpus` から作っている点である。つまり、今回の vocabulary size `29` は、プロンプトと固定文字列に含まれる文字から決まる。

## 2. `mark1/tokenizer.py`: 文字列を token id に変換する

Mark1 の tokenizer は文字単位である。単語単位や BPE ではない。

特殊トークンは以下の 4 つ。

```text
<PAD> = 0
<UNK> = 1
<BOS> = 2
<EOS> = 3
```

`encode()` は、入力文字列の前後に `<BOS>` と `<EOS>` を付ける。

```text
"Mark1のtransformer確認"
  ↓
[<BOS>, M, a, r, k, 1, の, t, r, a, n, s, f, o, r, m, e, r, 確, 認, <EOS>]
  ↓
[2, 6, 7, 21, 15, 5, 26, 23, 21, 7, 18, 22, 11, 19, 21, 17, 10, 21, 27, 28, 3]
```

この結果、sequence length は `21` になる。

## 3. `mark1/model.py`: Transformer 本体

`NumpyTransformerLM.forward()` の入力は `input_ids: [B, T]` である。

今回の実行では:

```text
B = 1
T = 21
D = 64
H = 4
Dh = 16
L = 2
V = 29
```

意味:

- `B`: batch size
- `T`: token 数
- `D`: embedding 次元
- `H`: attention head 数
- `Dh`: 1 head あたりの次元。`D / H`
- `L`: Transformer layer 数
- `V`: 語彙数

### 3.1 Embedding

最初に token id をベクトルへ変換する。

```python
tok = self.token_embedding[input_ids]      # [B, T, D]
pos = self.pos_embedding[:seq_len][None]   # [1, T, D]
x = tok + pos                              # [B, T, D]
```

今回の shape:

```text
input_ids : [1, 21]
tok       : [1, 21, 64]
pos       : [1, 21, 64]
x         : [1, 21, 64]
```

token embedding は「この文字はどんなベクトルか」を表す。positional embedding は「何文字目か」という位置情報を表す。Transformer はそのままだと順序を知らないため、位置情報を足している。

### 3.2 Self-Attention

各 Transformer layer では、まず LayerNorm 後に Q/K/V を作る。

```python
x_ln = self._layer_norm(x, self.cfg.eps)

q = x_ln @ Wq + bq
k = x_ln @ Wk + bk
v = x_ln @ Wv + bv
```

この時点ではすべて `[B, T, D]` である。

次に multi-head attention 用に head を分割する。

```python
q = q.reshape(B, T, H, Dh).transpose(0, 2, 1, 3)
k = k.reshape(B, T, H, Dh).transpose(0, 2, 1, 3)
v = v.reshape(B, T, H, Dh).transpose(0, 2, 1, 3)
```

今回の shape:

```text
q : [1, 4, 21, 16]
k : [1, 4, 21, 16]
v : [1, 4, 21, 16]
```

各 token が、過去のどの token をどれだけ参照するかを計算する。

```python
scores = (q @ k.transpose(0, 1, 3, 2)) / sqrt(Dh)
scores = scores + causal_mask
attn = softmax(scores)
ctx = attn @ v
```

shape:

```text
scores : [1, 4, 21, 21]
attn   : [1, 4, 21, 21]
ctx    : [1, 4, 21, 16]
```

`[21, 21]` は「各 token が、各 token を見る重み」を表す。ただし Decoder-only モデルなので、未来の token を見ないように causal mask を足している。

その後、head を結合して元の `D=64` 次元へ戻す。

```python
ctx = ctx.transpose(0, 2, 1, 3).reshape(B, T, D)
attn_out = ctx @ Wo + bo
x = x + attn_out
```

ここで `x = x + attn_out` は residual connection である。attention の出力を元の入力に足すことで、情報を失いにくくしている。

### 3.3 FFN

Self-Attention の後に FFN を通す。

```python
y = self._layer_norm(x, self.cfg.eps)
ffn = gelu(y @ W1 + b1)
ffn_out = ffn @ W2 + b2
x = x + ffn_out
```

shape:

```text
y       : [1, 21, 64]
ffn     : [1, 21, 128]
ffn_out : [1, 21, 64]
x       : [1, 21, 64]
```

FFN は各 token のベクトルを個別に変換する部分である。Attention が token 間の関係を見るのに対し、FFN は各 token の表現を深く加工する。

### 3.4 Layer を 2 回繰り返す

デフォルト設定では `n_layers=2` なので、上記の Self-Attention + FFN を 2 回繰り返す。

今回の trace:

```text
layer_0 output: [1, 21, 64]
layer_1 output: [1, 21, 64]
```

層を通っても、各 token の hidden size は `64` のままである。

### 3.5 LM Head

最後に LayerNorm を行い、hidden vector を vocabulary size の logits に変換する。

```python
x = self._layer_norm(x, self.cfg.eps)
logits = x @ self.W_vocab + self.b_vocab
```

shape:

```text
x      : [1, 21, 64]
logits : [1, 21, 29]
```

`logits[0, -1]` は「最後の token の次にどの token が来そうか」を表すスコアである。

## 4. `mark1/decode.py`: 次 token を選んで文章を伸ばす

`generate()` は、現在の token 列を model に入れ、最後の位置の logits から次 token を選ぶ。

```python
for _ in range(max_new_tokens):
    input_ids = np.array([token_ids], dtype=np.int64)
    logits, _ = model.forward(input_ids, return_trace=False)
    next_logits = logits[0, -1]
    next_id = _sample_from_logits(next_logits, temperature, rng)
    token_ids.append(next_id)
    if next_id == eos_id:
        break
```

`temperature=0` の場合は greedy decode で、最大スコアの token を選ぶ。

```python
next_id = int(np.argmax(logits))
```

`temperature>0` の場合は softmax 確率に従ってサンプリングする。

今回の生成結果:

```text
generated_ids  : [2, 6, 7, 21, 15, 5, 26, 23, 21, 7, 18, 22, 11, 19, 21, 17, 10, 21, 27, 28, 3, 19, 6, 6, 19, 19, 19, 19, 19]
generated_text : Mark1のtransformer確認oMMooooo
```

注意点として、このモデルは本格的に学習されていない。重みは乱数で初期化されているため、生成される文章に意味があるとは限らない。今回の `oMMooooo` も、学習済み知識による自然な続きではなく、乱数重みのモデルが greedy decode で選んだ token 列である。

## 5. ログ保存

`mark1/main.py` は実行結果を JSONL に追記する。

```python
log_row = {
    "ts": ...,
    "run_id": ...,
    "stage": "transformer_run",
    "input_text": args.prompt,
    "prompt_token_ids": prompt_ids,
    "seq_len": seq_len,
    "forward_logits_shape": list(logits.shape),
    "trace": trace,
    "generated_ids": generated_ids,
    "generated_text": decoded_generated,
}
```

保存先:

```text
logs/run_20260607.jsonl
```

ログには、入力、token id、shape trace、生成結果が残る。後から「どの設定で、どんな shape で、どんな出力になったか」を確認できる。

## 6. 学習デモ `mark1/train_min.py`

`mark1/train_min.py` は本格的な Transformer 学習ではない。教育用に、LM head の bias だけを SGD で更新する。

データフロー:

```text
corpus
  ↓
tokenizer
  ↓
"hello mark1"
  ↓
ids
  ↓
x_ids = ids[:-1]
y_ids = ids[1:]
  ↓
model.forward(x_ids)
  ↓
logits
  ↓
softmax
  ↓
cross entropy loss
  ↓
grad_logits
  ↓
grad_b
  ↓
model.b_vocab を更新
```

つまり、「入力 token から次 token を予測する」という言語モデル学習の形だけを簡略に示している。ただし、Attention や FFN の重みまでは更新していない。

## まとめ

Mark1 が行っている処理は、次の一連の流れである。

1. 入力文字列から文字単位の語彙を作る。
2. 入力文字列を token id に変換する。
3. token id を embedding vector に変換する。
4. 位置情報を足す。
5. causal self-attention で、各 token が過去 token を参照する。
6. FFN で各 token の表現を加工する。
7. 2 層分の Transformer block を通す。
8. LM Head で vocabulary ごとのスコア `logits` を出す。
9. 最後の token の logits から次 token を選ぶ。
10. token を追加し、必要回数だけ生成を繰り返す。
11. token id を文字列へ戻して表示する。
12. 実行結果と shape trace を JSONL に保存する。

Mark1 の重要な価値は、出力文章の品質ではなく、Transformer の内部でデータがどの shape で流れ、どの演算で変化するかを追える点にある。
