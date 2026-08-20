"""CSV / Excel 共通の表データ API のテスト。"""

import datetime
import logging
from typing import Any

import pytest

from comken.core import DateFileFinder, DateNameBuilder
from comken.exceptions.table import TableNotOpenError, TransferMappingError
from comken.runtime import debug
from comken.toolbox import CSV, Excel, Transfer


def test_date_finder_and_builder_share_prefix_rule(tmp_path) -> None:
    assert (
        DateNameBuilder("sales", datetime.date(2026, 8, 20)).prefix("DIY_{:%Y%m%d}_")
        == "DIY_20260820_sales.xlsx"
    )
    path = tmp_path / "DIY_20260820.xlsx"
    path.touch()

    assert DateFileFinder(tmp_path, datetime.date(2026, 8, 20)).prefix("DIY_") == path


def test_transfer_can_filter_and_edit_rows(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    destination_path = tmp_path / "destination.csv"
    source_path.write_text("ID,氏名,区分\n1, 山田 ,対象\n2,佐藤,不要\n", encoding="utf-8")

    with CSV(source_path) as source, CSV(destination_path) as destination:
        transfer = Transfer(source, destination, {"ID": "番号", "氏名": "名前"})

        def transform(source_row: dict[str, Any]) -> dict[str, Any] | None:
            if source_row["区分"] == "不要":
                return None
            source_row["氏名"] = source_row["氏名"].strip()
            return source_row

        assert transfer.run(transform) == 1

    assert list(CSV(destination_path).rows()) == [{"番号": "1", "名前": "山田"}]


def test_excel_rows_are_dicts(tmp_path) -> None:
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel:
        excel.write_rows([{"ID": 1, "氏名": "山田"}])

    with Excel(path) as excel:
        assert list(excel.rows()) == [{"ID": 1, "氏名": "山田"}]


def test_excel_requires_with_statement(tmp_path) -> None:
    with pytest.raises(TableNotOpenError):
        list(Excel(tmp_path / "book.xlsx").rows())


def test_transfer_requires_mapping(tmp_path) -> None:
    with (
        CSV(tmp_path / "source.csv") as source,
        CSV(tmp_path / "destination.csv") as destination,
        pytest.raises(TransferMappingError),
    ):
        Transfer(source, destination, {})


def test_transfer_can_stop_before_remaining_rows(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    destination_path = tmp_path / "destination.csv"
    source_path.write_text("ID\n1\n2\n3\n", encoding="utf-8")

    def transform(source_row: dict[str, Any]):
        if source_row["ID"] == "2":
            return Transfer.STOP
        return source_row

    with CSV(source_path) as source, CSV(destination_path) as destination:
        assert Transfer(source, destination, {"ID": "ID"}).run(transform) == 1

    assert list(CSV(destination_path).rows()) == [{"ID": "1"}]


def test_transfer_with_no_matches_clears_destination(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    destination_path = tmp_path / "destination.csv"
    source_path.write_text("ID\n1\n", encoding="utf-8")
    destination_path.write_text("番号\nold\n", encoding="utf-8")

    with CSV(source_path) as source, CSV(destination_path) as destination:
        assert Transfer(source, destination, {"ID": "番号"}).run(lambda source: None) == 0

    assert destination_path.read_text(encoding="utf-8-sig") == "番号\n"


@pytest.mark.parametrize(
    ("source_kind", "destination_kind"),
    [("csv", "csv"), ("csv", "excel"), ("excel", "csv"), ("excel", "excel")],
)
def test_transfer_supports_all_csv_excel_directions(
    tmp_path, source_kind, destination_kind
) -> None:
    source_suffix = "xlsx" if source_kind == "excel" else "csv"
    destination_suffix = "xlsx" if destination_kind == "excel" else "csv"
    source_path = tmp_path / f"source.{source_suffix}"
    destination_path = tmp_path / f"destination.{destination_suffix}"
    source = CSV(source_path) if source_kind == "csv" else Excel(source_path)
    destination = CSV(destination_path) if destination_kind == "csv" else Excel(destination_path)

    if source_kind == "csv":
        source_path.write_text("ID,氏名\n1,山田\n", encoding="utf-8")
    else:
        with source as source_table:
            source_table.write_rows([{"ID": 1, "氏名": "山田"}])

    with source as source_table, destination as destination_table:
        assert Transfer(source_table, destination_table, {"ID": "番号", "氏名": "名前"}).run() == 1

    with destination as destination_table:
        assert list(destination_table.rows()) == [
            {
                "番号": "1" if destination_kind == "csv" or source_kind == "csv" else 1,
                "名前": "山田",
            }
        ]


def test_transfer_debug_logs_show_progress_without_row_data(tmp_path, caplog) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("ID,氏名\n1,秘密の氏名\n", encoding="utf-8")

    with (
        caplog.at_level(logging.DEBUG),
        debug(),
        CSV(source_path) as source,
        CSV(tmp_path / "destination.csv") as destination,
    ):
        Transfer(source, destination, {"ID": "番号"}).run()

    messages = [record.getMessage() for record in caplog.records]
    assert any("Transfer開始" in message for message in messages)
    assert any("Transfer.run: 開始" in message for message in messages)
    assert any("Transfer.run: 完了" in message for message in messages)
    assert any("取得件数=1 転記対象件数=1" in message for message in messages)
    assert any("Transfer完了" in message for message in messages)
    assert all("秘密の氏名" not in message for message in messages)
