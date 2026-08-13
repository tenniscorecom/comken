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
    # NAS 等の DB は既定でローカルコピーされるため、ネットワーク越しの遅延や破損を避けられる。
    # 整形結果は CSV に出す中間生成物なので、元 DB へ書き戻す必要はない。
    # 元 DB を更新するときは AccessDatabase(DATABASE_PATH, local_copy=False) とする。
    # その場合は、元 DB を開く前に日時付きバックアップが自動作成され、既定で7日間残る。
    with AccessDatabase(DATABASE_PATH) as database:
        database.run_macro(MACRO_NAME)
        database.export_csv(OUTPUT_TABLE, CSV_PATH)

    # Access 側で帳票用に絞り込んだ出力を、既存の CSV / Excel API へつなぐ。
    rows = CsvReader(CSV_PATH).read_rows()
    with ExcelWriter.create(REPORT_PATH) as writer:
        sheet = writer.sheet("Sheet1")
        sheet.write_table(rows)
        sheet.freeze_header()
        sheet.auto_width()
        writer.save()


if __name__ == "__main__":
    main()
