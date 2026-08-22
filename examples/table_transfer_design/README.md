# Table / Transfer サンプル

保存先を持たない `Table` と、入力を変更せず新しい `Table` を返す `Transfer` の例です。

```text
python -m examples.table_transfer_design.run
```

`mapping` は転記元列から転記先列への対応です。`transform` には自動 mapping 済みの
作業行が渡り、`SKIP` / `False` ならその行の変更を破棄、`STOP` なら処理を停止します。

CSV や Excel へ保存するときは、結果を `CSV.write()` / `ExcelTable.write()` へ渡します。
`with` が正常終了した場合だけ自動保存されます。
