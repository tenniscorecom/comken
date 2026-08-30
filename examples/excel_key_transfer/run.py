"""
サンプル: CSV を参照して Excel に転記する（XLOOKUP / SUMIF 的転記）

「CSV の値を、Excel の一致する行に流し込む」という定番処理を動かす。
**キーが1件に決まるか、複数行あるか**で使う道具が変わる。そこがこのサンプルの主題。

    注文マスタ（注文番号 → 顧客名）  1対1   index()     → XLOOKUP に相当
    注文明細（注文番号 → 明細が複数） 1対多   group_by()  → SUMIF に相当

実行方法:
    リポジトリのルートで python -m examples.excel_key_transfer.run

実行の流れ（外部システム・ネット接続は不要）:
    1. サンプルデータを output/ に生成する（注文マスタ.csv・注文明細.csv・請求一覧.xlsx）
    2. マスタを index() で引いて、顧客名を転記する
    3. 明細を group_by() でまとめ、合計してから金額を転記する
    4. 転記前後を diff_rows で比較して「どの行のどの列が変わったか」をログに出す
"""

import logging
from pathlib import Path

from comken.core import diff_rows
from comken.core.table import Table, Transfer
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
MASTER_CSV = OUTPUT_FOLDER / "注文マスタ.csv"
DETAIL_CSV = OUTPUT_FOLDER / "注文明細.csv"
INVOICE_XLSX = OUTPUT_FOLDER / "請求一覧.xlsx"

SHEET = "Sheet1"
KEY = "注文番号"
AMOUNT_COL = "C"
AMOUNT = "金額"
TOTAL = "合計金額"
AMOUNT_FORMAT = "#,##0"

# 注文ごとに1行のマスタ（実務では基幹システムから出力した CSV にあたる）
MASTER_ROWS = [
    {"注文番号": "A001", "顧客名": "株式会社アルファ"},
    {"注文番号": "A002", "顧客名": "ベータ商事"},
    {"注文番号": "A003", "顧客名": "ガンマ工業"},
]

# 1つの注文に複数行ぶら下がる明細。A001 は3行あるので index() では引けない
DETAIL_ROWS = [
    {"注文番号": "A001", "商品": "ラケット", "金額": "48000"},
    {"注文番号": "A001", "商品": "ガット", "金額": "12000"},
    {"注文番号": "A001", "商品": "グリップ", "金額": "1500"},
    {"注文番号": "A002", "商品": "シューズ", "金額": "18000"},
    {"注文番号": "A003", "商品": "ボール", "金額": "4500"},
]

logger = logging.getLogger(__name__)


def create_sample_files() -> None:
    """入力になる CSV / Excel を生成する（サンプルを自己完結させるための準備処理）。"""
    with CSV(MASTER_CSV) as csv_file:
        csv_file.replace(Table(list(MASTER_ROWS[0]), MASTER_ROWS))
    with CSV(DETAIL_CSV) as csv_file:
        csv_file.replace(Table(list(DETAIL_ROWS[0]), DETAIL_ROWS))


def total_by_key() -> dict[str, dict[str, int]]:
    """明細をキーごとに合計し、転記元へ追加できる形にする。

    group_by() は {キー: 行のリスト} を返すので、転記に使うには
    {キー: {列名: 値}} へ組み直す。SUMIF を Python で書いているのと同じことをしている。
    """
    with CSV(DETAIL_CSV, read_only=True) as csv_file:
        groups = csv_file.read().group_by(KEY)
    # CSV の値は常に str。Excel 上で数値として集計できるよう int にしてから渡す
    return {
        key: {TOTAL: sum(int(row[AMOUNT]) for row in table.read_rows())}
        for key, table in groups.items()
    }


def main() -> None:
    create_sample_files()

    # ── 1対多の明細: group_by() でまとめてから集計する ────────────────────
    totals = total_by_key()
    logger.info("明細の合計: %s", {key: value[TOTAL] for key, value in totals.items()})

    mapping = {KEY: KEY, "顧客名": "顧客名", TOTAL: TOTAL}
    with CSV(MASTER_CSV, read_only=True) as csv_file:
        source = csv_file.read()
    source = Table(
        [KEY, "顧客名", TOTAL],
        [{**row, **totals.get(row[KEY], {})} for row in source.read_rows()],
    )
    destination = Table(
        [KEY, "顧客名", TOTAL],
        [{KEY: row[KEY], "顧客名": "", TOTAL: ""} for row in source.read_rows()],
    )
    before = destination.read_rows()
    transfer = Transfer(
        source,
        destination,
        mapping=mapping,
        read_key=KEY,
        write_key=KEY,
    )
    for read_row, write_row in transfer.matched_rows():
        # 条件は apply_mapping() より前に書く。 ``read_row[TOTAL]`` を見て
        # 明細が無い行を適用前にスキップする。 この位置で continue した行は
        # transfer の作業 Table へ反映されない（``apply_mapping`` を呼ばないため、
        # write_row への書き込みも起こらない）。
        if read_row[TOTAL] == "":
            # TOTAL が空のマスタは明細がないため、この行は転記しない。
            # write_row の TOTAL は初期値 ``""`` のまま残り、``working`` へも反映されない。
            continue
        # apply_mapping がコンストラクタで渡した mapping を write_row へコピーする
        transfer.apply_mapping(read_row, write_row)
    working = transfer.result()
    after = working.read_rows()
    with Excel(INVOICE_XLSX) as excel:
        sheet = excel.sheet(SHEET)
        values = [working.columns, *[list(row.values()) for row in after]]
        sheet.write_range(f"A1:C{len(values)}", values)
        for row in range(2, len(values) + 1):
            sheet.format(f"{AMOUNT_COL}{row}", number_format=AMOUNT_FORMAT)

    logger.info("%d 件転記した", len(working))

    # 転記前後を突合して、どの行のどの列が書き換わったかを確認する
    result = diff_rows(before, after, key=KEY)
    for change in result.changed:
        logger.info("変更 %s: %s", change.key, change.columns)

    logger.info("転記結果: %s", INVOICE_XLSX)


if __name__ == "__main__":
    # ログの設定は社内の共通ライブラリ側で行う。ここでは logging をそのまま使う
    main()
