# CSV API

CSV は `CSV` クラスで開き、Excelと同じ `Table` を読み書きします。既定ではすべて文字列として読み、必要な列だけ `types` で変換します。

**読み取り専用でも `with` 必須**。`with` を外れたインスタンスを触ると `TableNotOpenError` で停止する。

```python
from comken.toolbox.csv import CSV

with CSV("顧客.csv") as csv:
    table = csv.read()
    rows = [dict(row, 氏名=row["氏名"].strip()) for row in table]
    table.replace(rows)
```

`read_only=True` は読み取り専用です。通常の `with` 終了時に変更を保存し、例外終了、dry-run、読み取り専用では保存しません。途中で確定する場合は `csv.save()` を使います。

CSVを連結する場合は、列名の集合が完全に同じ `Table` 同士だけを `table.concat(other)` で連結します。列の順番は異なっていても構いません。

## ストリーム読み取り（大量データ）

`read()` はファイル全件をメモリに展開するため、行数が大きい CSV（目安: 1 万行超）では `read_rows()` を使う。1 行ずつ dict で返るので、全件を `list(...)` にまとめなければメモリ消費は 1 行分だけで抑えられる。列名は戻り値の dict からは取れないので、`csv.read().columns` か `columns=[...]` 引数で先に取っておく。

```python
with CSV("big.csv") as csv_file:
    for row in csv_file.read_rows():
        process(row)  # 1 行ずつ処理
```

`read_rows()` も `with` の中でのみ呼べる（`read()` と同じ `_ensure_open` を通る）。

ヘッダーのない CSV は、`headers` ではなくほかの Table API と同じ `columns` で
列名を指定します。

```python
with CSV("ヘッダーなし.csv", columns=["顧客ID", "氏名"]) as csv:
    table = csv.read()
```

`columns` を省略した CSV は先頭行を列名として扱います。空の見出し、重複する見出し、
見出しとデータ行の列数不一致は、データを黙って補正せず専用例外で停止します。
0バイトまたは UTF-8 BOM だけのファイルも見出しがないため、`CSVHeaderMissingError` で停止します。

## 関連

- [README](../README.md) — ライブラリ全体の概要
- [公開 API](自動生成/API.md) — 型ヒント付き署名・引数・戻り値・例外

