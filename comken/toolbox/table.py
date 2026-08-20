"""comken/toolbox/table.py — CSV・Excelを同じ表データとして扱う入口。"""

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, Self

from comken.constants import Encoding
from comken.exceptions.table import TableNotOpenError, TransferMappingError
from comken.toolbox.csv import CsvReader, CsvWriter
from comken.toolbox.excel import ExcelWriter, Sheet

Row = dict[str, Any]


class CSV:
    """CSVを列名付きの行として読み書きする。"""

    def __init__(self, path: str | Path, encoding: str = Encoding.AUTO) -> None:
        self.path = Path(path)
        self._encoding = encoding

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def rows(self) -> Iterator[Row]:
        """各行を列名でアクセスできる辞書として返す。"""
        yield from CsvReader(self.path, encoding=self._encoding).rows()

    def write_rows(self, rows: Iterable[Mapping[str, object]]) -> None:
        """行をCSVへ上書き保存する。列順は最初の行に合わせる。"""
        materialized = [dict(row) for row in rows]
        if materialized:
            CsvWriter(self.path, list(materialized[0]), encoding=self._encoding).write_rows(
                materialized
            )


class Excel:
    """Excelの1シートを列名付きの行として読み書きする。"""

    def __init__(self, path: str | Path, sheet: str = "Sheet1") -> None:
        self.path = Path(path)
        self._sheet_name = sheet
        self._book: ExcelWriter | None = None
        self._is_dirty = False

    def __enter__(self) -> Self:
        self._book = ExcelWriter(self.path) if self.path.exists() else ExcelWriter.create(self.path)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._book is None:
            return
        if exc_type is None and self._is_dirty:
            self._book.save()
        self._book.close()

    def rows(self) -> Iterator[Row]:
        """各行を列名でアクセスできる辞書として返す。"""
        yield from self._require_book().rows(self._sheet_name)

    def write_rows(self, rows: Iterable[Mapping[str, object]]) -> None:
        """選択中のシートへ列名と行を書き込む。"""
        materialized = [dict(row) for row in rows]
        if materialized:
            sheet = self._require_book().sheet(self._sheet_name)
            sheet.ws.delete_rows(1, sheet.ws.max_row)
            sheet.write_table(materialized)
            self._is_dirty = True

    def sheet(self, name: str | None = None) -> Sheet:
        """セルや書式を操作するシートを返す。"""
        self._is_dirty = True
        return self._require_book().sheet(name or self._sheet_name)

    def _require_book(self) -> ExcelWriter:
        if self._book is None:
            raise TableNotOpenError("Excel")
        return self._book


class Transfer:
    """列マッピングに従って表データを一方向へ転記する。"""

    def __init__(
        self, source: CSV | Excel, destination: CSV | Excel, mapping: Mapping[str, str]
    ) -> None:
        if not mapping:
            raise TransferMappingError
        self._source = source
        self._destination = destination
        self._mapping = dict(mapping)

    def rows(self) -> Iterator[Row]:
        """転記前に選別・加工できる転記元行のコピーを返す。"""
        for source_row in self._source.rows():
            yield dict(source_row)

    def run(self, rows: Iterable[Mapping[str, object]] | None = None) -> int:
        """指定行をマッピングして転記し、転記件数を返す。"""
        source_rows = rows if rows is not None else self.rows()
        destination_rows = [
            {destination: row.get(source) for source, destination in self._mapping.items()}
            for row in source_rows
        ]
        self._destination.write_rows(destination_rows)
        return len(destination_rows)


__all__ = ["CSV", "Excel", "Transfer"]
