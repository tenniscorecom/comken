"""CSV / Excel 共通の表データ API のテスト。"""

import datetime

import pytest

from comken.core import DateFileFinder, DateNameBuilder
from comken.exceptions.table import TableNotOpenError, TransferMappingError
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
        rows = []
        for source_row in transfer.rows():
            if source_row["区分"] == "不要":
                continue
            source_row["氏名"] = source_row["氏名"].strip()
            rows.append(source_row)
        assert transfer.run(rows) == 1

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
