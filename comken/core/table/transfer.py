"""comken/core/table/transfer.py — Table 間のキー突合。

``Transfer(read, write, mapping, read_key=..., write_key=...)`` を作り、
``matched_rows()`` / ``transfer_rows()`` で ``for`` ループしながら
``apply_mapping(read_row, write_row)`` を呼ぶ書き方が公式。
mapping の列名はコンストラクタで検証するので、typo は早期に例外になる。
入力 ``read`` / ``write`` は直接変更せず、内部の作業 Table に書き込む。
"""

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from comken.core.table.model import Table
from comken.exceptions.table import (
    InvalidTableInputError,
    TableColumnNotFoundError,
    TransferDestinationMissingError,
    TransferDestinationMultipleMatchError,
    TransferMappingError,
)

Row = dict[str, Any]


class Transfer:
    """Table 間のキー突合と転記を行う。

    基本的な使い方は次のとおり。 ``mapping`` は「転記元の列名 → 転記先の列名」。

    Example:
        transfer = Transfer(read_table, write_table, mapping,
                            read_key="顧客ID", write_key="顧客ID")
        for read_row, write_row in transfer.matched_rows():
            if 条件:
                continue                       # この行は破棄
            transfer.apply_mapping(read_row, write_row)   # mapping の値をコピー
            # 必要なら write_row["備考"] = "..." のように追加加工
        result = transfer.result()             # 変更後の Table

    **条件は ``apply_mapping()`` より前に書くこと。** Python の ``for`` ループは
    ``continue`` したかどうかを呼び出し側に伝えないため、ループ内で
    ``apply_mapping()`` を呼ばずに ``continue`` した行は、作業 Table へ反映されない。
    条件判定を ``apply_mapping()`` の後ろに書くと、``continue`` しても mapping が
    適用済みとなり破棄できないので、判定は必ず ``apply_mapping()`` の前に置く。
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
        # mapping の列名 typo を早期に検知する。実行時の KeyError を未然に防ぐため。
        # 表を引かない素の mapping 検証はここで済ませておく。
        read_existing = list(self.read.columns)
        write_existing = list(self.write.columns)
        missing_read = [column for column in self.mapping if column not in read_existing]
        if missing_read:
            raise TableColumnNotFoundError(missing_read)
        missing_write = [column for column in self.mapping.values() if column not in write_existing]
        if missing_write:
            raise TableColumnNotFoundError(missing_write)
        # 作業 Table は最初のイテレーションで生成する。入力には触らない。
        self._working_table: Table | None = None

    def transfer_rows(self) -> Iterator[tuple[Row, Row | None]]:
        """転記元の全行を ``(read_row, write_row)`` で返す。

        転記先に存在しない行は ``(read_row, None)`` として返す。新規行の追加が
        必要かどうかは利用者が ``if write_row is None: ...`` で判定する。
        書き込みは ``apply_mapping(read_row, write_row)`` を中心に行い、
        必要な列だけを ``write_row[write_col] = read_row[read_col]`` の形で
        個別に上書きする。 結果は ``result()`` で取り出す。
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
        """両方に存在する行だけを ``(read_row, write_row)`` で返す。

        転記先に存在しない行（``destination`` が ``None``）は含まない。
        """
        for read_row, write_row in self.transfer_rows():
            if write_row is not None:
                yield read_row, write_row

    def apply_mapping(self, read_row: Row, write_row: Row | None) -> None:
        """コンストラクタで渡された ``mapping`` どおりに値を ``write_row`` へコピーする。

        mapping の read 列 / write 列は ``__init__`` で存在を検証済みなので、
        ここで再びキー存在を確かめない。 ``write_row`` が ``None`` の場合
        （``transfer_rows()`` の ``(read_row, None)`` をそのまま渡した場合など）は
        転記先の行が無いので ``TransferDestinationMissingError`` で停止する。

        入力 ``read`` / ``write`` には触れない。書き込みは Transfer 内部の
        作業 Table に紐づいた ``write_row`` に対して行う。

        Args:
            read_row: 転記元の行。
            write_row: 転記先の行。 ``matched_rows()`` の戻り値か、
                ``transfer_rows()`` の戻り値で ``None`` でないもの。

        Raises:
            TransferDestinationMissingError: ``write_row`` が ``None`` のとき。
        """
        if write_row is None:
            raise TransferDestinationMissingError(
                "apply_mapping に None の転記先行を渡しました。"
                "transfer_rows() が返した (read_row, None) は write 側に対応行が無い行です。"
                "matched_rows() を使うか、None を確認してから渡してください。"
            )
        # mapping は __init__ で検証済み。辞書のキー参照が KeyError になる心配はない。
        for read_column, write_column in self.mapping.items():
            write_row[write_column] = read_row[read_column]

    def result(self) -> Table:
        """変更後の Table を返す。

        ``transfer_rows()`` / ``matched_rows()`` のイテレーション中に ``write_row``
        に対して行った変更が反映された作業用 Table を返す。 イテレータを 1 度も
        進めないうちに ``result()`` を呼ぶと ``write`` のコピー（変更なし）が返る。

        Example:
            transfer = Transfer(source, destination, mapping,
                                read_key="顧客ID", write_key="顧客ID")
            for source_row, destination_row in transfer.matched_rows():
                transfer.apply_mapping(source_row, destination_row)
            final_table = transfer.result()  # 変更後の Table
        """
        if self._working_table is None:
            # transfer_rows() / matched_rows() がまだ呼ばれていないので、
            # write のコピーを返す（変更なし）。
            self._working_table = Table(
                self.write.columns, self.write.read(), types=self.write.types
            )
        return self._working_table

    def _working_index(self) -> dict[tuple[Any, ...], Row]:
        """作業中の Table を複合キーで検索できる辞書にする。

        ``transfer_rows()`` のキー検索専用。同じキーに複数の行が当たる場合は
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
