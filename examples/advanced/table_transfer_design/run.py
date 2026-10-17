"""サンプル: transfer() の使い分け。

`Table / transfer() の設計サンプル` として、基本サンプル（`examples/column_mapping.py`）
との違いを示す。 このサンプルでは次の 4 つを取り上げる:

- ``where=`` で金額 0 の行の転記を ``False`` にして、ログだけ出す（呼び出し側の
  ループで ``continue`` する必要がない）
- ``result.only_in_read`` の行を ``result.table.append()`` で新規行として追加する
- ``result.only_in_write`` の行に備考（転記元に無し）を付ける
- 最後に ``result.table.filter()`` で備考が空の行（転記されなかった行）を落とす

CSV / Excel への保存は ``with`` ブロックを正常終了した時に行われる。
"""

import logging
from pathlib import Path

from comken import comken_logger
from comken.core.table import Table, transfer
from comken.core.types import Row
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
SOURCE_CSV = OUTPUT_FOLDER / "受注.csv"
OUTPUT_PATH = OUTPUT_FOLDER / "請求一覧.xlsx"

logger = logging.getLogger(__name__)


def is_transferable(read_row: Row, _write_row: Row) -> bool:
    """金額 > 0 の行だけ転記する（それ以外はスキップしてログだけ出す）。"""
    if read_row["金額"] <= 0:
        logger.info("スキップ: %s（金額 %s）", read_row["注文番号"], read_row["金額"])
    return read_row["金額"] > 0


def main() -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    # 毎回まっさらな状態から作るため、前回実行分の出力ブックを消しておく
    # （create_data_sheet() は同名シートが既にあると ExcelError になるため）。
    OUTPUT_PATH.unlink(missing_ok=True)
    # 転記元のサンプルデータ（外部入力の代わり）。
    # 4 パターンを 1 回ずつ出すため、read には A001 / A002 / A003 を入れる。
    # - A001: 両側にあり・金額 > 0（通常の転記）
    # - A002: 両側にあり・金額 = 0（``where`` でスキップ）
    # - A003: read だけ（only_in_read 側で追加）
    with CSV(SOURCE_CSV) as source_csv:
        source_csv.replace(
            Table(
                ["注文番号", "取引先", "金額"],
                [
                    {"注文番号": "A001", "取引先": "株式会社アルファ", "金額": 12000},
                    {"注文番号": "A002", "取引先": "株式会社ブラボー", "金額": 0},
                    {"注文番号": "A003", "取引先": "株式会社チャーリー", "金額": 5000},
                ],
            )
        )

    # mapping は「転記元の列名 → 転記先の列名」の dict
    mapping = {"取引先": "顧客名", "金額": "請求額"}

    # 転記先 Table には、mapping に無い「備考」列も入れておく
    # （転記後に ``replace`` で計算して埋める）。
    with CSV(SOURCE_CSV, read_only=True, types={"金額": int}) as csv_file:
        source = csv_file.read()
    destination_table = Table(
        ["注文番号", "顧客名", "請求額", "備考"],
        [
            # 通常の転記対象（金額 > 0）
            {"注文番号": "A001", "顧客名": "", "請求額": "", "備考": ""},
            # 両側にあるが金額 = 0 → ``where`` でスキップされ、備考が空のまま残る
            {"注文番号": "A002", "顧客名": "", "請求額": "", "備考": ""},
            # read に存在しない行（write だけにある = 「転記元に無し」を付ける）
            {"注文番号": "A099", "顧客名": "", "請求額": "", "備考": ""},
        ],
    )

    # 1 回の呼び出しで突合→転記→結果（table / only_in_read / only_in_write）が揃う。
    # ``where=lambda r, w: ...`` は True のときだけ転記する（matched かつ where=True が
    # transferred_count に入る。A002 は matched だが transferred には入らない）。
    result = transfer(
        source,
        destination_table,
        mapping=mapping,
        read_key="注文番号",
        write_key="注文番号",
        where=is_transferable,
    )

    # ``note_for`` の中で使うため、``only_in_write`` のキーの set を先に作っておく。
    only_in_write_keys = {row["注文番号"] for row in result.only_in_write}

    def note_for(row: Row) -> Row:
        """1 行ごとに転記後の備考を決める。

        - ``only_in_write`` のキー（write 側にしか無い行）は「転記元に無し」
        - 請求額が空でない行は消費税（10%、四捨五入なしの整数）
        - それ以外は元の備考をそのまま返す（``where`` でスキップされた A002 など）
        """
        if row["注文番号"] in only_in_write_keys:
            return {**row, "備考": "転記元に無し"}
        if row["請求額"] != "":
            return {**row, "備考": f"消費税: {int(row['請求額']) * 0.1:.0f}"}
        return row

    working = result.table.replace([note_for(row) for row in result.table])

    # ``only_in_read`` の行は新規行として追加する（read の列名を write の列名に直す）。
    for read_row in result.only_in_read:
        logger.info("追加: %s", read_row["注文番号"])
        working.append(
            {
                "注文番号": read_row["注文番号"],
                "顧客名": read_row["取引先"],
                "請求額": read_row["金額"],
                "備考": "新規追加",
            }
        )

    # where でスキップされた行（備考が空のまま残った A002 など）をここで落とす。
    working = working.filter(lambda row: row["備考"] != "")

    with Excel(OUTPUT_PATH) as destination:
        destination.create_data_sheet("請求一覧").create_table("請求一覧", working)

    logger.info("Excel 転記: %s（%d 件）", OUTPUT_PATH, len(working))


if __name__ == "__main__":
    comken_logger.setup_local_logging()
    main()
