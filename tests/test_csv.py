"""CSV API の読み書き・保留・失敗時保護の契約を確認する。"""

from unittest.mock import patch

import pytest

from comken.constants import Encoding
from comken.core import Table
from comken.exceptions import (
    CsvColumnsRequiredError,
    CsvFileNotFoundError,
    CsvHeaderMissingError,
    CsvInvalidHeaderError,
    CsvRowLengthError,
    EncodingDetectionError,
    InvalidTableOperationError,
    TableRowColumnsError,
    TableTypeConversionError,
    UnsupportedFileSuffixError,
)
from comken.toolbox import csv as csv_package
from comken.toolbox.csv import CSV


class TestCSV:
    def test_public_api_contains_only_csv(self) -> None:
        assert csv_package.__all__ == ["CSV"]
        for removed in ("Csv" + "Reader", "Csv" + "Writer", "Csv" + "Base", "index" + "_files"):
            assert not hasattr(csv_package, removed)

    def test_reads_strings_by_default_and_only_converts_requested_columns(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,山田\n", encoding="utf-8-sig")
        assert CSV(path).read().read() == [{"id": "1", "name": "山田"}]
        assert CSV(path, types={"id": int}).read().read() == [{"id": 1, "name": "山田"}]

    def test_auto_reads_cp932(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("名前\n山田\n", encoding="cp932")
        assert CSV(path, encoding=Encoding.AUTO).read().column("名前") == ["山田"]

    def test_columns_treats_first_row_as_data(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("A001,1000\n", encoding="utf-8-sig")
        table = CSV(path, columns=["注文番号", "金額"]).read()
        assert table.read() == [{"注文番号": "A001", "金額": "1000"}]

    def test_append_is_saved_only_on_normal_with_exit(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id\n1\n", encoding="utf-8-sig")
        with pytest.raises(RuntimeError), CSV(path) as csv_file:
            csv_file.append({"id": "2"})
            raise RuntimeError
        assert CSV(path).read().column("id") == ["1"]
        with CSV(path) as csv_file:
            csv_file.append({"id": "2"})
        assert CSV(path).read().column("id") == ["1", "2"]

    def test_replace_accepts_table(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        with CSV(path) as csv_file:
            csv_file.replace(Table(["id"], [{"id": "1"}]))
        assert CSV(path).read().read() == [{"id": "1"}]

    def test_rejects_non_csv_suffix(self, tmp_path) -> None:
        with pytest.raises(UnsupportedFileSuffixError):
            CSV(tmp_path / "data.txt")

    def test_auto_reads_utf8_bom_without_bom_in_header(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,山田\n", encoding="utf-8-sig")
        assert CSV(path, encoding=Encoding.AUTO).read().read() == [{"id": "1", "name": "山田"}]

    def test_auto_rejects_unknown_encoding_with_csv_exception(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_bytes(b"\x81\x20\x81\x20")
        with pytest.raises(EncodingDetectionError):
            CSV(path, encoding=Encoding.AUTO).read()

    def test_headerless_rejects_rows_with_too_many_columns(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("A001,1000,山田\n", encoding="utf-8-sig")
        with pytest.raises(CsvRowLengthError, match="1行目"):
            CSV(path, columns=["id", "amount"]).read()

    def test_read_only_rejects_replace_and_does_not_save(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id\nold\n", encoding="utf-8-sig")
        with pytest.raises(InvalidTableOperationError), CSV(path, read_only=True) as csv_file:
            csv_file.replace([{"id": "new"}])
        assert CSV(path).read().column("id") == ["old"]

    def test_dry_run_does_not_save(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id\nold\n", encoding="utf-8-sig")
        with CSV(path, dry_run=True) as csv_file:
            csv_file.replace([{"id": "new"}])
            assert csv_file.read().column("id") == ["new"]
            csv_file.save()
        assert CSV(path).read().column("id") == ["old"]

    def test_pending_read_is_visible_before_save(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        with CSV(path) as csv_file:
            csv_file.replace([{"id": "1"}])
            assert csv_file.read().read() == [{"id": "1"}]
            assert not path.exists()

    def test_append_requires_matching_columns(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,A\n", encoding="utf-8-sig")
        with pytest.raises(TableRowColumnsError), CSV(path) as csv_file:
            csv_file.append({"id": "2"})

    def test_append_table_requires_matching_columns(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id\n1\n", encoding="utf-8-sig")
        with pytest.raises(TableRowColumnsError), CSV(path) as csv_file:
            csv_file.append(Table(["name"], [{"name": "A"}]))

    def test_save_writes_header_and_creates_parent(self, tmp_path) -> None:
        path = tmp_path / "nested" / "data.csv"
        with CSV(path) as csv_file:
            csv_file.replace([{"id": "1"}])
            csv_file.save()
        assert path.read_text(encoding="utf-8-sig") == "id\n1\n"

    def test_types_only_convert_declared_columns(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id,amount\n001,2\n", encoding="utf-8-sig")
        table = CSV(path, types={"amount": int}).read()
        assert table.read() == [{"id": "001", "amount": 2}]

    def test_type_conversion_error_reports_row_and_column(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id,amount\n1,invalid\n", encoding="utf-8-sig")
        with pytest.raises(TableTypeConversionError, match="1件目、列「amount」"):
            CSV(path, types={"amount": int}).read()

    def test_write_failure_preserves_existing_file(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        original = "id\nold\n"
        path.write_text(original, encoding="utf-8-sig")
        with (
            patch("csv.DictWriter.writerows", side_effect=OSError("write failed")),
            pytest.raises(OSError, match="write failed"),
            CSV(path) as csv_file,
        ):
            csv_file.replace([{"id": "new"}])
            csv_file.save()
        assert path.read_text(encoding="utf-8-sig") == original

    @pytest.mark.parametrize("text", ["id,\n1,A\n", "id,id\n1,2\n"])
    def test_rejects_invalid_headers(self, tmp_path, text) -> None:
        path = tmp_path / "data.csv"
        path.write_text(text, encoding="utf-8-sig")
        with pytest.raises(CsvInvalidHeaderError):
            CSV(path).read()

    @pytest.mark.parametrize("text", ["id,name\n1\n", "id,name\n1,A,extra\n"])
    def test_rejects_wrong_data_width(self, tmp_path, text) -> None:
        path = tmp_path / "data.csv"
        path.write_text(text, encoding="utf-8-sig")
        with pytest.raises(CsvRowLengthError, match="2行目"):
            CSV(path).read()

    def test_missing_and_zero_byte_have_dedicated_errors(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        with pytest.raises(CsvFileNotFoundError):
            CSV(path).read()
        path.touch()
        with pytest.raises(CsvHeaderMissingError):
            CSV(path).read()
        assert CSV(path, columns=["id"]).read() == []

    def test_utf8_bom_only_has_missing_header_error(self, tmp_path) -> None:
        path = tmp_path / "bom_only.csv"
        path.write_bytes(b"\xef\xbb\xbf")
        with pytest.raises(CsvHeaderMissingError):
            CSV(path).read()

    def test_replace_empty_preserves_columns_or_requires_them(self, tmp_path) -> None:
        existing = tmp_path / "existing.csv"
        existing.write_text("id\n1\n", encoding="utf-8-sig")
        with CSV(existing) as csv_file:
            csv_file.replace([])
        assert existing.read_text(encoding="utf-8-sig") == "id\n"
        with pytest.raises(CsvColumnsRequiredError), CSV(tmp_path / "new.csv") as csv_file:
            csv_file.replace([])
