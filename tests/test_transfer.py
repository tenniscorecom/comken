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
    assert transfer.result().read() == [{"id": 1, "value": "new"}]
    # 入力は不変（書き換えは作業行への操作）
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
    # 同じ呼び出しをもう一度やっても同じ結果（_working_rows は最初の呼び出しで固定）
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


# ---- 未マッチ行 API ----


def test_unmatched_only_in_read_returns_rows_missing_in_write() -> None:
    """unmatched().only_in_read は write に無い read 行だけを返す。"""
    source = Table(
        ["id", "value"],
        [{"id": "1", "value": "new"}, {"id": "2", "value": "extra"}],
    )
    destination = Table(["id", "value"], [{"id": "1", "value": "old"}])
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    extras = transfer.unmatched().only_in_read.read()

    assert extras == [{"id": "2", "value": "extra"}]


def test_unmatched_only_in_write_returns_rows_missing_in_read() -> None:
    """unmatched().only_in_write は read に無い write 行だけを返す。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}])
    destination = Table(
        ["id", "value"],
        [{"id": "1", "value": "old"}, {"id": "2", "value": "stale"}],
    )
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    extras = transfer.unmatched().only_in_write

    assert extras == [{"id": "2", "value": "stale"}]


def test_unmatched_only_in_write_mutation_reflects_in_result() -> None:
    """unmatched().only_in_write で書き換えた値が result() にも反映される。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}])
    destination = Table(
        ["id", "value"],
        [{"id": "1", "value": "old"}, {"id": "2", "value": "stale"}],
    )
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    # write にしか無い行の "備考" 列を埋める
    for write_row in transfer.unmatched().only_in_write:
        write_row["value"] = "破棄予定"

    assert transfer.result().read() == [
        {"id": "1", "value": "old"},
        {"id": "2", "value": "破棄予定"},
    ]


def test_blank_key_rows_are_excluded_from_matching() -> None:
    """空キーは照合に使わず、result() にも転記されない。

    既存バグの例: write 側の空キーが「一致した行」と判定されて
    TransferDestinationMultipleMatchError で止まる事故を防ぐ。
    """
    source = Table(
        ["id", "name"],
        [{"id": "", "name": "空白"}, {"id": "1", "name": "正常"}],
    )
    destination = Table(
        ["id", "name"],
        [{"id": "", "name": ""}, {"id": "1", "name": ""}],
    )
    transfer = Transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")

    # matched_rows は id="1" の1件だけ
    pairs = list(transfer.matched_rows())
    assert len(pairs) == 1
    read_row, write_row = pairs[0]
    assert read_row["id"] == "1"
    assert write_row is not None and write_row["id"] == "1"

    # mapping を適用。空キーは result() に初期値のまま残る
    for src, dst in pairs:
        transfer.apply_mapping(src, dst)

    # write に転記されたのは id="1" だけ。空キーは転記対象外なので初期値のまま
    assert transfer.result().read() == [
        {"id": "", "name": ""},
        {"id": "1", "name": "正常"},
    ]


def test_unmatched_only_in_read_includes_blank_keys() -> None:
    """read 側の空キー行は unmatched().only_in_read に流れる。"""
    source = Table(
        ["id", "name"],
        [{"id": "", "name": "空白"}],
    )
    destination = Table(["id", "name"], [{"id": "1", "name": "既存"}])
    transfer = Transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")

    extras = transfer.unmatched().only_in_read.read()

    assert extras == [{"id": "", "name": "空白"}]


def test_unmatched_only_in_write_includes_blank_keys() -> None:
    """write 側の空キー行は unmatched().only_in_write に流れる。"""
    source = Table(["id", "name"], [{"id": "1", "name": "新規"}])
    destination = Table(
        ["id", "name"],
        [{"id": "", "name": ""}, {"id": "1", "name": ""}],
    )
    transfer = Transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")

    extras = transfer.unmatched().only_in_write

    assert extras == [{"id": "", "name": ""}]


def test_none_key_is_treated_as_blank() -> None:
    """キー値が ``None`` のときも ``""`` と同じ空キー扱い。"""
    source = Table(
        ["id", "name"],
        [{"id": None, "name": "Noneキー"}],
    )
    destination = Table(["id", "name"], [{"id": "1", "name": "既存"}])
    transfer = Transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")

    # matched_rows も空集合
    assert list(transfer.matched_rows()) == []
    # source 側の None は空キー扱いで only_in_read 側へ流れる
    result = transfer.unmatched()
    assert result.only_in_read.read() == [{"id": None, "name": "Noneキー"}]
    # destination 側の "1" は source に無いので only_in_write 側へ流れる
    assert result.only_in_write == [{"id": "1", "name": "既存"}]


