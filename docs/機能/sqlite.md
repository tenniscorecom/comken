# SQLite 操作

[README（ドキュメントの入口）へ戻る](../../README.md)

README の「SQLite」から移した、モジュールを使うときの詳しい説明です。

## SQLite

Python 標準の `sqlite3` だけで SQLite を読み書きする薄い API。SQL 文を直接書かずにメソッドを繋いで読み書きできる。
社内で Access の代わりに SQLite を使う場面を想定している。
新しい依存は入れない（SQLAlchemy 等は使わない）。

```python
from comken.toolbox.sqlite import SQLite

db = SQLite(r"C:\作業\顧客.db")                 # ファイルが無ければ ComkenFileNotFoundError
db = SQLite(r"C:\作業\顧客.db", create=True)   # 無ければ作る（dry-run 中は作らない）

print(db.tables())                             # 表の名前の一覧（sqlite_ で始まる内部表は除く）
db.table("顧客").create(columns=["顧客ID", "氏名"], primary_key="顧客ID")

rows = (
    db.table("顧客")
    .where("状態", "=", "有効")
    .where("金額", ">=", 1000)
    .order_by("顧客ID")
    .limit(100)
    .read()                                    # Table を返す（columns を渡せば任意列だけ）
)
print(db.table("顧客").where("状態", "=", "有効").count())   # 件数（int）

db.table("顧客").insert(rows)                  # 追加した件数を返す
n = (
    db.table("顧客")
    .where("顧客ID", "=", "001")
    .update({"状態": "解約"})                  # 更新件数
)
n = (
    db.table("顧客")
    .where("顧客ID", "=", "001")
    .delete()                                  # 削除件数
)
```

`SQLite` インスタンスは `with` 文で包まない。**メソッド単位で接続を開いて閉じる**ため、
読み書きのあとでもファイルをリネーム・削除できる（接続が閉じている）。

## where の演算子

`where(column, op, value)` の `op` は次のいずれか。OR・結合・集計は作らないので、
複雑な絞り込みは読んでから Python 側（pandas や Table の `filter`）でやる。

| 演算子 | 意味 | value の指定 |
|---|---|---|
| `=` | 等しい | 必須 |
| `!=` | 等しくない | 必須 |
| `<`, `<=`, `>`, `>=` | 比較 | 必須 |
| `in` | いずれかと一致 | list / tuple（空は許さない） |
| `not in` | いずれも一致しない | list / tuple（空は許さない） |
| `like` | パターンマッチ（SQL の `LIKE`） | 必須 |
| `is_null` | NULL | **渡さない** |
| `not_null` | NULL でない | **渡さない** |

複数の `where` は AND で結合される。`order_by(column, *, desc=False)` は
複数回で優先順に並ぶ。`limit(n)` は 1 以上。

## クエリの不変性

`db.table("顧客").where(...)` の戻り値は不変。`where` / `order_by` / `limit` は
新しいクエリを返し、元のクエリは変わらない。同じ `base` を使い回しても
`base.read()` と `base.where(...).read()` の結果が混ざることはない。

```python
base = db.table("顧客").where("状態", "=", "有効")
derived_a = base.order_by("顧客ID")            # base は変わらない
derived_b = base.order_by("金額", desc=True).limit(1)
```

## 書き込み

- `insert(rows: Table) -> int` — `Table` の列が表に全部あること。`Table` の値をそのまま渡す（`None` → `NULL`、日付は ISO 文字列）。
- `update(values: dict) -> int` — **where が無いクエリでは送らない**（全件書き換え事故の防止）。`limit` / `order_by` を付けたクエリでも送らない。
- `delete() -> int` — `update` と同じ条件で送る。
- `create(columns, *, types=None, primary_key=None)` — `types` に書いた列だけ `TEXT` / `INTEGER` / `REAL` を付ける。`primary_key` は 1 列だけ。

**書き込みは 1 呼び出し 1 トランザクション**で実行される。途中で失敗したら巻き戻す
（insert で 1000 件中 500 件目が失敗したら 0 件）。

## dry-run

`with comken.dry_run():` の中で呼ぶと、書き込みは実行せずログだけ。
戻り値は `insert` なら渡した件数、`update` / `delete` なら where に当たる件数（`SELECT COUNT(*)` で数える）、`create` は何もしない。
読み込みは dry-run でも普通に読む。

`create=True` でファイル作成するパスも dry-run 中はファイルを作らない。

## 日付の扱い

`datetime.date` / `datetime.datetime` / pandas の `Timestamp` は **ISO 形式の文字列** で保存する。
読むときは文字列のまま返す（自動変換しない）。

## エラー

- **表がない**ときは「表が見つかりません: 名前 / 存在する表: [...]」
- **列がない**ときは「列が見つかりません: 表名.列名 / 存在する列: [...]」
- ファイルがロックされているときは「他の人が使っていないか確認」を添えて `SQLiteError` に包む
- `sqlite3` 由来の例外は `SQLiteError`（`ComkenError` の派生）に包む

## 共有フォルダと SQLite

SQLite は共有フォルダ（ネットワークドライブ）上で **複数人が同時に書くと壊れることがある**
（SQLite 公式の注意）。
**書き込むファイルはローカルか 1 人だけが書く場所に置くこと**。
読取り専用で共有フォルダに置いておき、書き込む作業用ファイルは各自のローカルに持つ運用が無難。

## Access からの移行

Access の `read_table` が返す `Table` をそのまま `create` → `insert` で SQLite に持っていける。

```python
from comken.toolbox.access import AccessDatabase
from comken.toolbox.sqlite import SQLite

with AccessDatabase(r"\\server\share\顧客.accdb") as accdb:
    customers = accdb.read_table("顧客")

with SQLite(r"C:\local\顧客.db", create=True) if False else SQLite(r"C:\local\顧客.db"):
    pass  # with には包まない（SQLite はメソッド単位で開閉する）

db = SQLite(r"C:\local\顧客.db")
db.table("顧客").create(
    columns=list(customers.columns),
    types={c: int for c in customers.columns},  # 例: 数値列を int に
    primary_key="顧客ID",
)
db.table("顧客").insert(customers)
```

## 関連

- [README](../../README.md) — ライブラリ全体の概要
- [公開 API](../自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外