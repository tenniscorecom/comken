# Table / Transfer サンプル

保存先を持たない `Table` と、入力を変更せず新しい `Table` を返す `Transfer` の例です。

```text
python -m examples.table_transfer_design.run
```

`mapping` は「転記元の列名 → 転記先の列名」の dict。
`Transfer(read, write, mapping, read_key=..., write_key=...)` を作り、
次の公式ループで加工する:

```python
for read_row, write_row in transfer.matched_rows():
    if 条件:
        continue                          # この行は apply_mapping を呼ばずに終わる
    transfer.apply_mapping(read_row, write_row)   # mapping の値をコピー
    write_row["備考"] = "..."             # mapping に無い列を追加加工
result = transfer.result().filter(lambda row: row["顧客名"] != "")
# スキップした行は作業 Table に初期値のまま残るため、filter で取り除く
```

**条件は `apply_mapping()` より前に書く。** `continue` したかどうかを呼び出し側に
伝える方法がないため、`apply_mapping()` を呼んだ後に判定しても mapping が適用済みになり、filter で取り除くこともできない。
`matched_rows()` は両側に存在する行だけを返し、転記先に無い行は自動で除かれる。
**`continue` した行は作業 Table に残るため、`transfer.result()` の戻り値には
初期値（空欄）のまま含まれる。** 出力から除くには `Table.filter()` などで
別途除く必要がある。

CSV や Excel へ保存するときは、結果を `CSV.write()` / `ExcelTable.write()` へ渡す。
`with` を正常終了した場合だけ自動保存される。