def test_zero_value_is_a_valid_key() -> None:
    """``0`` はキーに使っても空キー扱いにならない（数値ゼロ落ち対策）。"""
    source = Table(["id", "value"], [{"id": 0, "value": "zero-read"}])
    destination = Table(["id", "value"], [{"id": 0, "value": "zero-write"}])
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    pairs = list(transfer.matched_rows())

    assert len(pairs) == 1
    assert pairs[0][0]["id"] == 0
    assert pairs[0][1] is not None and pairs[0][1]["id"] == 0


def test_composite_key_with_partially_blank_is_blank() -> None:
    """複合キーは **1要素でも空** なら空扱い（部分空のキーは照合に使えない）。

    write 側に「read と同じ複合キー値（部分空を含む）」を置く。 ``any()`` 実装なら
    両側のキーが空扱いで ``unmatched()`` 側へ流れる。 旧 ``all()`` 実装だと
    部分空のキーは照合対象になり、``("", "1")`` 同士が「一致した」と誤判定される。
    """
    source = Table(
        ["group", "id", "value"],
        [
            # 1要素目だけが空 → キーは空扱い
            {"group": "", "id": "1", "value": "group空"},
            # 2要素目だけが空 → キーは空扱い
            {"group": "A", "id": "", "value": "id空"},
        ],
    )
    destination = Table(
        ["group", "id", "value"],
        [
            # 1要素目だけが空 → キーは空扱い。read 側 ("", "1") と同じ値
            {"group": "", "id": "1", "value": "w-1"},
            # どちらも空ではない → キーは有効
            #  空ではない read 行と一致しないので only_in_write 側へ
            {"group": "A", "id": "1", "value": "w-2"},
        ],
    )
    transfer = Transfer(
        source,
        destination,
        {"value": "value"},
        read_key=["group", "id"],
        write_key=["group", "id"],
    )

    # 部分空の read 行はすべて only_in_read 側へ流れる
    unmatched = transfer.unmatched()
    extras_read = unmatched.only_in_read.read()
    assert {row["value"] for row in extras_read} == {"group空", "id空"}
    # matched は0件
    assert list(transfer.matched_rows()) == []
    # write 側 ("", "1") も空キー扱いなので only_in_write 側へ流れる
    extras_write = unmatched.only_in_write
    assert {row["value"] for row in extras_write} == {"w-1", "w-2"}


def test_multiple_blank_write_keys_do_not_raise_multiple_match() -> None:
    """write 側に空キーが複数あっても例外にならない。

    修正前は同じ空キー（``""``）同士が一致と判定され
    TransferDestinationMultipleMatchError で止まっていた。
    """
    source = Table(["id", "value"], [{"id": "1", "value": "new"}])
    destination = Table(
        ["id", "value"],
        [{"id": "", "value": ""}, {"id": "", "value": ""}, {"id": "1", "value": "old"}],
    )
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    # 例外が出ずに動く
    pairs = list(transfer.transfer_rows())
    assert pairs == [
        ({"id": "1", "value": "new"}, {"id": "1", "value": "old"}),
    ]
    # 空キーは only_in_write 側へ流れる
    assert len(transfer.unmatched().only_in_write) == 2


