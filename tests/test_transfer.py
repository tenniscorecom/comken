"""Transfer の契約テスト。"""

import pytest

from comken.core.table import Table, Transfer
from comken.exceptions.table import (
    InvalidTableInputError,
    TableColumnNotFoundError,
    TransferDestinationMissingError,
    TransferDestinationMultipleMatchError,
    TransferMappingError,
)


def test_transfer_init_rejects_non_table() -> None:
    """read/write は Table でなければならない。"""
    not_a_table: object = "not a table"
    with pytest.raises(InvalidTableInputError):
        Transfer(
            not_a_table,  # type: ignore[arg-type]
            Table(["id"], [{"id": 1}]),
            {"id": "id"},
            read_key="id",
            write_key="id",
        )
    with pytest.raises(InvalidTableInputError):
        Transfer(
            Table(["id"], [{"id": 1}]),
            not_a_table,  # type: ignore[arg-type]
            {"id": "id"},
            read_key="id",
            write_key="id",
        )


def test_transfer_init_requires_mapping_and_keys() -> None:
    """mapping / read_key / write_key が無ければ TransferMappingError。"""
    source = Table(["id"], [{"id": 1}])
    destination = Table(["id"], [{"id": 1}])
    with pytest.raises(TransferMappingError):
        Transfer(source, destination, {}, read_key="id", write_key="id")
    with pytest.raises(TransferMappingError):
        Transfer(source, destination, {"id": "id"}, read_key=None, write_key="id")
    with pytest.raises(TransferMappingError):
        Transfer(source, destination, {"id": "id"}, read_key="id", write_key=None)


def test_transfer_init_rejects_mismatched_key_lengths() -> None:
    """read_key と write_key の要素数を揃える。"""
    source = Table(["group", "id"], [{"group": "A", "id": 1}])
    destination = Table(["group", "id"], [{"group": "A", "id": 1}])
    with pytest.raises(TransferMappingError):
        Transfer(
            source,
            destination,
            {"id": "id"},
            read_key=["group", "id"],
            write_key="id",
        )


def test_transfer_init_rejects_missing_read_column() -> None:
    """mapping の read 列が read Table に無ければ TableColumnNotFoundError。"""
    source = Table(["id", "name"], [{"id": 1, "name": "A"}])
    destination = Table(["id", "name"], [{"id": 1, "name": "old"}])
    with pytest.raises(TableColumnNotFoundError):
        Transfer(source, destination, {"missing": "name"}, read_key="id", write_key="id")


def test_transfer_init_rejects_missing_write_column() -> None:
    """mapping の write 列が write Table に無ければ TableColumnNotFoundError。"""
    source = Table(["id", "name"], [{"id": 1, "name": "A"}])
    destination = Table(["id", "name"], [{"id": 1, "name": "old"}])
    with pytest.raises(TableColumnNotFoundError):
        Transfer(source, destination, {"name": "missing"}, read_key="id", write_key="id")


def test_transfer_transfer_rows_includes_unmatched() -> None:
    """transfer_rows() は未マッチ行を (read, None) で返す。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}, {"id": "2", "value": "extra"}])
    destination = Table(["id", "value"], [{"id": "1", "value": "old"}])

    pairs = list(
        Transfer(
            source, destination, {"value": "value"}, read_key="id", write_key="id"
        ).transfer_rows()
    )

    assert pairs == [
        ({"id": "1", "value": "new"}, {"id": "1", "value": "old"}),
        ({"id": "2", "value": "extra"}, None),
    ]


def test_transfer_matched_rows_excludes_unmatched() -> None:
    """matched_rows() は両側にキーが揃う行だけを返す。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}, {"id": "2", "value": "extra"}])
    destination = Table(["id", "value"], [{"id": "1", "value": "old"}])

    pairs = list(
        Transfer(
            source, destination, {"value": "value"}, read_key="id", write_key="id"
        ).matched_rows()
    )

    assert len(pairs) == 1
    read_row, write_row = pairs[0]
    assert write_row is not None
    assert read_row == {"id": "1", "value": "new"}
    assert write_row == {"id": "1", "value": "old"}


def test_transfer_apply_mapping_copies_by_mapping() -> None:
    """apply_mapping は mapping に従って read の値を write にコピーする。"""
    source = Table(["id", "name"], [{"id": 1, "name": "Alice"}])
    destination = Table(["id", "name"], [{"id": 1, "name": ""}])
    transfer = Transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")

    for read_row, write_row in transfer.matched_rows():
        transfer.apply_mapping(read_row, write_row)

    assert transfer.result().read() == [{"id": 1, "name": "Alice"}]


