# Excel キー突合転記

`python -m examples.excel_key_transfer.run` で、CSV をキー検索して Excel へ転記する例を実行する。
この例は列位置が固定された帳票なので `transfer_by_letter()` を使い、対応表は
`{"顧客名": "B"}` のように「転記元の列名 → 転記先の列記号」で書く。

ヘッダー行があり列名で指定できる帳票では `transfer_by_mapping()` を使う。こちらも
`{"顧客名": "取引先"}` のように、対応表の向きは「転記元 → 転記先」で共通である。
