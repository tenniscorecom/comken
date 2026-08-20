"""comken/toolbox/table.py — 既存のCSV・Excelクラス間で行を転記する。"""

import logging
from collections.abc import Callable, Mapping
from enum import Enum, auto
from typing import Final, cast

from comken.core.timer import measure
from comken.exceptions import TransferSourceColumnNotFoundError
from comken.exceptions.table import (
    TransferDestinationMultipleMatchError,
    TransferDestinationRowMissingError,
    TransferMappingError,
    TransferRowError,
)
from comken.toolbox.csv import CsvReader, CsvWriter
from comken.toolbox.excel import Sheet

logger = logging.getLogger(__name__)

Row = dict[str, object]
Source = CsvReader | Sheet
Destination = CsvWriter | Sheet


class _TransferControl(Enum):
    SKIP = auto()
    STOP = auto()


Transform = Callable[[Row, Row | None], None | _TransferControl]


class Transfer:
    """既存のCSV・Excelクラス間で、列マッピングに従って行を転記する。

    CSVの転記先は、転記先の列名と順序が一致するように
    ``CsvWriter(path, fieldnames=list(mapping.values()))`` と構築する。
    Excelを転記元または転記先にする場合は、``ExcelWriter.sheet()`` で取得した
    ``Sheet`` を渡す。Excelファイルの保存は呼び出し側で ``save()`` する。
    """

    SKIP: Final = _TransferControl.SKIP
    STOP: Final = _TransferControl.STOP

    def __init__(
        self,
        source: Source,
        destination: Destination,
        mapping: Mapping[str, str],
    ) -> None:
        if not mapping:
            raise TransferMappingError
        self._source = source
        self._destination = destination
        self._mapping = dict(mapping)

    @measure
    def run(self, *, transform: Transform) -> int:
        """転記元を加工・選別して転記し、転記件数を返す。

        ``transform`` は転記元行と、mapping の先頭列で一致した既存の転記先行を受け取る。
        一致する行がなければ転記先行は ``None``。行はコピーせず渡すため直接変更できる。
        通常は何も返さず、``Transfer.SKIP`` で1件を除外し、``Transfer.STOP`` で全体を止める。
        """
        logger.debug(
            "Transfer開始: 転記元=%s 転記先=%s マッピング列数=%d",
            type(self._source).__name__,
            type(self._destination).__name__,
            len(self._mapping),
        )
        logger.debug("転記元データ取得開始")
        destination_rows = _read_destination_rows(self._destination)
        source_key_column, destination_key_column = next(iter(self._mapping.items()))
        destination_index = _index_destination_rows(destination_rows, destination_key_column)
        read_count = 0
        transferred_count = 0
        for source_row in _read_source_rows(self._source):
            read_count += 1
            if source_key_column not in source_row:
                raise TransferSourceColumnNotFoundError([source_key_column], list(source_row))
            destination_row = destination_index.get(source_row[source_key_column])
            try:
                result = transform(source_row, destination_row)
            except TypeError as error:
                if destination_row is None and _is_none_row_access_error(error):
                    raise TransferDestinationRowMissingError(read_count) from error
                raise
            if result is self.STOP:
                logger.debug("転記元データ取得を停止: 取得件数=%d", read_count)
                break
            if result is self.SKIP:
                continue
            if result is not None:
                raise TransferRowError(
                    read_count,
                    "transform は辞書を返す必要はありません。通常は None（return なし）、"
                    "1件を除外する場合は Transfer.SKIP、全体を止める場合は "
                    "Transfer.STOP を返してください。",
                )
            missing = [source for source in self._mapping if source not in source_row]
            if missing:
                raise TransferSourceColumnNotFoundError(missing, list(source_row))
            if destination_row is None:
                destination_row = {
                    destination: source_row[source] for source, destination in self._mapping.items()
                }
                destination_rows.append(destination_row)
                destination_index[source_row[source_key_column]] = destination_row
            transferred_count += 1
        logger.debug(
            "転記元データ取得完了: 取得件数=%d 転記対象件数=%d",
            read_count,
            transferred_count,
        )
        logger.debug("転記先書き込み開始: 件数=%d", len(destination_rows))
        _write_destination_rows(
            self._destination,
            destination_rows,
            list(self._mapping.values()),
        )
        logger.debug("Transfer完了: 転記件数=%d", transferred_count)
        return transferred_count


def _read_source_rows(source: Source) -> list[Row]:
    return list(source.rows())


def _read_destination_rows(destination: Destination) -> list[Row]:
    if isinstance(destination, CsvWriter):
        if not destination.path.exists() or destination.path.stat().st_size == 0:
            return []
        return [cast(Row, row) for row in CsvReader(destination.path).rows()]
    return list(destination.rows())


def _index_destination_rows(rows: list[Row], key_column: str) -> dict[object, Row]:
    index: dict[object, Row] = {}
    for row in rows:
        key = row.get(key_column)
        if key in index:
            raise TransferDestinationMultipleMatchError(key_column, key)
        index[key] = row
    return index


def _is_none_row_access_error(error: TypeError) -> bool:
    message = str(error)
    return "'NoneType' object is not subscriptable" in message or (
        "'NoneType' object does not support item assignment" in message
    )


def _write_destination_rows(
    destination: Destination,
    rows: list[Row],
    columns: list[str],
) -> None:
    if isinstance(destination, CsvWriter):
        destination.write_rows(rows)
        return
    if rows:
        destination.write_table(rows, headers=columns)
    else:
        destination.write_row(1, columns)


__all__ = ["Transfer"]
