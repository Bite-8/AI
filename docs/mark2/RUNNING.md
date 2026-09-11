# Mark2 初回推論の実行手順

状態: 推論コードと記録処理を実装済み。現EC2で設定・記録・失敗処理を検証済み。公開重みの読込、CUDA推論、固定した依存関係の組合せはGPU実機で未検証。

## 現在のEC2でできる確認

追加パッケージや重みの取得なしで実行できる。

```sh
python3 -m mark2.run --check-config
python3 -m unittest discover -s tests -v
```

`--check-config` はJSONの構造・固定revision・入力数・生成上限を検査する。tokenizerによる入力長の検査は本実行時に行う。

## GPU環境の準備

想定はLinux / NVIDIA L4 / BF16対応、Python 3.12。現在のt2.micro上で以下のインストールや推論を行う前提ではない。CUDA対応ドライバのある実験機でリポジトリを取得し、そのルートで実行する。EC2の新設・変更を行うコマンドは含まない。

```sh
python3 --version
nvidia-smi
python3 -m venv .venv-mark2
. .venv-mark2/bin/activate
python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r mark2/requirements.txt
python -m pip check
python -c 'import torch; from transformers import Qwen3_5ForCausalLM; print(torch.__version__, torch.version.cuda, torch.cuda.is_available()); print(torch.cuda.get_device_name(0), torch.cuda.is_bf16_supported())'
```

PyTorchのCUDA 12.8配布指定は[公式インストール例](https://pytorch.org/get-started/previous-versions/)に基づく。ドライバとの互換性は上のGPU検査で確認する。Pythonの版が異なる場合も結果へ記録する。主要依存は固定しているが、推移的依存を含む完全なlockではない。実行機で `pip freeze` を保存し、初回成功後にその環境を再現基準にする。既存の別用途の仮想環境を流用しない。

## 実行

```sh
mkdir -p logs/mark2
python -m pip freeze > logs/mark2/installed-requirements.txt
python -m mark2.run
```

出力先を変える場合:

```sh
python -m mark2.run --output-root logs/mark2/trials
```

初回は重みをHugging Faceの標準キャッシュへ取得する。保存場所を変える場合は実験機で `HF_HOME` を専用の保存先に設定する。モデルとtokenizerは設定ファイルの同じcommit SHAを指定する。モデルのリモートPythonコードは実行しない。

実装は[公式のtext-only経路](https://huggingface.co/docs/transformers/v5.13.0/model_doc/qwen3_5)の `Qwen3_5ForCausalLM` を使う。学習済みテキスト部分を無変更で読み込み、vision towerは構築しない。モデルの全モダリティを検証する実験ではない。チェックポイントのmissing/mismatched keysがある場合は停止して記録する。

初回は高速化用の追加カーネルを導入せず、Attentionはeagerを明示する。Gated DeltaNetはインストール環境に応じた参照実装等を使うため、依存一覧も保存する。この実行速度をモデルの最高速度とは扱わない。

## 実行条件と保存されるもの

設定: `mark2/configs/qwen35_smoke.json`。固定入力3件を各2回、batch 1、入力上限512、生成上限128トークン。thinkingは無効、greedy生成、seed 42、量子化なしのBF16。上限超過の入力は切り捨てずエラーにする。各試行のキャッシュは独立させる。

毎回 `logs/mark2/<時刻>-<ID>/` を新設する。

| ファイル | 内容 |
|---|---|
| config.json | 入力文を含む実験条件とモデルrevision |
| manifest.json | 成否、環境、依存版、コード版、sourceハッシュ、読込時間、失敗理由 |
| source/ | 実行したrun.py、environment.py、requirements.txtのコピー |
| loading_info.json | チェックポイントの読込結果 |
| model_config.json / generation_config.json | 実際に使用した設定 |
| chat_template.txt | 実際の入力テンプレート |
| results.jsonl | 試行ごとの入出力・トークンID・時間・GPUピークメモリ・初回出力との一致 |

生成時間はGPU同期を入れたprefill＋decodeの時間。tokenizer処理やモデル読込は含めない。初回はウォームアップなしなので、初回と後続の値を混ぜて平均しない。tokens/secは生成トークン数をこの時間で割った値であり、decode単独の速度ではない。GPUメモリはPyTorchのallocated/reservedで、ホストRAMやデバイス全体の使用量ではない。

終了理由はEOS、生成上限、その他を分ける。固定seedでも環境をまたぐ出力一致は保証しない。エラーやCtrl-C時は終了コード1とfailed記録を残し、書込済みの試行を保持する。強制終了・マシン停止ではmanifestがrunningのまま残る場合があり、その場合は未完了として扱う。

## 終了と次の確認

本コマンドにEC2の停止機能はない。プロセス終了後もインスタンス料金は継続する。初回の実験機では起動時間2時間を目安の上限とし、結果を回収してAWS上の停止を確認する。自動停止の設定は未実施。

初回成功後は、manifest、6試行の結果、GPU情報、実費を確認する。これは実行基盤の疎通確認で、品質改善を示すベンチマークではない。その後に内部データフローの追跡と研究用評価を追加する。

## 検証済み範囲

2026-09-08、Python 3.14.4 / t2.microで以下を確認した。

- 標準ライブラリのみで設定検査が成功する。
- 依存未導入で本実行すると、重み取得前に終了コード1とfailed manifestを残す。
- unittestで固定revision、入力上限、重複ID、EOS判定、失敗時の部分結果保持、出力先の分離、設定検査の独立性を確認した。

テスト内の推論部分は置換している。実モデルのAPI互換性・チェックポイント読込・生成品質・CUDA測定は、これらのテストでは検証していない。
