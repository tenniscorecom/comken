"""comken/core/table/transfer.py — Table 間のキー突合。"""

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from comken.core.table.model import Table
from comken.exceptions.table import (
    InvalidTableInputError,
    TransferDestinationMultipleMatchError,
    TransferMappingError,
)

Row = dict[str, Any]


class Transfer:
    """行を見つづけて渡すところまで。

    ``read`` と ``write`` は入力として扱い、どちらも直接変更しません。
    ``mapping`` は「read 側の列名: write 側の列名」で、
    コンストラクターへ転記ルールと一緒に渡します。
    書き込み・追加・スキップ・中断の判定は利用者の Python コードが
    ``for`` / ``if`` / ``continue`` で書きます。Transfer はそのための
    「行を見つけて渡す」役割に絞ります。
    """

    def __init__(
        self,
        read: Table,
        write: Table,
        mapping: Mapping[str, str],
        *,
        read_key: str | Sequence[str] | None = None,
        write_key: str | Sequence[str] | None = None,
    ) -> None:
        if not isinstance(read, Table) or not isinstance(write, Table):
            raise InvalidTableInputError("TransferのreadとwriteにはTableを指定してください。")
        if not mapping or read_key is None or write_key is None:
            raise TransferMappingError
        self.read, self.write = read, write
        self.mapping = dict(mapping)
        self.read_keys = [read_key] if isinstance(read_key, str) else list(read_key)
        self.write_keys = [write_key] if isinstance(write_key, str) else list(write_key)
        if len(self.read_keys) != len(self.write_keys):
            raise TransferMappingError
        # transfer_rows() のための作業Table。matched_rows() は同じ実体を読む。
        self._working_table: Table | None = None

    def transfer_rows(self) -> Iterator[tuple[Row, Row | None]]:
        """転記元の全行を返す。

        転記先に存在しない行も ``(read_row, None)`` として返します。
        新規行の追加が必要かどうかは利用者が ``if destination is None: continue`` で
        その場で判定できるようにするためです。
        """
        self.read._check_columns(self.read_keys)
        self.write._check_columns(self.write_keys)
        if self._working_table is None:
            self._working_table = Table(
                self.write.columns, self.write.read(), types=self.write.types
            )
        write_index = self._working_index()
        for read_row in self.read.read():
            key = self._row_key(read_row, self.read_keys)
            write_row = write_index.get(key)
            yield read_row, write_row

    def matched_rows(self) -> Iterator[tuple[Row, Row]]:
        """両方に存在する行だけを返す。

        転記先に存在しない行（``destination`` が ``None``）は含みません。
        """
        for read_row, write_row in self.transfer_rows():
            if write_row is not None:
                yield read_row, write_row

    def _working_index(self) -> dict[tuple[Any, ...], Row]:
        """作業中のTableを複合キーで検索できる辞書にする。

        transfer_rows() のキー検索専用。複数の行が同じキーに当たる場合は
        曖昧な更新をさせないために例外で止める。
        """
        if self._working_table is None:
            return {}
        index: dict[tuple[Any, ...], Row] = {}
        for write_row in self._working_table._iter_rows_for_update():
            key = self._row_key(write_row, self.write_keys)
            if key in index:
                raise TransferDestinationMultipleMatchError(",".join(self.write_keys), key)
            index[key] = write_row
        return index

    @staticmethod
    def _row_key(row: Row, columns: Sequence[str]) -> tuple[Any, ...]:
        """複数キーを順序付きの1つの比較値へまとめる。"""
        return tuple(row[column] for column in columns)


__all__ = ["Transfer"]
