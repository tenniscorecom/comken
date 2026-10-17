# Table / transfer() サンプル

保存先を持たない `Table` と、入力を変更せず新しい `Table` を返す `transfer()` の例です。

```text
python -m examples.advanced.table_transfer_design.run
```

`mapping` は「転記元の列名 → 転記先の列名」の dict。
`transfer(read, write, mapping, read_key=..., write_key=...)` を 1 回呼ぶと、
突合・転記・未一致行まで一度に揃った `TransferResult` が返る:

- `result.table` — 転記後の write（write と同じ列・同じ行順・同じ行数の新しい `Table`）。
  入力 `write` は変更しない
- `result.only_in_read` — write に対応が無い read の行（`Table`・read の列構成）
- `result.only_in_write` — read に対応が無い write の行（`Table`・write の列構成・転記前の値）
- `result.matched_count` / `result.transferred_count` — キーが一致した組の数と、
  そのうち `where` が True で実際に転記した組の数

```python skip
result = transfer(
    source, destination, mapping,
    read_key="注文番号", write_key="注文番号",
    where=lambda read_row, write_row: read_row["金額"] > 0,
)
working = result.table

# read にしか無い行は新規行として追加
for read_row in result.only_in_read:
    working.append({"注文番号": read_row["注文番号"], "顧客名": read_row["取引先"], ...})

# write にしか無い行は「転記元に無し」と印を付ける（必要なら後で filter で取り除く）
only_in_write_keys = {row["注文番号"] for row in result.only_in_write}
working = working.replace([
    {**row, "備考": "転記元に無し"}
    if row["注文番号"] in only_in_write_keys else row
    for row in working.to_rows()
])

# 転記後に空の備考が残った行を落とす
working = working.filter(lambda row: row["備考"] != "")
```

`where=` は任意の追加条件 `Callable[[Row, Row], bool]`。`True` のときだけ転記する
（matched だが転記しなかった組は `matched_count` には入るが `transferred_count` に
入らず、`only_in_*` にも入らない）。受け取るのは `Row` のコピー（書き換えても結果に
も入力にも影響しない）。ログ出力は可。

**空キー（`""`。`None` は `Table` に入れた時点で `""` になる）は突合対象外**。
`0` や `False` は空ではない。空キーは read 側・write 側のどちらでも照合に使われず、
`result.only_in_read` / `result.only_in_write` 側へ流れる。

CSV や Excel へ保存するときは、結果を `CSV.replace()` / `ExcelTable.replace()` へ渡す。
`with` を正常終了した場合だけ自動保存される。
