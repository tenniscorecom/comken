# Excel キー突合転記

`python -m examples.excel_key_transfer.run` で、CSV をキー検索して Excel へ転記する例を実行する。
`Transfer(source, destination.sheet("Sheet1"), mapping).run(transform)` を使い、明細の合計を
転記元1件へ追加してから Excel へ書く。対応表は `{"顧客名": "取引先"}` のように
「転記元の列名 → 転記先の列名」で書く。
