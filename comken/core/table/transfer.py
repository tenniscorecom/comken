"""comken/core/table/transfer.py — Table 間の非破壊転記。"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from enum import Enum, auto
from typing import Any, Final

from comken.core.table.model import Table
from comken.exceptions.table import (
    InvalidTableInputError,
    TransferDestinationMultipleMatchError,
    TransferMappingError,
    TransferRowError,
)

Row = dict[str, Any]


class _Control(Enum):
    SKIP = auto()
    STOP = auto()


Transform = Callable[[Row, Row | None], bool | None | _Control]


class Transfer:
    """read の行を write のコピーへ転記する。

    ``read`` と ``write`` は入力として扱い、どちらも直接変更しません。
    ``mapping`` は「read 側の列名: write 側の列名」で、転記のルールと一緒に
    コンストラクターへ渡します。保存は担当せず、結果の Table を呼び出し側へ返します。
    """

    SKIP: Final = _Control.SKIP
    STOP: Final = _Control.STOP
    APPLY: Final = True

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

    def transfer_rows(self) -> Iterator[tuple[Row, Row | None]]:
        """readを基準に、キーで対応付けた行を順番に返す。

        write側に同じキーがない場合も、転記元の行を落とさず
        ``(read_row, None)`` として返します。これは新規行を追加するかを
        利用者が条件分岐で判断できるようにするためです。
        """
        write_index = self._write_index()
        for read_row in self.read.read():
            key = self._row_key(read_row, self.read_keys)
            write_row = write_index.get(key)
            yield read_row, None if write_row is None else dict(write_row)

    def matched_rows(self) -> Iterator[tuple[Row, Row]]:
        """readとwriteの両方に存在する行だけを返す。"""
        for read_row, write_row in self.transfer_rows():
            if write_row is not None:
                yield read_row, write_row

    def result(self) -> Table:
        """転記処理の結果を新しいTableとして返す。

        このメソッドは、現在の公開APIでは ``run()`` の結果を明示的に
        取得するための名前として用意しています。入力Tableは変更しません。
        """
        return self.run()

    def run(self, *, transform: Transform | None = None) -> Table:
        """転記結果の新しい Table を返す。"""
        self.read._check_columns([*self.read_keys, *self.mapping.keys()])
        self.write._check_columns([*self.write_keys, *self.mapping.values()])
        # write をコピーしてから加工するため、元の Table は転記後もそのまま残る。
        result_table = Table(self.write.columns, self.write.read(), types=self.write.types)
        index: dict[tuple[Any, ...], Row] = {}
        for write_row in result_table:
            key = tuple(write_row[column] for column in self.write_keys)
            if key in index:
                raise TransferDestinationMultipleMatchError(
                    ",".join(self.write_keys), key
                )
            index[key] = write_row
        # read() でコピーを取り出すため、transform が行を変更しても入力 read は変わらない。
        for read_row in self.read.read():
            key = tuple(read_row[column] for column in self.read_keys)
            write_row = index.get(key)
            if write_row is None:
                # 新規行の追加は Table.append() の責務にするため、Transferでは扱わない。
                continue
            working_row = dict(write_row)
            control = transform(read_row, working_row) if transform else self.APPLY
            if control is self.STOP:
                break
            if control is self.SKIP or control is False:
                continue
            if control is self.STOP:
                break
            if control is not self.APPLY and control is not None:
                raise TransferRowError(
                    0, "transformはTrue、False、APPLY、SKIP、STOPのいずれかを返してください。"
                )
            for read_column, write_column in self.mapping.items():
                working_row[write_column] = read_row[read_column]
            write_row.update(working_row)
        return result_table

    def _write_index(self) -> dict[tuple[Any, ...], Row]:
        """writeの行を複合キーで検索できる辞書にする。"""
        self.write._check_columns(self.write_keys)
        index: dict[tuple[Any, ...], Row] = {}
        for write_row in self.write.read():
            key = self._row_key(write_row, self.write_keys)
            if key in index:
                raise TransferDestinationMultipleMatchError(
                    ",".join(self.write_keys), key
                )
            index[key] = write_row
        return index

    @staticmethod
    def _row_key(row: Row, columns: Sequence[str]) -> tuple[Any, ...]:
        """複数キーを順序付きの1つの比較値へまとめる。"""
        return tuple(row[column] for column in columns)


__all__ = ["Transfer"]
