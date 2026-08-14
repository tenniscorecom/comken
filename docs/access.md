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

    for row in db.read_rows("T_出力"):  # Python 側で逐次処理するときだけ
        ...
```

コピー上の変更は元 DB に反映されない。元 DB を更新するマクロや VBA を実行する場合だけ、
`AccessDatabase(path, local_copy=False)` を指定して元ファイルを直接開く。この場合は開く前に
元 DB と同じフォルダの `backup/` へ、`20260729_153045_顧客.accdb` のような
日時付きバックアップを自動作成する。バックアップは既定で7日間残り、同じ DB の期限切れ分だけが
次回バックアップ時に削除される。保持期間は `backup_days`、作成の停止は `backup=False` で指定できる。
数百 MB の DB をネットワーク越しにコピーすると時間がかかる。巨大な DB では `backup_dir` に
ローカルフォルダを指定できるが、顧客情報がローカルに残ることを理解したうえで選ぶ。

バックアップは処理成功後も残り、自動では書き戻されない。復旧が必要な場合は元 DB の利用を止め、
残すべき現行ファイルを退避したうえで、ログに記録されたバックアップを人が手でコピーする。
元 DB と同じ場所なので、サーバー障害や誤削除では控えも一緒に失われる。書き込み中の切断による
DB 破損からの復旧用であり、本格的な世代保全はサーバー側のバックアップに依存する。
OneDrive などの同期フォルダでは控えも同期され、容量と帯域を消費する。

`table_names()` で利用可能なテーブルと保存済みクエリを確認できる。外部に影響する
マクロ・VBA・CSV 出力は `dry_run()` 中には実行されない。

---

## 関連

- [README](../README.md) — ライブラリ全体の概要と環境構築
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外
