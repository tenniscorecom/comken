# Excel キー突合転記

`python -m examples.advanced.excel_key_transfer.run` で、CSV をキー検索して Excel へ転記する例を実行する。
CSV と Excel をそれぞれ `Table` として読み、
`destination.transfer_from(source, mapping, read_key=..., write_key=...)` 1 回で突合と転記を行う。
戻り値の `result.table` を Excel へ書く。対応表は `{"顧客名": "取引先"}` のように
「転記元の列名 → 転記先の列名」で書く。

`where=lambda read_row, write_row: ...` で転記する条件を指定する。matched_count /
transferred_count は結果オブジェクトから取得する。