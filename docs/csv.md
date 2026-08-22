# CSV API

CSV は `CSV` クラスで開き、Excelと同じ `Table` を読み書きします。既定ではすべて文字列として読み、必要な列だけ `types` で変換します。

```python
from comken.toolbox.csv import CSV

with CSV("顧客.csv") as csv:
    table = csv.read()
    rows = table.read()
    table.replace(rows)
```

`read_only=True` は読み取り専用です。通常の `with` 終了時に変更を保存し、例外終了、dry-run、読み取り専用では保存しません。途中で確定する場合は `csv.save()` を使います。

CSVを連結する場合は、列名の集合が完全に同じ `Table` 同士だけを `table.concat(other)` で連結します。列の順番は異なっていても構いません。

旧 `CsvReader` / `CsvWriter` は互換用に残っていますが、新しいコードでは `CSV` と `Table` を使ってください。
