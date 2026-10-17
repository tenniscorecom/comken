"""comken/core/table/transfer.py — Table 間のキー突合と転記。

``transfer(read, write, mapping, read_key=..., write_key=..., where=...)`` を
1 回呼ぶと、転記後の ``Table`` と、``only_in_read`` / ``only_in_write``、
``matched_count`` / ``transferred_count`` を ``TransferResult`` で返す。
キーは ``comken.core.text.normalize`` でそろえてから比べる
（``Table.diff()`` と同じ規則）。CSV の ``"1001"`` と Excel の ``1001.0``、
全角の ``Ａ１`` と半角の ``A1``、前後の空白は、同じキーとして突合する。
突合に使うだけで、転記するデータは変えない（ただし ``write.types`` の変換だけは
転記した値に 1 回だけかける）。
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from comken.core.table.diff import index_by_key
from comken.core.table.model import Table
from comken.core.text import normalize
from comken.core.types import Row
from comken.exceptions.tables import (
    InvalidTableInputError,
    TableError,
)

logger = logging.getLogger(__name__)


def _transfer_mapping_error() -> TableError:
    """``TableError`` の「mapping に転記元列と転記先列が指定されていない」文言。"""
    return TableError(
        "mapping には転記元列と転記先列を指定してください。"
        "\n対処: mapping に転記元列名と転記先列名を指定してください。"
    )


def _transfer_duplicate_destination_error(duplicates: list[str]) -> TableError:
    """``TableError`` の「mapping の転記先列が重複している」文言。"""
    return TableError(
        f"mapping の転記先列に重複があります: {','.join(duplicates)}。"
        "\n対処: mapping の転記先列を一意にしてください。"
    )


@dataclass(frozen=True)
class TransferResult:
    """``transfer()`` の結果。

    Attributes:
        table: 転記後の ``Table``。 ``write`` と同じ列・同じ行順・同じ行数の
            **新しい** ``Table``。 入力 ``write`` は変更しない。
        only_in_read: ``write`` に対応が無かった ``read`` の行（``read`` の列構成・型）。
            空キーの行も含む。
        only_in_write: ``read`` に対応が無かった ``write`` の行（``write`` の列構成・型）。
            **転記前の値** をそのまま持つ。 空キーの行も含む。
        matched_count: キーが一致した組の数（``where`` の結果に関係なく）。
        transferred_count: そのうち ``where`` が True で実際に転記した組の数。
    """

    table: Table
    only_in_read: Table
    only_in_write: Table
    matched_count: int
    transferred_count: int


def _validate_transfer_inputs(
    read: Table,
    write: Table,
    mapping: Mapping[str, str],
    read_key: str | Sequence[str],
    write_key: str | Sequence[str],
) -> tuple[dict[str, str], list[str], list[str]]:
    """``transfer()`` の入力検証（データを読む前に全部済ませる）。

    Returns:
        ``(mapping_dict, read_keys, write_keys)``。
    """
    if not isinstance(read, Table) or not isinstance(write, Table):
        raise InvalidTableInputError("transferのreadとwriteにはTableを指定してください。")

    mapping_dict = dict(mapping)
    read_keys = [read_key] if isinstance(read_key, str) else list(read_key)
    write_keys = [write_key] if isinstance(write_key, str) else list(write_key)

    if not mapping_dict or not read_keys or not write_keys:
        raise _transfer_mapping_error()
    if len(read_keys) != len(write_keys):
        raise _transfer_mapping_error()

    write_targets = list(mapping_dict.values())
    duplicates = sorted({column for column in write_targets if write_targets.count(column) > 1})
    if duplicates:
        raise _transfer_duplicate_destination_error(duplicates)

    # mapping とキー列の存在をまとめて検証する。 Table._check_columns は
    # 不足列を ``TableColumnNotFoundError`` にまとめて出す。
    read._check_columns(read_keys)
    write._check_columns(write_keys)
    read._check_columns(list(mapping_dict.keys()))
    write._check_columns(write_targets)

    return mapping_dict, read_keys, write_keys


def _apply_transfers(
    read_index: dict[tuple[str, ...], Row],
    write_index: dict[tuple[str, ...], Row],
    write_rows: list[Row],
    write: Table,
    mapping_dict: dict[str, str],
    where: Callable[[Row, Row], bool] | None,
) -> tuple[list[Row], int, int]:
    """matched 組を転記して作業用行を作る（``transfer()`` のコア処理）。

    Returns:
        ``(new_rows, matched_count, transferred_count)``。
        ``new_rows`` は ``write`` と同じ行順・同じ行数の新しい行のリスト。
    """
    # write の各行の「作業中」位置（write の 1 始まり行番号）を引けるように、
    # id(row) で位置を覚えておく。
    write_position: dict[int, int] = {id(row): index for index, row in enumerate(write_rows)}
    new_rows: list[Row] = [dict(row) for row in write_rows]

    matched_count = 0
    transferred_count = 0

    for read_key_tuple, read_row in read_index.items():
        write_row = write_index.get(read_key_tuple)
        if write_row is None:
            continue
        matched_count += 1
        # write の 1 始まり行番号。 ``Table._convert_one`` のメッセージが
        # 「Table の N 件目」と出るので、write の何件目かを渡す
        # （``Table.concat()`` の ``other`` 側の使い方と同じ）。
        position = write_position[id(write_row)]
        row_number = position + 1
        if where is not None and not where(dict(read_row), dict(write_row)):
            # 条件で外れた行は転記せず、only_in_* にも入れない（キーが一致しているため）
            continue
        new_row = new_rows[position]
        for read_column, write_column in mapping_dict.items():
            value = read_row[read_column]
            if write_column in write.types:
                # 転記した値にだけ 1 回かける。 転記しなかった値には再適用しない。
                value = write._convert_one(write_column, value, row_number)
            new_row[write_column] = value
        transferred_count += 1

    return new_rows, matched_count, transferred_count


def _build_unmatched_rows(
    rows: list[Row],
    columns: list[str],
    counterpart_index: dict[tuple[str, ...], Row],
) -> list[Row]:
    """未一致行（キーが空、または相手側索引に無い行）だけを ``rows`` の順で集める。"""
    unmatched: list[Row] = []
    for row in rows:
        key = tuple(normalize(row[column]) for column in columns)
        if any(value == "" for value in key) or key not in counterpart_index:
            unmatched.append(row)
    return unmatched


def transfer(
    read: Table,
    write: Table,
    mapping: Mapping[str, str],
    *,
    read_key: str | Sequence[str],
    write_key: str | Sequence[str],
    where: Callable[[Row, Row], bool] | None = None,
) -> TransferResult:
    """Table 間のキー突合と転記を 1 回で行う。

    Args:
        read: 転記元の ``Table``。変更しない。
        write: 転記先の ``Table``。変更しない。
        mapping: 「転記元の列名 → 転記先の列名」の ``Mapping``。 1 個以上必須。
        read_key: ``read`` のキー列。 ``str`` なら 1 列、 ``Sequence[str]`` なら複合キー。
        write_key: ``write`` のキー列。 ``read_key`` と同じ要素数でなければならない。
        where: 任意の追加条件 ``(read_row, write_row) -> bool``。 ``True`` のときだけ
            転記する。 受け取るのはコピー（書き換えても結果にも入力にも影響しない）。
            判定だけ書く（行を直す処理は書かない）。 ログ出力は可。 例外はそのまま
            伝わる。 未一致の行では呼ばれない。 1 組につき 1 回。

    Returns:
        ``TransferResult``。 ``table`` が転記後の ``Table``、 ``only_in_read`` /
        ``only_in_write`` が未一致の行、 ``matched_count`` / ``transferred_count``
        が一致数と転記数。

    Raises:
        InvalidTableInputError: ``read`` / ``write`` が ``Table`` でない。
        TableError: ``mapping`` が空、 ``read_key`` と ``write_key`` の要素数が違う、
            ``mapping`` の転記先列が重複している。
        TableColumnNotFoundError: ``mapping`` の転記元列・転記先列、
            ``read_key`` / ``write_key`` の列が存在しない（データを読む前に出る）。

    Note:
        セルの値は ``str`` / ``int`` / ``float`` / ``bool`` / ``datetime`` などの
        **不変の値であること** を前提とする。 ``list`` や ``dict`` など変更可能な値を
        セルに入れた場合、浅いコピーによる共有は保証しない。

        ``result.table`` は転記した値に ``write.types`` の変換を 1 回かける。
        転記しなかった行・列には変換関数を再適用しない（呼び出し回数が増える不具合を
        防ぐため）。 ``write.types`` に無い列は変換しない。 変換できない値は
        ``TableError``（行番号・列名・値が出る）。

    Example:
        通常の転記::

            from comken.core.table import Table, transfer
            result = transfer(
                source, destination, mapping={"顧客名": "name", "金額": "amount"},
                read_key="顧客ID", write_key="id",
            )
            result_table = result.table

        ``where`` で条件を満たす行だけ転記::

            def is_confirmed(read_row, write_row):
                return read_row["金額"] > 0
            result = transfer(
                source, destination, mapping, read_key="id", write_key="id", where=is_confirmed,
            )

        未一致の行を別途処理する::

            for read_row in result.only_in_read:
                ...  # read 側にしか無い行（write への新規追加候補）

            for write_row in result.only_in_write:
                ...  # write 側にしか無い行（破棄候補）
    """
    mapping_dict, read_keys, write_keys = _validate_transfer_inputs(
        read, write, mapping, read_key, write_key
    )

    logger.debug(
        "transfer 開始: read=%d 行, write=%d 行, mapping=%d 列, keys(read/write)=%d/%d",
        len(read),
        len(write),
        len(mapping_dict),
        len(read_keys),
        len(write_keys),
    )

    # ---- 索引作成（重複があればここで TableDuplicateKeyError）----
    read_rows = read.to_rows()
    write_rows = write.to_rows()
    read_index = index_by_key(read_rows, read_keys, skip_blank=True)
    write_index = index_by_key(write_rows, write_keys, skip_blank=True)

    # ---- 転記ループ ----
    new_rows, matched_count, transferred_count = _apply_transfers(
        read_index, write_index, write_rows, write, mapping_dict, where
    )
    result_table = Table._from_normalized_rows(write.columns, new_rows, types=write.types)

    # ---- 未一致行（入力のコピーを使う。 結果と辞書を共有しない）----
    only_in_read_rows = _build_unmatched_rows(read_rows, read_keys, write_index)
    only_in_read = Table._from_normalized_rows(read.columns, only_in_read_rows, types=read.types)

    only_in_write_rows = _build_unmatched_rows(write_rows, write_keys, read_index)
    only_in_write = Table._from_normalized_rows(
        write.columns, only_in_write_rows, types=write.types
    )

    logger.debug(
        "transfer 完了: matched=%d, transferred=%d, only_in_read=%d, only_in_write=%d",
        matched_count,
        transferred_count,
        len(only_in_read),
        len(only_in_write),
    )

    return TransferResult(
        table=result_table,
        only_in_read=only_in_read,
        only_in_write=only_in_write,
        matched_count=matched_count,
        transferred_count=transferred_count,
    )


__all__ = ["TransferResult", "transfer"]
