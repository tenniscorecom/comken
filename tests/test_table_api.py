"""既存のCSV / Excelクラスを使うTransfer APIのテスト。"""

import logging
from typing import Any

import pytest

from comken.exceptions import (
    DuplicateHeaderCellError,
    TransferDestinationMultipleMatchError,
    TransferDestinationRowMissingError,
    TransferSourceColumnNotFoundError,
)
from comken.exceptions.table import TransferMappingError, TransferRowError
from comken.runtime import debug
from comken.toolbox import Transfer
from comken.toolbox.csv import CSV, CsvReader, CsvWriter
from comken.toolbox.excel import Excel, ExcelTable


def test_transfer_can_filter_edit_and_stop_rows(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    destination_path = tmp_path / "destination.csv"
    source_path.write_text(
        "ID,氏名,区分\n1, 山田 ,対象\n2,佐藤,不要\n3,鈴木,対象\n", encoding="utf-8"
    )
    mapping = {"ID": "番号", "氏名": "名前"}

    def transform(source_row: dict[str, Any], destination_row: dict[str, Any] | None):
        assert destination_row is None
        if source_row["ID"] == "2":
            return Transfer.SKIP
        if source_row["ID"] == "3":
            return Transfer.STOP
        source_row["氏名"] = source_row["氏名"].strip()

    transferred = Transfer(
        CsvReader(source_path),
        CsvWriter(destination_path, fieldnames=list(mapping.values())),
        mapping,
    ).run(transform=transform)

    assert transferred == 1
    assert CsvReader(destination_path).read_rows() == [{"番号": "1", "名前": "山田"}]


def test_transfer_requires_mapping(tmp_path) -> None:
    with pytest.raises(TransferMappingError):
        Transfer(CsvReader(tmp_path / "source.csv"), CsvWriter(tmp_path / "out.csv", []), {})


def test_transfer_rejects_missing_source_column(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("ID\n1\n", encoding="utf-8")
    with pytest.raises(TransferSourceColumnNotFoundError):
        Transfer(
            CsvReader(source_path),
            CsvWriter(tmp_path / "out.csv", ["名前"]),
            {"氏名": "名前"},
        ).run(transform=lambda source, destination: None)


def test_transfer_rejects_invalid_transform_result(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("ID\n1\n", encoding="utf-8")
    with pytest.raises(TransferRowError):
        Transfer(
            CsvReader(source_path),
            CsvWriter(tmp_path / "out.csv", ["ID"]),
            {"ID": "ID"},
        ).run(transform=lambda source, destination: "invalid")  # type: ignore[return-value]


def test_transfer_passes_rows_by_reference_and_writes_destination_change(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    destination_path = tmp_path / "destination.csv"
    source_path.write_text("ID,氏名\n1,山田\n", encoding="utf-8")
    destination_path.write_text("番号,名前\n1,変更前\n", encoding="utf-8")
    received: list[dict[str, Any]] = []

    def transform(source_row: dict[str, Any], destination_row: dict[str, Any] | None) -> None:
        assert destination_row is not None
        destination_row["名前"] = source_row["氏名"]
        received.append(destination_row)

    count = Transfer(
        CsvReader(source_path),
        CsvWriter(destination_path, ["番号", "名前"]),
        {"ID": "番号", "氏名": "名前"},
    ).run(transform=transform)

    assert count == 1
    assert received[0]["名前"] == "山田"
    assert CsvReader(destination_path).read_rows() == [{"番号": "1", "名前": "山田"}]


def test_transfer_explains_type_error_caused_by_missing_destination_row(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("ID\n1\n", encoding="utf-8")

    def transform(source_row: dict[str, Any], destination_row: dict[str, Any] | None) -> None:
        destination_row["番号"] = source_row["ID"]  # type: ignore[index]

    with pytest.raises(TransferDestinationRowMissingError) as exc_info:
        Transfer(
            CsvReader(source_path),
            CsvWriter(tmp_path / "destination.csv", ["番号"]),
            {"ID": "番号"},
        ).run(transform=transform)

    assert "destination_row が None" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, TypeError)


def test_transfer_keeps_unrelated_type_error(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("ID\n1\n", encoding="utf-8")

    def transform(source_row: dict[str, Any], destination_row: dict[str, Any] | None) -> None:
        1 + source_row["ID"]  # type: ignore[operator]

    with pytest.raises(TypeError, match="unsupported operand"):
        Transfer(
            CsvReader(source_path),
            CsvWriter(tmp_path / "destination.csv", ["番号"]),
            {"ID": "番号"},
        ).run(transform=transform)


def test_transfer_rejects_multiple_destination_matches(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    destination_path = tmp_path / "destination.csv"
    source_path.write_text("ID\n1\n", encoding="utf-8")
    destination_path.write_text("番号,名前\n1,山田\n1,佐藤\n", encoding="utf-8")

    with pytest.raises(TransferDestinationMultipleMatchError):
        Transfer(
            CsvReader(source_path),
            CsvWriter(destination_path, ["番号", "名前"]),
            {"ID": "番号"},
        ).run(transform=lambda source_row, destination_row: None)


def test_sheet_rows_ignores_empty_rows_and_styled_trailing_columns(tmp_path) -> None:
    path = tmp_path / "source.xlsx"
    with Excel(path) as book:
        table = book.sheet("data_入力").table()
        table.replace([{"ID": 1, "名前": "山田"}])
        assert table.read() == [{"ID": 1, "名前": "山田"}]


def test_sheet_rows_rejects_duplicate_headers(tmp_path) -> None:
    path = tmp_path / "source.xlsx"
    from openpyxl import Workbook

    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = "data_入力"
    worksheet.append(["ID", "ID"])
    worksheet.append([1, 2])
    workbook.save(path)
    with Excel(path) as book:
        table = book.sheet("data_入力").table()
        with pytest.raises(DuplicateHeaderCellError):
            table.read()


def test_transfer_with_no_matches_writes_csv_header(tmp_path) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("ID\n1\n", encoding="utf-8")
    mapping = {"ID": "番号"}

    count = Transfer(
        CsvReader(source_path),
        CsvWriter(tmp_path / "destination.csv", fieldnames=list(mapping.values())),
        mapping,
    ).run(transform=lambda source, destination: Transfer.SKIP)

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
    if source_kind == "csv":
        source_path.write_text("ID,氏名\n1,山田\n", encoding="utf-8")
        source = CsvReader(source_path)
    else:
        source_excel = Excel(source_path)
        source = source_excel.sheet("data_入力").table()
        source.replace([{"ID": 1, "氏名": "山田"}])

    if destination_kind == "csv":
        destination = CsvWriter(destination_path, fieldnames=list(mapping.values()))
    else:
        destination_excel = Excel(destination_path)
        destination = destination_excel.sheet("data_出力").table()

    count = Transfer(source, destination, mapping).run(
        transform=lambda source_row, destination_row: None
    )
    if source_kind == "excel":
        source_excel.close()
    if destination_kind == "excel":
        destination_excel.close()
    assert count == 1

    if destination_kind == "csv":
        assert CsvReader(destination_path).read_rows() == [{"番号": "1", "名前": "山田"}]
    else:
        with Excel(destination_path) as excel:
            assert excel.sheet("data_出力").table().read() == [
                {"番号": "1" if source_kind == "csv" else 1, "名前": "山田"}
            ]


def test_sheet_reads_rows_as_dicts(tmp_path) -> None:
    with Excel(tmp_path / "data.xlsx") as excel:
        table = excel.sheet("data_入力").table()
        table.replace([{"ID": 1, "氏名": "山田"}])

        assert table.read() == [{"ID": 1, "氏名": "山田"}]
        assert table.count() == 1


def test_transfer_type_aliases_accept_only_csv_or_sheet() -> None:
    from comken.toolbox import table

    assert table.Source == CsvReader | CSV | ExcelTable
    assert table.Destination == CsvWriter | CSV | ExcelTable


def test_transfer_debug_logs_do_not_include_row_data(tmp_path, caplog) -> None:
    source_path = tmp_path / "source.csv"
    source_path.write_text("ID,氏名\n1,秘密の氏名\n", encoding="utf-8")

    with caplog.at_level(logging.DEBUG), debug():
        Transfer(
            CsvReader(source_path),
            CsvWriter(tmp_path / "destination.csv", ["番号"]),
            {"ID": "番号"},
        ).run(transform=lambda source_row, destination_row: None)

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
