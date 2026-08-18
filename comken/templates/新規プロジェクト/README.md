# （プロジェクト名）

（ここを書く：1〜2行でこのツールの説明）

comken（社内共通ライブラリ）を使った業務自動化ツールです。

---

## ドキュメント（読む人で分かれています）

| 読む人 | ファイル |
|---|---|
| 実行する人（毎日使う） | [docs/使い方.md](docs/使い方.md) |
| 保守する人（中身を直す） | [docs/仕様書.md](docs/仕様書.md) |
| エラーが出た人 | [docs/ERRORS.md](docs/ERRORS.md) |

---

## セットアップ（初回だけ）

1. `python main.py` を1度動かす。`config.ini.example` から `config.ini` が作られるので、値を書き換える

comken の場所（`PYTHON_LIBRARY`）は作成時に入っているので、通常は触らなくてよい。
comken を別の場所へ移したときだけ、`認証情報の登録.bat` と `.vscode/settings.json` の**両方**を直す
（前者は実行用、後者は VS Code の補完・定義ジャンプ用。片方だけ直すと、動くのに補完が効かなくなる）。

## 実行

**人が手で動かすとき**は `python main.py` を実行する。

**社内 RPA 基盤から動かすとき**も `python <このフォルダ>\main.py` を直接呼ぶ形になる。
PYTHONPATH は PC 側で通っているので、bat が肩代わりしていた PYTHONPATH の設定は要らない。
RPA 基盤から呼び出すときは `main.py` の末尾のコメント（社内 RPA 基盤から実行する場合）に従って
`main.py` を書き換える。

---

## このひな形の使い方（エンジニア向け・作り終えたら消す）

このフォルダは comken の `templates/新規プロジェクト/` をコピーしたものです。
新規プロジェクトを始めるときの初期構成が入っています。

やること:

1. このフォルダをコピーしてプロジェクト名にリネームし、git 初期化する
2. `src/run.py` の `run()` に処理を書く（`from comken import config` で設定を読む。
   `config.` まで打つと Pylance が補完する。補完用スタブ typings/ は自動生成される。
)
3. `docs/使い方.md` / `docs/仕様書.md` / この README の `（ここを書く）` を埋める
4. `docs/ERRORS.md` の「プロジェクト固有のエラー」に、このツールで起きやすいエラーを追記する
5. この節を README から削除する

コーディング規約は comken リポジトリの `CONVENTIONS.md` に従う。
使える機能の探し方と使うときの約束は comken の `README.md`。
