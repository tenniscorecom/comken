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

`read()` と `iter_rows()` のメモリ特性・列名の取得方法・呼び出し条件（`with` 内限定）は
`CSV.read()` / `CSV.iter_rows()` のdocstring（自動生成/API.md）を参照。

```python
with CSV("big.csv") as csv_file:
    for row in csv_file.iter_rows():
        process(row)  # 1 行ずつ処理
```

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

