# Excel キー突合転記

`python -m examples.excel_key_transfer.run` で、CSV をキー検索して Excel へ転記する例を実行する。
CSV と Excel をそれぞれ `Table` として読み、
`Transfer(read, write, mapping, read_key=..., write_key=...)` を作り、
`matched_rows()` / `transfer_rows()` でループしながら書き換える。
結果は作業 Table に反映されるので、それを Excel へ書く。対応表は `{"顧客名": "取引先"}` のように
「転記元の列名 → 転記先の列名」で書く。

ループは普通の Python の `for` / `if` / `continue` で組み立てる。
`for source, destination in transfer.matched_rows():` のように書く。