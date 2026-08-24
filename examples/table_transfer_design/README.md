# Table / Transfer サンプル

保存先を持たない `Table` と、入力を変更せず新しい `Table` を返す `Transfer` の例です。

```text
python -m examples.table_transfer_design.run
```

`mapping` は「転記元の列名 → 転記先の列名」の dict。
`Transfer(read, write, mapping, read_key=..., write_key=...)` を作り、
3つの取り出し口を使い分けて read / write を行単位で加工する:

- `matched_rows()`: 両方にキーが揃う行を `(read_row, write_row)` で返す
  （**両方とも作業 Table の実体行**）
- `transfer_rows()`: read 全行を `(read_row, write_row | None)` で返す
  （write に無い行は `None`、`read_row` は **コピー**）
- `unmatched()`: 突合しなかった行を `UnmatchedRows` で返す
  - `only_in_read`: write に無い read 行（**コピー** / `Table`）
  - `only_in_write`: read に無い write 行（**作業 Table の実体行** / `list[Row]`）

```python
for read_row, write_row in transfer.matched_rows():
    if 条件:
        continue                          # この行は apply_mapping を呼ばずに終わる
    transfer.apply_mapping(read_row, write_row)   # mapping の値をコピー
    write_row["備考"] = "..."             # mapping に無い列を追加加工

# 転記先に無い read 行は新規行として追加
result = transfer.result()
for read_row in transfer.unmatched().only_in_read:
    result.append({"注文番号": read_row["注文番号"], "顧客名": read_row["取引先"], ...})

# 転記元に無い write 行は「転記元に無し」と印を付けて残す（必要なら後で filter で取り除く）
for write_row in transfer.unmatched().only_in_write:
    write_row["備考"] = "転記元に無し"

# continue した行は備考が空欄のまま残るので、filter で落とす
result = result.filter(lambda row: row["備考"] != "")
```

**条件は `apply_mapping()` より前に書く。** `continue` したかどうかを呼び出し側に
伝える方法がないため、`apply_mapping()` を呼んだ後に判定しても mapping が適用済みになり、filter で取り除くこともできない。
`matched_rows()` は両側に存在する行だけを返し、転記先に無い行は自動で除かれる。
**`continue` した行は作業 Table に残るため、`transfer.result()` の戻り値には
初期値（空欄）のまま含まれる。** 出力から除くには `Table.filter()` などで
別途除く必要がある。

**空キー (`None` / `""`) は突合対象外**。 `0` や `False` は空ではない。
空キーは read 側・write 側のどちらでも照合に使われず、`unmatched()` 側へ流れる。

CSV や Excel へ保存するときは、結果を `CSV.replace()` / `ExcelTable.replace()` へ渡す。
`with` を正常終了した場合だけ自動保存される。