def test_transfer_apply_mapping_supports_different_column_names() -> None:
    """mapping の read 列と write 列で名前が違っていても転記できる。"""
    source = Table(["id", "name"], [{"id": 1, "name": "山田"}])
    destination = Table(["id", "label"], [{"id": 1, "label": "旧"}])
    transfer = Transfer(source, destination, {"name": "label"}, read_key="id", write_key="id")

    for read_row, write_row in transfer.matched_rows():
        transfer.apply_mapping(read_row, write_row)

    assert transfer.result().read() == [{"id": 1, "label": "山田"}]


def test_transfer_apply_mapping_supports_composite_key() -> None:
    """複合キーの Table でも apply_mapping で正しく転記できる。"""
    source = Table(
        ["group", "id", "value"],
        [
            {"group": "A", "id": 1, "value": "new"},
            {"group": "B", "id": 2, "value": "extra"},
        ],
    )
    destination = Table(
        ["group", "id", "value"],
        [{"group": "A", "id": 1, "value": "old"}],
    )
    transfer = Transfer(
        source,
        destination,
        {"value": "value"},
        read_key=["group", "id"],
        write_key=["group", "id"],
    )

    for read_row, write_row in transfer.matched_rows():
        transfer.apply_mapping(read_row, write_row)

    # A-1 だけ転記される。B-2 は write に存在しないので対象にならない。
    assert transfer.result().read() == [{"group": "A", "id": 1, "value": "new"}]


def test_transfer_continue_skips_apply_mapping() -> None:
    """``continue`` した行は mapping 適用されず、write の値のまま残る。"""
    source = Table(
        ["id", "value"],
        [{"id": 1, "value": "new"}, {"id": 2, "value": "x"}],
    )
    destination = Table(
        ["id", "value"],
        [{"id": 1, "value": "old"}, {"id": 2, "value": "old2"}],
    )
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    for read_row, write_row in transfer.matched_rows():
        # value が "x" のときは転記しない
        if read_row["value"] == "x":
            continue
        transfer.apply_mapping(read_row, write_row)

    # id=1 だけ転記され、id=2 は古い値のまま
    assert transfer.result().read() == [
        {"id": 1, "value": "new"},
        {"id": 2, "value": "old2"},
    ]


