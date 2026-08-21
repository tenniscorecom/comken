# Table / Transfer 設計サンプル

新しい `Table` / `Transfer` API のたたき台です。

このサンプルでは、Excel・CSV の読み書きはまだ扱わず、どちらから読んでも最終的に
同じ `Table` に揃う、というデータ操作部分だけを確認します。

実行方法:

```text
python -m examples.table_transfer_design.run
```

## 使い分け

### データシートを使う処理

```python
source = CSV("顧客.csv").read()
destination = excel.sheet("data_顧客").table()

Transfer(
    source=source,
    destination=destination,
    source_key="顧客ID",
    destination_key="お客様ID",
).run(transform)

excel.save()
```

### XLOOKUPのような単純な結合

```python
joined = source.merge(
    master,
    left_on="顧客ID",
    right_on="お客様ID",
    how="left",
)
```

### 既存帳票へ直接書く処理

既存の表示シートとデータシートが分かれていない場合は、無理にTableへ移さず、
シートのセルへ直接書く処理を残してよい。

```python
report_sheet.write_value("B3", "東京都")
excel.save()
```

## 想定する本体API

```python
source = CSV("顧客.csv").read()
destination = excel.sheet("data_顧客").table()

Transfer(
    source=source,
    destination=destination,
    source_key="顧客ID",
    destination_key="お客様ID",
).run(transform=transform)
```

既存の帳票を直接更新する場合は、Excelテーブルを経由せず、従来どおりセルへ書き込む
処理を別に残す想定です。
