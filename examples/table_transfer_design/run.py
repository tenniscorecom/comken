"""サンプル: Transfer の API（matched_rows / unmatched / apply_mapping / result）の使い方。

`Table / Transfer の設計サンプル` として、基本サンプル（`basics/column_mapping.py`）
との違いを示す。 このサンプルでは次の 4 つを取り上げる:

- ``matched_rows()`` の ``for`` ループ内で ``continue`` して、特定条件の行を
  スキップする（旧 API の ``SKIP`` / ``False`` 相当）。``Transfer.result()`` は
  ``continue`` した行も **初期値のまま残った行として含む** ため、最終結果から
  ``Table.filter()`` で取り除く
- ``apply_mapping()`` の **前** に条件を書く（後ろだと ``continue`` しても
  mapping が適用済みになる）
- ``apply_mapping()`` の後に ``write_row["列名"] = ...`` で追加加工する
  （mapping に無い列を計算して埋める）
- ``unmatched().only_in_read`` / ``unmatched().only_in_write`` で、
  read / write どちらかにしか無い行を扱う。 ``result().append()`` で新規行として
  追加、 ``write_row["備考"] = ...`` で破棄予定であることを示す

CSV / Excel への保存は ``with`` ブロックを正常終了した時に行われる。
"""

import logging
from pathlib import Path

from comken import comken_logger
from comken.core.table import Table, Transfer
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel

HERE = Path(__file__).parent
OUTPUT_FOLDER = HERE / "output"
SOURCE_CSV = OUTPUT_FOLDER / "受注.csv"
OUTPUT_PATH = OUTPUT_FOLDER / "請求一覧.xlsx"

logger = logging.getLogger(__name__)


def main() -> None:
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    # 転記元のサンプルデータ（外部入力の代わり）。
    # 4パターンを1回ずつ出すため、read には A001 / A002 / A003 を入れる。
    # - A001: 両側にあり・金額 > 0（通常の転記）
    # - A002: 両側にあり・金額 = 0（continue でスキップ）
    # - A003: read だけ（only_in_read 側で追加）
    with CSV(SOURCE_CSV) as source_csv:
        source_csv.write(
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
    # （apply_mapping の後に write_row["備考"] = ... で計算して埋める）
    source = CSV(SOURCE_CSV, read_only=True, types={"金額": int}).read()
    destination_table = Table(
        ["注文番号", "顧客名", "請求額", "備考"],
        [
            # 通常の転記対象（金額 > 0）
            {"注文番号": "A001", "顧客名": "", "請求額": "", "備考": ""},
            # 両側にあるが金額 = 0 → matched_rows 内で continue され、スキップされる
            {"注文番号": "A002", "顧客名": "", "請求額": "", "備考": ""},
            # read に存在しない行（write だけにある = 破棄候補）
            {"注文番号": "A099", "顧客名": "", "請求額": "", "備考": ""},
        ],
    )

    transfer = Transfer(
        source,
        destination_table,
        mapping=mapping,
        read_key="注文番号",
        write_key="注文番号",
    )
    for read_row, write_row in transfer.matched_rows():
        # 条件は apply_mapping() より前に書く。continue すると apply_mapping を
        # 呼ばずに終わるので、その行は作業 Table に初期値のまま残る。
        if read_row["金額"] <= 0:
            logger.info("スキップ: %s（金額 %s）", read_row["注文番号"], read_row["金額"])
            continue
        # mapping に従い write_row へ値をコピー
        transfer.apply_mapping(read_row, write_row)
        # mapping に無い列は個別に加工する。請求額（税抜）の 10% を消費税として追記
        write_row["備考"] = f"消費税: {int(write_row['請求額']) * 0.1:.0f}"

    # 転記先に無い read 行は新規行として追加する
    result = transfer.result()
    for read_row in transfer.unmatched().only_in_read:
        logger.info("追加: %s", read_row["注文番号"])
        result.append(
            {
                "注文番号": read_row["注文番号"],
                "顧客名": read_row["取引先"],
                "請求額": read_row["金額"],
                "備考": "新規追加",
            }
        )

    # 転記元に無い write 行は「転記元に無し」と書き換える
    for write_row in transfer.unmatched().only_in_write:
        logger.info("転記元に無し: %s", write_row["注文番号"])
        write_row["備考"] = "転記元に無し"

    # matched_rows で continue した行は apply_mapping が呼ばれず、備考が空欄のまま残る。
    # filter で空欄行を落とすと、対象外（備考あり）と新規追加（備考あり）は残る。
    result = result.filter(lambda row: row["備考"] != "")

    with Excel(OUTPUT_PATH) as destination:
        destination.create_data_sheet("請求一覧").create_table("請求一覧", result)

    logger.info("Excel 転記: %s（%d 件）", OUTPUT_PATH, result.count())


if __name__ == "__main__":
    comken_logger.setup_local_logging()
    main()
