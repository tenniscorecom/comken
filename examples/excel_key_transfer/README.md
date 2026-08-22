# Excel キー突合転記

`python -m examples.excel_key_transfer.run` で、CSV をキー検索して Excel へ転記する例を実行する。
CSV と Excel をそれぞれ `Table` として読み、
`Transfer(read, write, mapping, read_key=..., write_key=...).run(transform=...)` を使う。
結果は入力とは別の新しい `Table` なので、それを Excel へ書く。対応表は `{"顧客名": "取引先"}` のように
「転記元の列名 → 転記先の列名」で書く。

`transform` は任意で、指定した場合は mapping 適用後の作業行を追加加工できる。
