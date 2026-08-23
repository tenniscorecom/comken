"""comken/core/table/transfer.py — Table 間の非破壊転記。"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from enum import Enum, auto
from typing import Any, Final

from comken.core.table.model import Table
from comken.exceptions.table import (
    InvalidTableInputError,
    InvalidTransferResultError,
    TransferDestinationMultipleMatchError,
    TransferDestinationRowMissingError,
    TransferMappingError,
    TransferTransformError,
)

Row = dict[str, Any]


class TransferResult(Enum):
    """transform コールバックの戻り値。

    APPLY / SKIP / STOP のいずれかを返す。
    """

    APPLY = auto()  # 転記を適用
    SKIP = auto()  # この行をスキップ
    STOP = auto()  # 転記処理自体を中断


Transform = Callable[[Row, Row | None], TransferResult]


class Transfer:
    """read の行を write のコピーへ転記する。

    ``read`` と ``write`` は入力として扱い、どちらも直接変更しません。
    ``mapping`` は「read 側の列名: write 側の列名」で、転記のルールと一緒に
    コンストラクターへ渡します。保存は担当せず、結果の Table を呼び出し側へ返します。
    """

    APPLY: Final = TransferResult.APPLY
    SKIP: Final = TransferResult.SKIP
    STOP: Final = TransferResult.STOP

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
        self._working_table: Table | None = None

    def transfer_rows(self) -> Iterator[tuple[Row, Row | None]]:
        """readを基準に、キーで対応付けた行を順番に返す。

        write側に同じキーがない場合も、転記元の行を落とさず
        ``(read_row, None)`` として返します。これは新規行を追加するかを
        利用者が条件分岐で判断できるようにするためです。
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
        """readとwriteの両方に存在する行だけを返す。

        転記先に存在しない行（``destination_row`` が ``None``）は含みません。
        """
        for read_row, write_row in self.transfer_rows():
            if write_row is not None:
                yield read_row, write_row

    def result(self) -> Table:
        """転記処理の結果を新しいTableとして返す。

        このメソッドは、現在の公開APIでは ``run()`` の結果を明示的に
        取得するための名前として用意しています。入力Tableは変更しません。
        """
        if self._working_table is None:
            return self.run()
        return self._working_table

    def run(self, *, transform: Transform | None = None) -> Table:
        """転記結果の新しい Table を返す。"""
        self._working_table = None
        self.read._check_columns([*self.read_keys, *self.mapping.keys()])
        self.write._check_columns([*self.write_keys, *self.mapping.values()])
        # write をコピーしてから加工するため、元の Table は転記後もそのまま残る。
        result_table = Table(self.write.columns, self.write.read(), types=self.write.types)
        self._working_table = result_table
        for row_number, (read_row, write_row) in enumerate(self.transfer_rows(), start=1):
            key = tuple(read_row[column] for column in self.read_keys)
            control = self._process_row(read_row, write_row, transform, row_number, key)
            if control is TransferResult.STOP:
                break
        return result_table

    def _process_row(
        self,
        read_row: Row,
        write_row: Row | None,
        transform: Transform | None,
        row_number: int,
        key: tuple,
    ) -> TransferResult:
        """1行ごとに transform の判定結果を見て「どうするか」を実行する。"""
        if write_row is None:
            return self._process_unmatched_row(read_row, transform, row_number, key)
        working_row = self._build_working_row(write_row, read_row)
        control = self._run_transform(transform, read_row, working_row, row_number, key)
        if control is TransferResult.APPLY:
            write_row.update(working_row)
        return control

    def _process_unmatched_row(
        self,
        read_row: Row,
        transform: Transform | None,
        row_number: int,
        key: tuple,
    ) -> TransferResult:
        """転記先に存在しない行の処理を決める。"""
        # transform が無いときは未マッチ行を黙ってスキップする(後方互換)。
        if transform is None:
            return TransferResult.SKIP
        control = self._run_transform(transform, read_row, None, row_number, key)
        if control is TransferResult.APPLY:
            # 反映先がないので新規行を追加する責務は呼び出し側
            raise TransferDestinationRowMissingError(row_number)
        return control

    def _build_working_row(self, write_row: Row, read_row: Row) -> Row:
        """write_row を壊さずに mapping を適用した作業行を返す。"""
        working_row = dict(write_row)
        for read_column, write_column in self.mapping.items():
            working_row[write_column] = read_row[read_column]
        return working_row

    def _run_transform(
        self,
        transform: Transform | None,
        read_row: Row,
        working_row: Row | None,
        row_number: int,
        key: tuple,
    ) -> TransferResult:
        """利用者 callback の失敗へ転記元行の文脈を加える。"""
        if transform is None:
            return TransferResult.APPLY
        try:
            result = transform(read_row, working_row)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise TransferTransformError(row_number, key, read_row, exc) from exc
        if not isinstance(result, TransferResult):
            raise InvalidTransferResultError(row_number, result)
        return result

    def _working_index(self) -> dict[tuple[Any, ...], Row]:
        """作業中のTableを複合キーで検索できる辞書にする。"""
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


__all__ = ["Transfer", "TransferResult"]
