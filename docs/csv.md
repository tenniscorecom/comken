# CSV API

CSV は `CSV` クラスで開き、Excelと同じ `Table` を読み書きします。既定ではすべて文字列として読み、必要な列だけ `types` で変換します。

```python
from comken.toolbox.csv import CSV

with CSV("顧客.csv") as csv:
    table = csv.read()
    rows = [dict(row, 氏名=row["氏名"].strip()) for row in table]
    table.replace(rows)
```

`read_only=True` は読み取り専用です。通常の `with` 終了時に変更を保存し、例外終了、dry-run、読み取り専用では保存しません。途中で確定する場合は `csv.save()` を使います。

CSVを連結する場合は、列名の集合が完全に同じ `Table` 同士だけを `table.concat(other)` で連結します。列の順番は異なっていても構いません。

ヘッダーのない CSV は、`headers` ではなくほかの Table API と同じ `columns` で
列名を指定します。

```python
with CSV("ヘッダーなし.csv", columns=["顧客ID", "氏名"]) as csv:
    table = csv.read()
```

`columns` を省略した CSV は先頭行を列名として扱います。空の見出し、重複する見出し、
見出しとデータ行の列数不一致は、データを黙って補正せず専用例外で停止します。
0バイトまたは UTF-8 BOM だけのファイルも見出しがないため、`CSVHeaderMissingError` で停止します。
