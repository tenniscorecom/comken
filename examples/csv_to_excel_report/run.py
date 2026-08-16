"""
サンプル: CSV を読んで Excel レポートを作る

comken の最初の一歩としてまず動かすサンプル。
CSV の読み込み・絞り込み・集計（CsvReader）と、
Excel レポートの作成・見た目調整（ExcelWriter.create + Sheet）を通しで行う。

実行方法:
    リポジトリのルートで python -m examples.csv_to_excel_report.run

- 入力: このフォルダの data/売上明細.csv（同梱。外部システム・ネット接続は不要）
- 出力: このフォルダの output/売上レポート_YYYYMMDD.xlsx
"""

import logging
from pathlib import Path

from comken.constants import Color
from comken.core.utils.files import DateNameBuilder
from comken.toolbox.csv import CsvReader
from comken.toolbox.excel import ExcelWriter

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
    reader = CsvReader(INPUT_CSV)

    # 全行を辞書のリストで取得する（1行 = 1辞書。キーはヘッダー名、値はすべて str）
    rows = reader.read_rows()
    logger.info("CSV 読み込み: %d 件", len(rows))

    # 条件に一致する行だけ絞り込む
    target_rows = reader.filter("担当者", TARGET_STAFF)
    logger.info("%s の担当分: %d 件", TARGET_STAFF, len(target_rows))

    # 列の値一覧を取り出して集計する（CSV の値は str なので数値にしてから足す）
    total = sum(int(v) for v in reader.column(AMOUNT_COL))
    logger.info("全体の合計金額: %s 円", f"{total:,}")

    # Excel 側で数値として扱いたい列は、書き込む前に int に変換しておく
    # （str のまま書くと Excel 上で「文字列として保存された数値」になり集計できない）
    excel_rows = [{**row, AMOUNT_COL: int(row[AMOUNT_COL])} for row in rows]

    # 「売上レポート_20260713.xlsx」のような日付付きファイル名を組み立てる
    output_path = OUTPUT_FOLDER / DateNameBuilder("売上レポート").suffix()

    with ExcelWriter.create(output_path) as f:
        s = f.sheet(SHEET)
        s.write_table(excel_rows)  # ヘッダー行 + データ行をまとめて書く
        s.append_row(["合計", "", "", "", total])  # 最終行の下に追記

        # 見た目の調整（ヘッダー色付け・合計行の強調・列幅・ヘッダー固定）
        column_count = len(excel_rows[0])
        for col in range(1, column_count + 1):
            s.set_fill(row=HEADER_ROW, col=col, color=Color.LIGHT_BLUE)
        s.set_bold(row=s.last_row, col=1)
        s.set_bold(row=s.last_row, col=column_count)
        s.set_number_format(row=s.last_row, col=column_count, fmt=AMOUNT_FORMAT)
        s.auto_width()
        s.freeze_header()

        f.save()  # save() を呼ぶまでファイルには書き込まれない

    logger.info("レポート出力: %s", output_path)


if __name__ == "__main__":
    # ログの設定は社内の共通ライブラリ側で行う。ここでは logging をそのまま使う
    main()
