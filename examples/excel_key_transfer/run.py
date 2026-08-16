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

from comken.core.utils import diff_rows
from comken.exceptions import CsvRowDuplicateKeyError
from comken.toolbox.csv import CsvReader, CsvWriter
from comken.toolbox.excel import ExcelWriter

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
MASTER_CSV = OUTPUT_FOLDER / "注文マスタ.csv"
DETAIL_CSV = OUTPUT_FOLDER / "注文明細.csv"
INVOICE_XLSX = OUTPUT_FOLDER / "請求一覧.xlsx"

SHEET = "Sheet1"
KEY = "注文番号"
KEY_COL = "A"  # Excel 側でキー（注文番号）が入っている列
CUSTOMER_COL = "B"
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

# マスタにも明細にもない注文番号（転記されずスキップされることを確認する用）
MISSING_KEY = "Z999"

# Excel 側は「注文番号だけ入っていて、顧客名・合計金額が空」という状態を作る
INVOICE_KEYS = ["A001", "A002", "A003", MISSING_KEY]

logger = logging.getLogger(__name__)


def create_sample_files() -> None:
    """入力になる CSV / Excel を生成する（サンプルを自己完結させるための準備処理）。"""
    CsvWriter(MASTER_CSV, fieldnames=list(MASTER_ROWS[0].keys())).write_rows(MASTER_ROWS)
    CsvWriter(DETAIL_CSV, fieldnames=list(DETAIL_ROWS[0].keys())).write_rows(DETAIL_ROWS)

    with ExcelWriter.create(INVOICE_XLSX) as f:
        s = f.sheet(SHEET)
        s.write_table([{"注文番号": key, "顧客名": "", TOTAL: ""} for key in INVOICE_KEYS])
        f.save()


def total_by_key() -> dict[str, dict[str, int]]:
    """明細をキーごとに合計し、transfer_by_letter に渡せる形にする。

    group_by() は {キー: 行のリスト} を返すので、転記に使うには
    {キー: {列名: 値}} へ組み直す。SUMIF を Python で書いているのと同じことをしている。
    """
    groups = CsvReader(DETAIL_CSV).group_by(KEY)
    # CSV の値は常に str。Excel 上で数値として集計できるよう int にしてから渡す
    return {key: {TOTAL: sum(int(row[AMOUNT]) for row in rows)} for key, rows in groups.items()}


def main() -> None:
    create_sample_files()

    # ── 1対1のマスタ: index() でキーから1行を引く ─────────────────────────
    # → {"A001": {"注文番号": "A001", "顧客名": "株式会社アルファ"}, ...}
    customers = CsvReader(MASTER_CSV).index(KEY)

    # ── 1対多の明細: group_by() でまとめてから集計する ────────────────────
    totals = total_by_key()
    logger.info("明細の合計: %s", {key: value[TOTAL] for key, value in totals.items()})

    with ExcelWriter(INVOICE_XLSX) as f:
        before = f.read_rows_as_dicts(SHEET)  # 検証用に転記前の状態を控えておく
        s = f.sheet(SHEET)

        # キー列の値で lookup を引き、一致した行に書き込む。
        # 空行・キーが空の行・lookup にないキーの行は自動でスキップされる
        matched = s.transfer_by_letter(
            key_col=KEY_COL, lookup=customers, mapping={"顧客名": CUSTOMER_COL}
        )
        s.transfer_by_letter(key_col=KEY_COL, lookup=totals, mapping={TOTAL: AMOUNT_COL})

        for row in range(2, s.last_row + 1):
            s.set_number_format(row=row, col=AMOUNT_COL, fmt=AMOUNT_FORMAT)
        s.auto_width()
        f.save()  # 書き込み後は save() を忘れずに

        after = f.read_rows_as_dicts(SHEET)

    logger.info("%d 件転記した（マスタにない %s はスキップ）", matched, MISSING_KEY)

    # 転記前後を突合して、どの行のどの列が書き換わったかを確認する
    result = diff_rows(before, after, key=KEY)
    for change in result.changed:
        logger.info("変更 %s: %s", change.key, change.columns)

    logger.info("転記結果: %s", INVOICE_XLSX)

    _show_why_group_by_is_needed()


def _show_why_group_by_is_needed() -> None:
    """明細に index() を使うとどうなるかを実際に見せる（説明用）。

    黙って後の行で上書きすると、A001 の金額が「最後の1件（グリップ 1500円）」になり、
    合計 61500 円のはずが 1500 円で出てしまう。気づけないので例外で止める。
    """
    try:
        CsvReader(DETAIL_CSV).index(KEY)
    except CsvRowDuplicateKeyError as e:
        logger.info("明細に index() を使うと止まる（想定どおり）: %s", e)


if __name__ == "__main__":
    # ログの設定は社内の共通ライブラリ側で行う。ここでは logging をそのまま使う
    main()
