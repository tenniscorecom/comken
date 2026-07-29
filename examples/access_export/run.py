"""サンプル: Access で整形し、CSV を経由して Excel 帳票を作る。

事前準備:
    Microsoft Access がインストールされた Windows PC で、
    DATABASE_PATH とマクロ名・テーブル名を実際の環境に合わせる。

実行方法:
    リポジトリのルートで python -m examples.access_export.run
"""

from pathlib import Path

from comken.access import AccessDatabase
from comken.csv import CsvReader
from comken.excel import ExcelWriter

DATABASE_PATH = Path(r"C:\作業\顧客.accdb")
CSV_PATH = Path(r"C:\作業\顧客.csv")
REPORT_PATH = Path(r"C:\作業\顧客一覧.xlsx")
MACRO_NAME = "日次整形"
OUTPUT_TABLE = "T_出力"


def main() -> None:
    """Access の整形結果を CSV に出し、Excel 帳票へ転記する。"""
    with AccessDatabase(DATABASE_PATH) as database:
        database.run_macro(MACRO_NAME)
        database.export_csv(OUTPUT_TABLE, CSV_PATH)

    # Access 側で帳票用に絞り込んだ出力を、既存の CSV / Excel API へつなぐ。
    rows = CsvReader(CSV_PATH).rows()
    with ExcelWriter.create(REPORT_PATH) as writer:
        sheet = writer.sheet("Sheet1")
        sheet.write_table(rows)
        sheet.freeze_header()
        sheet.auto_width()
        writer.save()


if __name__ == "__main__":
    main()
