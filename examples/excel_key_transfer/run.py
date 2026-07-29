"""
サンプル: キー突合転記（XLOOKUP 的転記）

「マスタ CSV の値を、Excel の一致する行に流し込む」という定番処理を動かす。
Excel 関数の VLOOKUP / XLOOKUP でやっている作業を transfer_by_key に置き換えるイメージ。

実行方法:
    リポジトリのルートで python -m examples.excel_key_transfer.run

実行の流れ（外部システム・ネット接続は不要）:
    1. サンプルデータを output/ に生成する（注文マスタ.csv と 請求一覧.xlsx）
    2. マスタ CSV をキー列（注文番号）でインデックス化する（CsvReader.index）
    3. Excel の注文番号と突合して、顧客名・金額を転記する（transfer_by_key）
    4. 転記前後を diff_rows で比較して「どの行のどの列が変わったか」をログに出す
"""

import logging
from pathlib import Path

from comken.csv import CsvReader, CsvWriter
from comken.excel import ExcelWriter
from comken.utils import diff_rows

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
MASTER_CSV = OUTPUT_FOLDER / "注文マスタ.csv"
INVOICE_XLSX = OUTPUT_FOLDER / "請求一覧.xlsx"

SHEET = "Sheet1"
KEY = "注文番号"
KEY_COL = "A"  # Excel 側でキー（注文番号）が入っている列
MAPPING = {"B": "顧客名", "C": "金額"}  # Excel の列レター → マスタ CSV の列名

# サンプル用のマスタデータ（実務では基幹システムから出力した CSV などにあたる）
MASTER_ROWS = [
    {"注文番号": "A001", "顧客名": "株式会社アルファ", "金額": "120000"},
    {"注文番号": "A002", "顧客名": "ベータ商事", "金額": "80000"},
    {"注文番号": "A003", "顧客名": "ガンマ工業", "金額": "45000"},
]

# マスタに存在しない注文番号（転記されずスキップされることを確認する用）
MISSING_KEY = "Z999"

# Excel 側は「注文番号だけ入っていて、顧客名・金額が空」という状態を作る
INVOICE_KEYS = ["A001", "A002", "A003", MISSING_KEY]

logger = logging.getLogger(__name__)


def create_sample_files() -> None:
    """入力になる CSV / Excel を生成する（サンプルを自己完結させるための準備処理）。"""
    CsvWriter(MASTER_CSV, fieldnames=list(MASTER_ROWS[0].keys())).write_rows(MASTER_ROWS)

    with ExcelWriter.create(INVOICE_XLSX) as f:
        s = f.sheet(SHEET)
        s.write_table([{"注文番号": key, "顧客名": "", "金額": ""} for key in INVOICE_KEYS])
        f.save()


def main() -> None:
    create_sample_files()

    # キー列でインデックス化する
    # → {"A001": {"注文番号": "A001", "顧客名": "株式会社アルファ", "金額": "120000"}, ...}
    lookup = CsvReader(MASTER_CSV).index(KEY)

    with ExcelWriter(INVOICE_XLSX) as f:
        before = f.read_rows_as_dicts(SHEET)  # 検証用に転記前の状態を控えておく

        # キー列の値で lookup を引き、一致した行に MAPPING に従って書き込む。
        # 空行・キーが空の行・lookup にないキーの行は自動でスキップされる
        matched = f.transfer_by_key(SHEET, key_col=KEY_COL, lookup=lookup, column_mapping=MAPPING)
        f.save()  # 書き込み後は save() を忘れずに

        after = f.read_rows_as_dicts(SHEET)

    logger.info("%d 件転記した（マスタにない %s はスキップ）", matched, MISSING_KEY)

    # 転記前後を突合して、どの行のどの列が書き換わったかを確認する
    result = diff_rows(before, after, key=KEY)
    for change in result.changed:
        logger.info("変更 %s: %s", change.key, change.columns)

    logger.info("転記結果: %s", INVOICE_XLSX)


if __name__ == "__main__":
    # ログの設定は社内の共通ライブラリ側で行う。ここでは logging をそのまま使う
    main()
