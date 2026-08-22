"""
サンプル: CSV を読んで Excel レポートを作る

comken の最初の一歩としてまず動かすサンプル。
CSV の読み込み・絞り込み・集計（CSV + Table）と、
Excel レポートの作成・見た目調整（Excel + Sheet）を通しで行う。

実行方法:
    リポジトリのルートで python -m examples.csv_to_excel_report.run

- 入力: このフォルダの data/売上明細.csv（同梱。外部システム・ネット接続は不要）
- 出力: このフォルダの output/売上レポート_YYYYMMDD.xlsx
"""

import logging
from pathlib import Path

from comken.constants import Color
from comken.core import DateNameBuilder
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel

# 入出力はこのフォルダ内で完結させる（サンプル用。実プロジェクトではパスは config.ini に書く）
HERE = Path(__file__).parent
INPUT_CSV = HERE / "data" / "売上明細.csv"
OUTPUT_FOLDER = HERE / "output"

SHEET = "Sheet1"
HEADER_ROW = 1
TARGET_STAFF = "山田"
AMOUNT_COL = "金額"
AMOUNT_FORMAT = "#,##0"  # 3桁区切り表示

logger = logging.getLogger(__name__)


def main() -> None:
    table = CSV(INPUT_CSV).read()

    # 全行を辞書のリストで取得する（1行 = 1辞書。キーはヘッダー名、値はすべて str）
    rows = table.read()
    logger.info("CSV 読み込み: %d 件", len(rows))

    # 条件に一致する行だけ絞り込む
    target_rows = table.filter(lambda row: row["担当者"] == TARGET_STAFF)
    logger.info("%s の担当分: %d 件", TARGET_STAFF, len(target_rows))

    # 列の値一覧を取り出して集計する（CSV の値は str なので数値にしてから足す）
    total = sum(int(v) for v in table.column(AMOUNT_COL))
    logger.info("全体の合計金額: %s 円", f"{total:,}")

    # Excel 側で数値として扱いたい列は、書き込む前に int に変換しておく
    # （str のまま書くと Excel 上で「文字列として保存された数値」になり集計できない）
    excel_rows = [{**row, AMOUNT_COL: int(row[AMOUNT_COL])} for row in rows]

    # 「売上レポート_20260713.xlsx」のような日付付きファイル名を組み立てる
    output_path = OUTPUT_FOLDER / DateNameBuilder("売上レポート").suffix()

    with Excel(output_path) as excel:
        sheet = excel.sheet(SHEET)
        headers = list(excel_rows[0])
        values = [headers, *[[row[header] for header in headers] for row in excel_rows]]
        values.append(["合計", *([""] * (len(headers) - 2)), total])
        sheet.write_range(f"A1:E{len(values)}", values)

        # 見た目の調整（ヘッダー色付け・合計行の強調・列幅・ヘッダー固定）
        column_count = len(excel_rows[0])
        for col in range(1, column_count + 1):
            sheet.set_background(f"{chr(64 + col)}{HEADER_ROW}", Color.LIGHT_BLUE)
        last_row = len(values)
        sheet.format(f"A{last_row}", bold=True)
        sheet.format(f"E{last_row}", bold=True, number_format=AMOUNT_FORMAT)
        sheet.freeze_panes("A2")

    logger.info("レポート出力: %s", output_path)


if __name__ == "__main__":
    # ログの設定は社内の共通ライブラリ側で行う。ここでは logging をそのまま使う
    main()
