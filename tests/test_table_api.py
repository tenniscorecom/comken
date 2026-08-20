"""既存のCSV / Excelクラスを使うTransfer APIのテスト。"""

import logging
from typing import Any

import pytest
from openpyxl import Workbook
from openpyxl.styles import Font

from comken.exceptions.table import TransferMappingError
from comken.runtime import debug
from comken.toolbox import Transfer
from comken.toolbox.csv import CsvReader, CsvWriter
from comken.toolbox.excel import ExcelReader, ExcelWriter, Sheet


def test_transfer_can_filter_edit_and_stop_rows(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    destination_path = tmp_path / "destination.csv"
    source_path.write_text(
        "ID,氏名,区分\n1, 山田 ,対象\n2,佐藤,不要\n3,鈴木,対象\n", encoding="utf-8"
    )
    mapping = {"ID": "番号", "氏名": "名前"}

    def transform(source_row: dict[str, Any]):
        if source_row["ID"] == "2":
            return None
        if source_row["ID"] == "3":
            return Transfer.STOP
        source_row["氏名"] = source_row["氏名"].strip()
        return source_row

    transferred = Transfer(
        CsvReader(source_path),
        CsvWriter(destination_path, fieldnames=list(mapping.values())),
        mapping,
    ).run(transform)

    assert transferred == 1
    assert CsvReader(destination_path).read_rows() == [{"番号": "1", "名前": "山田"}]


def test_transfer_requires_mapping(tmp_path) -> None:
    with pytest.raises(TransferMappingError):
        Transfer(CsvReader(tmp_path / "source.csv"), CsvWriter(tmp_path / "out.csv", []), {})


def test_transfer_with_no_matches_writes_csv_header(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("ID\n1\n", encoding="utf-8")
    mapping = {"ID": "番号"}

    count = Transfer(
        CsvReader(source_path),
        CsvWriter(tmp_path / "destination.csv", fieldnames=list(mapping.values())),
        mapping,
    ).run(lambda source: None)

    assert count == 0
    assert (tmp_path / "destination.csv").read_text(encoding="utf-8-sig") == "番号\n"


@pytest.mark.parametrize(
    ("source_kind", "destination_kind"),
    [("csv", "csv"), ("csv", "excel"), ("excel", "csv"), ("excel", "excel")],
)
def test_transfer_supports_all_csv_excel_directions(
    tmp_path, source_kind, destination_kind
) -> None:
    mapping = {"ID": "番号", "氏名": "名前"}
    source_path = tmp_path / f"source.{('xlsx' if source_kind == 'excel' else 'csv')}"
    destination_path = (
        tmp_path / f"destination.{('xlsx' if destination_kind == 'excel' else 'csv')}"
    )
    source_book: ExcelWriter | None = None
    destination_book: ExcelWriter | None = None

    if source_kind == "csv":
        source_path.write_text("ID,氏名\n1,山田\n", encoding="utf-8")
        source = CsvReader(source_path)
    else:
        source_book = ExcelWriter.create(source_path, sheet_name="入力")
        source_book.sheet("入力").write_table([{"ID": 1, "氏名": "山田"}])
        source_book.save()
        source_book.close()
        source_book = ExcelWriter(source_path)
        source = source_book.sheet("入力")

    if destination_kind == "csv":
        destination = CsvWriter(destination_path, fieldnames=list(mapping.values()))
    else:
        destination_book = ExcelWriter.create(destination_path, sheet_name="出力")
        destination = destination_book.sheet("出力")

    count = Transfer(source, destination, mapping).run()
    if destination_kind == "excel":
        assert destination_book is not None
        destination_book.save()
    if source_kind == "excel":
        assert source_book is not None
        source_book.close()
    if destination_kind == "excel":
        assert destination_book is not None
        destination_book.close()
    assert count == 1

    if destination_kind == "csv":
        assert CsvReader(destination_path).read_rows() == [{"番号": "1", "名前": "山田"}]
    else:
        with ExcelReader(destination_path) as reader:
            assert reader.read_rows_as_dicts("出力") == [
                {"番号": "1" if source_kind == "csv" else 1, "名前": "山田"}
            ]


def test_sheet_reads_rows_as_dicts() -> None:
    worksheet = Workbook().active
    assert worksheet is not None
    sheet = Sheet(worksheet)
    sheet.write_table([{"ID": 1, "氏名": "山田"}])

    assert sheet.read_rows_as_dicts() == [{"ID": 1, "氏名": "山田"}]
    assert list(sheet.rows()) == [{"ID": 1, "氏名": "山田"}]


def test_sheet_copy_to_copies_entire_sheet(tmp_path) -> None:
    source_path = tmp_path / "source.xlsx"
    destination_path = tmp_path / "destination.xlsx"
    with ExcelWriter.create(source_path, sheet_name="入力") as source_book:
        source = source_book.sheet("入力")
        source["A1"] = "見出し"
        source["A2"] = "=1+1"
        source.ws["A1"].font = Font(bold=True)
        source.ws.column_dimensions["A"].width = 24
        source.ws.row_dimensions[1].height = 30
        source.ws.merge_cells("A1:B1")
        source.ws.freeze_panes = "A2"
        source.ws.auto_filter.ref = "A1:B2"

        with ExcelWriter.create(destination_path, sheet_name="既定") as destination_book:
            copied = source.copy_to(destination_book, "複製")

            assert copied["A1"] == "見出し"
            assert copied["A2"] == "=1+1"
            assert copied.ws["A1"].font.bold is True
            assert copied.ws.column_dimensions["A"].width == 24
            assert copied.ws.row_dimensions[1].height == 30
            assert "A1:B1" in copied.ws.merged_cells
            assert copied.ws.freeze_panes == "A2"
            assert copied.ws.auto_filter.ref == "A1:B2"


def test_transfer_type_aliases_accept_only_csv_or_sheet() -> None:
    from comken.toolbox import table

    assert table.Source == CsvReader | Sheet
    assert table.Destination == CsvWriter | Sheet


def test_transfer_debug_logs_do_not_include_row_data(tmp_path, caplog) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("ID,氏名\n1,秘密の氏名\n", encoding="utf-8")

    with caplog.at_level(logging.DEBUG), debug():
        Transfer(
            CsvReader(source_path),
            CsvWriter(tmp_path / "destination.csv", ["番号"]),
            {"ID": "番号"},
        ).run()

    messages = [record.getMessage() for record in caplog.records]
    assert any("Transfer開始" in message for message in messages)
    assert any("Transfer.run: 開始" in message for message in messages)
    assert any("Transfer.run: 完了" in message for message in messages)
    assert any("取得件数=1 転記対象件数=1" in message for message in messages)
    assert all("秘密の氏名" not in message for message in messages)


def test_new_wrapper_classes_are_not_public() -> None:
    import comken.toolbox as toolbox

    assert toolbox.__all__ == ["Transfer"]
    assert not hasattr(toolbox, "CSV")
    assert not hasattr(toolbox, "Excel")