def test_unmatched_works_without_calling_other_iterators() -> None:
    """unmatched() は transfer_rows() / matched_rows() を呼ばずに動く。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}])
    destination = Table(
        ["id", "value"],
        [{"id": "1", "value": "old"}, {"id": "2", "value": "stale"}],
    )
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    extras = transfer.unmatched().only_in_write

    assert extras == [{"id": "2", "value": "stale"}]


def test_unmatched_only_in_read_append_appears_in_result() -> None:
    """unmatched().only_in_read を result().append() すると最終結果へ入る。"""
    source = Table(
        ["id", "name"],
        [{"id": "1", "name": "既存"}, {"id": "2", "name": "新規"}],
    )
    destination = Table(
        ["id", "name"],
        [{"id": "1", "name": ""}],
    )
    transfer = Transfer(
        source,
        destination,
        {"name": "name"},
        read_key="id",
        write_key="id",
    )

    for src, dst in transfer.matched_rows():
        transfer.apply_mapping(src, dst)

    # 既存行の転記後、write に無い read 行を新規行として追加する
    only_in_read = transfer.unmatched().only_in_read
    for read_row in only_in_read:
        transfer.result().append(dict(read_row))

    assert transfer.result().read() == [
        {"id": "1", "name": "既存"},
        {"id": "2", "name": "新規"},
    ]


def test_transfer_methods_do_not_mutate_input_tables() -> None:
    """unmatched() を呼んでも read / write Table は変わらない。"""
    source = Table(
        ["id", "value"],
        [{"id": "1", "value": "new"}, {"id": "2", "value": "extra"}],
    )
    destination = Table(
        ["id", "value"],
        [{"id": "1", "value": "old"}, {"id": "3", "value": "stale"}],
    )
    original_source = source.read()
    original_destination = destination.read()
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    unmatched = transfer.unmatched()
    list(unmatched.only_in_read.read())
    list(unmatched.only_in_write)

    assert source.read() == original_source
    assert destination.read() == original_destination


def test_result_called_before_unmatched_only_in_write_mutation_reflects() -> None:
    """``result()`` を先に呼んでも、その後 ``unmatched().only_in_write`` の ``write_row``
    を書き換えると ``result()`` 側に反映される（順序非依存）。

    ``Table.__init__`` は ``_normalize`` で行 dict をコピーするため、
    ``_result_table`` を ``Table(list(cols), self._working_rows, ...)`` で
    作ると、 ``_working_rows`` 側の dict をいくら書き換えても反映されない。
    ``Transfer.result()`` は作業 Table を直接返す形にしておき、
    ``unmatched().only_in_write`` / ``matched_rows()`` の ``write_row`` が
    ``Table._iter_rows_for_update()`` 経由で作業 Table の実体 dict を参照する
    ことでこの順序依存を潰す。
    """
    source = Table(["id", "v"], [{"id": "A001", "v": "new"}])
    destination = Table(
        ["id", "v"],
        [{"id": "A001", "v": "old"}, {"id": "A099", "v": "stale"}],
    )
    transfer = Transfer(source, destination, {"v": "v"}, read_key="id", write_key="id")

    # matched_rows で転記を確定（イテレータを最後まで進める）
    for read_row, write_row in transfer.matched_rows():
        transfer.apply_mapping(read_row, write_row)

    # ここで result() を呼ぶ（初回呼び出し）
    first = transfer.result()

    # その後で only_in_write の write_row を書き換える
    for write_row in transfer.unmatched().only_in_write:
        write_row["v"] = "転記元に無し"

    # result() に書き換えが反映されている
    assert first.read() == [
        {"id": "A001", "v": "new"},
        {"id": "A099", "v": "転記元に無し"},
    ]
    # 2回目の result() も同じインスタンスで、同じ結果
    assert transfer.result().read() == first.read()


def test_result_called_before_append_reflects_new_rows() -> None:
    """``result()`` を先に呼んでも、その後の ``result().append(...)`` は反映される。

    順序非依存の回帰テスト（``unmatched().only_in_write`` 書き換えと表裏）。
    """
    source = Table(
        ["id", "name"],
        [{"id": "1", "name": "既存"}, {"id": "2", "name": "新規"}],
    )
    destination = Table(
        ["id", "name"],
        [{"id": "1", "name": "old"}],
    )
    transfer = Transfer(
        source,
        destination,
        {"name": "name"},
        read_key="id",
        write_key="id",
    )

    for src, dst in transfer.matched_rows():
        transfer.apply_mapping(src, dst)

    # ここで result() を呼ぶ
    first = transfer.result()

    # その後で新規行を append する
    only_in_read = transfer.unmatched().only_in_read
    for read_row in only_in_read:
        first.append(dict(read_row))

    assert first.read() == [
        {"id": "1", "name": "既存"},
        {"id": "2", "name": "新規"},
    ]
    assert transfer.result().read() == first.read()


def test_unmatched_only_in_read_mutation_does_not_affect_inputs_or_result() -> None:
    """only_in_read の行を書き換えても read / result() には反映されない。

    only_in_read は ``Table`` で、 ``for read_row in only_in_read:`` のように
    iterate すると ``Table.__iter__`` がコピーを返すため、書き換えは
    only_in_read 自体にも反映されない。 これは only_in_write（作業 Table の
    実体行）と異なる振る舞いで、型が違う理由でもある。
    """
    source = Table(
        ["id", "value"],
        [{"id": "1", "value": "new"}, {"id": "2", "value": "extra"}],
    )
    destination = Table(["id", "value"], [{"id": "1", "value": "old"}])
    transfer = Transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")

    only_in_read = transfer.unmatched().only_in_read
    # Table を iterate すると Table.__iter__ が dict(row) for row in self._rows の
    # コピーを返すため、書き換えても only_in_read._rows には反映されない。
    for read_row in only_in_read:
        read_row["value"] = "書き換え"

    # only_in_read 自体は書き換わっていない
    assert only_in_read.read() == [{"id": "2", "value": "extra"}]
    # 元の read は変わらない
    assert source.read() == [
        {"id": "1", "value": "new"},
        {"id": "2", "value": "extra"},
    ]
    # result() も変わらない
    assert transfer.result().read() == [
        {"id": "1", "value": "old"},
    ]