def test_transfer_apply_mapping_does_not_mutate_input_tables() -> None:
    """apply_mapping を呼んでも read / write Table は変わらない。"""
    source = Table(["id", "value"], [{"id": 1, "value": "new"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    original_source = source.read()
    original_destination = destination.read()
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    for read_row, write_row in transfer.matched_rows():
        transfer.apply_mapping(read_row, write_row)

    assert source.read() == original_source
    assert destination.read() == original_destination
    # 作業 Table 側にだけ変更が反映されている
    assert transfer.result().read() != original_destination


def test_transfer_apply_mapping_with_none_destination_raises() -> None:
    """apply_mapping に None の write_row を渡すと TransferDestinationMissingError。"""
    source = Table(["id", "value"], [{"id": 2, "value": "new"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    # transfer_rows() の (read_row, None) をそのまま渡すと例外になる
    for read_row, write_row in transfer.transfer_rows():
        if write_row is None:
            with pytest.raises(TransferDestinationMissingError):
                transfer.apply_mapping(read_row, write_row)


def test_transfer_guarding_none_with_transfer_rows_works() -> None:
    """transfer_rows() で None を弾いてから apply_mapping を呼べる。"""
    source = Table(["id", "value"], [{"id": 1, "value": "new"}, {"id": 2, "value": "extra"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    for read_row, write_row in transfer.transfer_rows():
        if write_row is None:
            continue  # 新規行は追加しない
        transfer.apply_mapping(read_row, write_row)

    # id=2 は write に存在しないので mapping 適用されず、id=1 だけ転記される
    assert transfer.result().read() == [{"id": 1, "value": "new"}]


def test_transfer_destination_changes_persist_to_working_table() -> None:
    """利用者が write_row[...] = ... で書き換えると _working_table に反映される。"""
    source = Table(["id", "value"], [{"id": 1, "value": "new"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    for read_row, write_row in transfer.matched_rows():
        write_row["value"] = read_row["value"]

    assert transfer._working_table is not None
    assert transfer._working_table.read() == [{"id": 1, "value": "new"}]
    # 入力は不変（書き換えは作業 Table への操作）
    assert source.read() == [{"id": 1, "value": "new"}]
    assert destination.read() == [{"id": 1, "value": "old"}]


def test_transfer_transfer_rows_returns_iterator_and_can_be_reused() -> None:
    """transfer_rows() はイテレータを返し、繰り返し呼んでも毎回結果を取り出せる。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}])
    destination = Table(["id", "value"], [{"id": "1", "value": "old"}])
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    first = transfer.transfer_rows()
    assert iter(first) is first
    assert list(first) == [({"id": "1", "value": "new"}, {"id": "1", "value": "old"})]
    # 同じ呼び出しをもう一度やっても同じ結果（_working_table は最初の呼び出しで固定）
    assert list(transfer.transfer_rows()) == [
        ({"id": "1", "value": "new"}, {"id": "1", "value": "old"})
    ]


def test_transfer_supports_composite_key() -> None:
    """複数キーの照合ができる。"""
    source = Table(
        ["group", "id", "value"],
        [
            {"group": "A", "id": 1, "value": "new"},
            {"group": "B", "id": 2, "value": "add"},
        ],
    )
    destination = Table(["group", "id", "value"], [{"group": "A", "id": 1, "value": "old"}])
    transfer = Transfer(
        source,
        destination,
        {"value": "value"},
        read_key=["group", "id"],
        write_key=["group", "id"],
    )

    pairs = list(transfer.transfer_rows())

    assert pairs[0][0] == {"group": "A", "id": 1, "value": "new"}
    assert pairs[0][1] == {"group": "A", "id": 1, "value": "old"}
    assert pairs[1][0] == {"group": "B", "id": 2, "value": "add"}
    assert pairs[1][1] is None


def test_transfer_rejects_missing_read_key_column() -> None:
    """read_key が Table に無い列なら TableColumnNotFoundError。"""
    read = Table(["id", "name"], [{"id": 1, "name": "A"}])
    write = Table(["id", "name"], [{"id": 1, "name": "old"}])
    with pytest.raises(TableColumnNotFoundError):
        list(
            Transfer(
                read, write, {"name": "name"}, read_key="missing", write_key="id"
            ).transfer_rows()
        )


def test_transfer_rejects_missing_write_key_column() -> None:
    """write_key が Table に無い列なら TableColumnNotFoundError。"""
    read = Table(["id", "name"], [{"id": 1, "name": "A"}])
    write = Table(["id", "name"], [{"id": 1, "name": "old"}])
    with pytest.raises(TableColumnNotFoundError):
        list(
            Transfer(
                read, write, {"name": "name"}, read_key="id", write_key="missing"
            ).transfer_rows()
        )


def test_transfer_rejects_duplicate_write_key() -> None:
    """write_key が重複する行を持っていれば TransferDestinationMultipleMatchError。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}])
    destination = Table(
        ["id", "value"],
        [{"id": "1", "value": "one"}, {"id": "1", "value": "two"}],
    )
    with pytest.raises(TransferDestinationMultipleMatchError):
        list(
            Transfer(
                source, destination, {"value": "value"}, read_key="id", write_key="id"
            ).transfer_rows()
        )


def test_transfer_does_not_mutate_input_tables() -> None:
    """Transfer の呼び出しだけで read / write の行は変わらない。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}])
    destination = Table(["id", "value"], [{"id": "1", "value": "old"}])
    original_source = source.read()
    original_destination = destination.read()
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    list(transfer.matched_rows())

    assert source.read() == original_source
    assert destination.read() == original_destination


def test_result_returns_modified_table_after_iterator() -> None:
    """apply_mapping の変更が result() に反映される。"""
    source = Table(["id", "name"], [{"id": 1, "name": "Alice"}])
    destination = Table(["id", "name"], [{"id": 1, "name": ""}])
    transfer = Transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")

    for src, dst in transfer.matched_rows():
        transfer.apply_mapping(src, dst)

    result_table = transfer.result()
    assert result_table.read()[0]["name"] == "Alice"


def test_result_returns_copy_when_iterator_not_called() -> None:
    """result() を最初に呼ぶと write のコピーが返る（変更なし）。"""
    source = Table(["id"], [{"id": 1}])
    destination = Table(["id", "name"], [{"id": 1, "name": "Original"}])
    transfer = Transfer(source, destination, {"id": "id"}, read_key="id", write_key="id")

    result_table = transfer.result()

    # transfer_rows() を呼んでいないので、write のコピー（変更なし）
    assert result_table.read()[0]["name"] == "Original"
