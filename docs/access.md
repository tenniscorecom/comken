# Access 操作

[README（ドキュメントの入口）へ戻る](../README.md)

README の「Access」から移した、モジュールを使うときの詳しい説明です。

## Access

Access がインストールされた Windows PC で、マクロや VBA による整形結果を CSV に出力する。
数十万件では `rows()` の結果をリスト化せず、Python のメモリを使わない `export_csv()` を使う。
既定の文字コードは Excel で開きやすい CP932。`Encoding.UTF8_SIG` も指定できる。
既定では DB を一時フォルダへコピーして開き、終了時にコピーとロックファイルを削除する。
NAS・共有フォルダ・クラウド同期フォルダを直接開かないため、速度・排他・破損リスクを抑えられる。

```python
from comken.toolbox.access import AccessDatabase
from comken.constants import Encoding

with AccessDatabase(r"C:\作業\顧客.accdb") as db:
    db.run_macro("日次整形")  # Access マクロ
    db.run_function("集計処理", "東日本")  # VBA のプロシージャ／関数
    db.run_query("Q_日次更新")  # 保存済みの更新・追加・削除・テーブル作成クエリ
    db.export_csv("T_出力", r"C:\作業\顧客.csv", encoding=Encoding.CP932)

    for row in db.iter_rows("T_出力"):  # Python 側で逐次処理するときだけ
        ...
```

`local_copy=False`（元 DB を直接開く場合）のバックアップ挙動——自動作成のタイミング・
保持期間・`backup_dir` を指定するときの注意点・復旧の手順——は `AccessDatabase`
クラスのdocstring（自動生成/API.md）を参照。

`table_names()` で利用可能なテーブルと保存済みクエリを確認できる。外部に影響する
マクロ・VBA・CSV 出力は `dry_run()` 中には実行されない。

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
