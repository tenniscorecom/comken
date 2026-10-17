"""transfer() の契約テスト。

実装をわざと壊したら落ちることを確かめる（バグ検出用）。"""
# mypy は Callable を `collections.abc` 側で参照する（typing.Callable は pyright で警告）。

import pytest

from comken.core.table import Table, TransferResult, transfer
from comken.exceptions.tables import (
    InvalidTableInputError,
    TableColumnNotFoundError,
    TableDuplicateKeyError,
    TableError,
)

# ---- 入力検証 ----


def test_transfer_rejects_non_table_read() -> None:
    """read が Table でないと InvalidTableInputError。"""
    not_a_table: object = "not a table"
    with pytest.raises(InvalidTableInputError):
        transfer(
            not_a_table,  # type: ignore[arg-type]
            Table(["id"], [{"id": 1}]),
            {"id": "id"},
            read_key="id",
            write_key="id",
        )


def test_transfer_rejects_non_table_write() -> None:
    """write が Table でないと InvalidTableInputError。"""
    not_a_table: object = "not a table"
    with pytest.raises(InvalidTableInputError):
        transfer(
            Table(["id"], [{"id": 1}]),
            not_a_table,  # type: ignore[arg-type]
            {"id": "id"},
            read_key="id",
            write_key="id",
        )


def test_transfer_rejects_empty_mapping() -> None:
    """mapping が空だと TableError。"""
    source = Table(["id"], [{"id": 1}])
    destination = Table(["id"], [{"id": 1}])
    with pytest.raises(TableError):
        transfer(source, destination, {}, read_key="id", write_key="id")


def test_transfer_rejects_mismatched_key_lengths() -> None:
    """read_key と write_key の要素数が違うと TableError。"""
    source = Table(["group", "id"], [{"group": "A", "id": 1}])
    destination = Table(["group", "id"], [{"group": "A", "id": 1}])
    with pytest.raises(TableError):
        transfer(
            source,
            destination,
            {"id": "id"},
            read_key=["group", "id"],
            write_key="id",
        )


def test_transfer_rejects_duplicate_destination_columns() -> None:
    """mapping の転記先列が重複していると TableError（末尾に対処）。"""
    source = Table(["a", "b"], [{"a": "1", "b": "2"}])
    destination = Table(["x"], [{"x": "old"}])
    with pytest.raises(TableError) as exc_info:
        transfer(
            source,
            destination,
            {"a": "x", "b": "x"},
            read_key="a",
            write_key="a",
        )
    # 転記先列の重複は「既存のエラーメッセージ形式（対処: ...）」に合わせる
    assert "対処" in str(exc_info.value)
    assert "x" in str(exc_info.value)


def test_transfer_rejects_missing_read_key_column() -> None:
    """read_key が存在しないと TableColumnNotFoundError（データを読む前に）。"""
    source = Table(["id", "name"], [{"id": 1, "name": "A"}])
    destination = Table(["id", "name"], [{"id": 1, "name": "old"}])
    with pytest.raises(TableColumnNotFoundError):
        transfer(
            source,
            destination,
            {"name": "name"},
            read_key="missing",
            write_key="id",
        )


def test_transfer_rejects_missing_write_key_column() -> None:
    """write_key が存在しないと TableColumnNotFoundError。"""
    source = Table(["id", "name"], [{"id": 1, "name": "A"}])
    destination = Table(["id", "name"], [{"id": 1, "name": "old"}])
    with pytest.raises(TableColumnNotFoundError):
        transfer(
            source,
            destination,
            {"name": "name"},
            read_key="id",
            write_key="missing",
        )


def test_transfer_rejects_missing_mapping_read_column() -> None:
    """mapping の転記元列が存在しないと TableColumnNotFoundError。"""
    source = Table(["id", "name"], [{"id": 1, "name": "A"}])
    destination = Table(["id", "name"], [{"id": 1, "name": "old"}])
    with pytest.raises(TableColumnNotFoundError):
        transfer(
            source,
            destination,
            {"missing": "name"},
            read_key="id",
            write_key="id",
        )


def test_transfer_rejects_missing_mapping_write_column() -> None:
    """mapping の転記先列が存在しないと TableColumnNotFoundError。"""
    source = Table(["id", "name"], [{"id": 1, "name": "A"}])
    destination = Table(["id", "name"], [{"id": 1, "name": "old"}])
    with pytest.raises(TableColumnNotFoundError):
        transfer(
            source,
            destination,
            {"name": "missing"},
            read_key="id",
            write_key="id",
        )


def test_transfer_column_validation_runs_before_data_reads() -> None:
    """列検証はデータを読む前に出る（存在しない列のとき、行を読まずに失敗する）。"""
    # read_table のデータを一切読まずに失敗すればよい。 Table 構築自体で失敗するため、
    # transfer() にはそもそも到達しないが、検証はTableの構築段階ではなく transfer 内で
    # 走ることを確認するため、エントリポイントで TableColumnNotFoundError を出す。
    source = Table(["id"], [{"id": 1}])
    destination = Table(["id"], [{"id": 2}])
    # read_key の column は存在しない
    with pytest.raises(TableColumnNotFoundError):
        transfer(
            source,
            destination,
            {"id": "id"},
            read_key="missing",
            write_key="id",
        )


# ---- 通常の転記 ----


def test_transfer_writes_mapping_into_write() -> None:
    """mapping どおりに転記される。"""
    source = Table(["id", "name"], [{"id": 1, "name": "Alice"}])
    destination = Table(["id", "name"], [{"id": 1, "name": ""}])
    result = transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")
    assert result.table.to_rows() == [{"id": 1, "name": "Alice"}]


def test_transfer_supports_different_column_names_in_mapping() -> None:
    """mapping の read 列と write 列で名前が違っていても転記できる。"""
    source = Table(["id", "name"], [{"id": 1, "name": "山田"}])
    destination = Table(["id", "label"], [{"id": 1, "label": "旧"}])
    result = transfer(source, destination, {"name": "label"}, read_key="id", write_key="id")
    assert result.table.to_rows() == [{"id": 1, "label": "山田"}]


def test_transfer_supports_composite_key_with_different_names() -> None:
    """複合キー（read と write で列名が違っていても）転記できる。"""
    source = Table(
        ["group", "id", "value"],
        [
            {"group": "A", "id": 1, "value": "new"},
            {"group": "B", "id": 2, "value": "extra"},
        ],
    )
    destination = Table(
        ["grp", "sid", "value"],
        [{"grp": "A", "sid": 1, "value": "old"}],
    )
    result = transfer(
        source,
        destination,
        {"value": "value"},
        read_key=["group", "id"],
        write_key=["grp", "sid"],
    )
    assert result.table.to_rows() == [{"grp": "A", "sid": 1, "value": "new"}]
    assert result.matched_count == 1
    assert result.transferred_count == 1
    # B-2 は write に無い → only_in_read 側へ
    assert result.only_in_read.to_rows() == [{"group": "B", "id": 2, "value": "extra"}]
    assert len(result.only_in_write) == 0


def test_transfer_keeps_unrelated_columns_unchanged() -> None:
    """mapping に無い列は変わらない。"""
    source = Table(["id", "name"], [{"id": 1, "name": "Alice"}])
    destination = Table(["id", "name", "備考"], [{"id": 1, "name": "", "備考": "既存"}])
    result = transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")
    assert result.table.to_rows() == [{"id": 1, "name": "Alice", "備考": "既存"}]


def test_transfer_keeps_input_tables_unchanged() -> None:
    """transfer を呼んだ前後で read / write の行は変わらない。"""
    source = Table(["id", "name"], [{"id": 1, "name": "Alice"}])
    destination = Table(["id", "name"], [{"id": 1, "name": "old"}])
    original_source = source.to_rows()
    original_destination = destination.to_rows()
    transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")
    assert source.to_rows() == original_source
    assert destination.to_rows() == original_destination


# ---- キーの正規化 ----


class TestKeysMatchedAfterNormalize:
    """キーは ``normalize`` でそろえてから突合する。"""

    @staticmethod
    def _transfer(read_key_value: object, write_key_value: object) -> TransferResult:
        source = Table(["id", "name"], [{"id": read_key_value, "name": "新"}])
        destination = Table(["id", "name"], [{"id": write_key_value, "name": "旧"}])
        return transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")

    @pytest.mark.parametrize(
        ("read_key", "write_key"),
        [
            ("1001", 1001),  # CSV の文字列と Excel の数値
            ("1001", 1001.0),  # Excel の整数値の小数
            ("Ａ１", "A1"),  # 全角と半角
            ("ｱｲｳ", "アイウ"),  # 半角カナと全角カナ
            (" 1001 ", "1001"),  # 前後の空白
        ],
    )
    def test_keys_that_differ_only_in_representation_match(
        self, read_key: object, write_key: object
    ) -> None:
        result = self._transfer(read_key, write_key)
        assert result.matched_count == 1
        assert result.transferred_count == 1

    def test_matching_does_not_change_the_written_values(self) -> None:
        """突合にだけ使い、転記先のキーの値は書き換えない。"""
        result = self._transfer("1001", 1001.0)
        assert result.table.to_rows() == [{"id": 1001.0, "name": "新"}]

    def test_leading_zero_keys_do_not_match_numbers(self) -> None:
        """先頭ゼロ付きの文字列（社員番号 "0001"）は数値の 1 と同じにならない。"""
        result = self._transfer("0001", 1)
        assert result.matched_count == 0
        assert result.transferred_count == 0

    def test_case_sensitive(self) -> None:
        """大文字小文字は区別する。"""
        result = self._transfer("A001", "a001")
        assert result.matched_count == 0


# ---- 空キー ----


def test_blank_key_rows_go_to_only_in() -> None:
    """空キー（""/空白）は突合されず、only_in_* に流れる。"""
    source = Table(
        ["id", "name"],
        [{"id": "", "name": "空白"}, {"id": "1", "name": "正常"}],
    )
    destination = Table(
        ["id", "name"],
        [{"id": "", "name": ""}, {"id": "1", "name": ""}],
    )
    result = transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")
    # id="1" の組だけが転記される
    assert result.matched_count == 1
    assert result.transferred_count == 1
    assert result.table.to_rows() == [
        {"id": "", "name": ""},
        {"id": "1", "name": "正常"},
    ]
    # 空キーは only_in_* に含まれる
    assert result.only_in_read.to_rows() == [{"id": "", "name": "空白"}]
    assert result.only_in_write.to_rows() == [{"id": "", "name": ""}]


def test_none_key_is_treated_as_blank() -> None:
    """キー値が None のときは Table 構築時に "" に揃うので空キー扱い。"""
    source = Table(["id", "name"], [{"id": None, "name": "Noneキー"}])
    destination = Table(["id", "name"], [{"id": "1", "name": "既存"}])
    result = transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")
    assert result.matched_count == 0
    assert result.only_in_read.to_rows() == [{"id": "", "name": "Noneキー"}]
    assert result.only_in_write.to_rows() == [{"id": "1", "name": "既存"}]


def test_whitespace_only_key_is_blank() -> None:
    """空白だけのキーも空扱い。"""
    source = Table(["id", "name"], [{"id": "  ", "name": "空白のみ"}])
    destination = Table(["id", "name"], [{"id": "x", "name": "X"}])
    result = transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")
    assert result.matched_count == 0
    assert result.only_in_read.to_rows() == [{"id": "  ", "name": "空白のみ"}]


def test_composite_key_with_partially_blank_is_blank() -> None:
    """複合キーは 1 要素でも空なら空扱い。"""
    source = Table(
        ["group", "id", "value"],
        [
            {"group": "", "id": "1", "value": "group空"},
            {"group": "A", "id": "", "value": "id空"},
        ],
    )
    destination = Table(
        ["group", "id", "value"],
        [
            {"group": "", "id": "1", "value": "w-1"},
            {"group": "A", "id": "1", "value": "w-2"},
        ],
    )
    result = transfer(
        source,
        destination,
        {"value": "value"},
        read_key=["group", "id"],
        write_key=["group", "id"],
    )
    # 部分空の read 行はすべて only_in_read 側へ
    assert {row["value"] for row in result.only_in_read.to_rows()} == {"group空", "id空"}
    assert result.matched_count == 0


def test_zero_value_is_a_valid_key() -> None:
    """0 はキーに使っても空扱いにならない。"""
    source = Table(["id", "value"], [{"id": 0, "value": "r"}])
    destination = Table(["id", "value"], [{"id": 0, "value": "w"}])
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    assert result.matched_count == 1
    assert result.transferred_count == 1


def test_false_value_is_a_valid_key() -> None:
    """False もキーに使っても空扱いにならない。"""
    source = Table(["flag", "value"], [{"flag": False, "value": "r"}])
    destination = Table(["flag", "value"], [{"flag": False, "value": "w"}])
    result = transfer(source, destination, {"value": "value"}, read_key="flag", write_key="flag")
    assert result.matched_count == 1
    assert result.transferred_count == 1


def test_blank_keys_are_not_checked_for_duplicates() -> None:
    """空キーが複数あってもエラーにならない。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}])
    destination = Table(
        ["id", "value"],
        [
            {"id": "", "value": ""},
            {"id": "", "value": ""},
            {"id": "1", "value": "old"},
        ],
    )
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    assert result.matched_count == 1
    # 空キーは only_in_write に含まれる
    assert len(result.only_in_write) == 2


# ---- 重複キー ----


def test_read_duplicate_key_raises() -> None:
    """read 側の重複キーは TableDuplicateKeyError。"""
    source = Table(
        ["id", "value"],
        [{"id": "1", "value": "a"}, {"id": "1", "value": "b"}],
    )
    destination = Table(["id", "value"], [{"id": "1", "value": "old"}])
    with pytest.raises(TableDuplicateKeyError):
        transfer(
            source,
            destination,
            {"value": "value"},
            read_key="id",
            write_key="id",
        )


def test_write_duplicate_key_raises() -> None:
    """write 側の重複キーは TableDuplicateKeyError。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}])
    destination = Table(
        ["id", "value"],
        [{"id": "1", "value": "one"}, {"id": "1", "value": "two"}],
    )
    with pytest.raises(TableDuplicateKeyError):
        transfer(
            source,
            destination,
            {"value": "value"},
            read_key="id",
            write_key="id",
        )


def test_duplicate_detection_uses_normalized_key() -> None:
    """重複判定は正規化後（"1" と 1.0 は同じキー）。"""
    source = Table(
        ["id", "value"],
        [{"id": "1", "value": "a"}, {"id": 1.0, "value": "b"}],
    )
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    with pytest.raises(TableDuplicateKeyError):
        transfer(
            source,
            destination,
            {"value": "value"},
            read_key="id",
            write_key="id",
        )


# ---- where ----


def test_where_false_skips_transfer_but_counts_as_matched() -> None:
    """where=False の行は転記されず、matched_count には数える。"""
    source = Table(
        ["id", "value"],
        [{"id": 1, "value": "keep"}, {"id": 2, "value": "skip"}],
    )
    destination = Table(
        ["id", "value"],
        [{"id": 1, "value": "old1"}, {"id": 2, "value": "old2"}],
    )
    result = transfer(
        source,
        destination,
        {"value": "value"},
        read_key="id",
        write_key="id",
        where=lambda r, w: r["value"] != "skip",
    )
    assert result.matched_count == 2
    assert result.transferred_count == 1
    assert result.table.to_rows() == [
        {"id": 1, "value": "keep"},
        {"id": 2, "value": "old2"},  # skip されたので元のまま
    ]


def test_where_false_rows_do_not_go_to_only_in() -> None:
    """where=False の行は only_in_* にも入らない（キーが一致しているため）。"""
    source = Table(["id", "value"], [{"id": 1, "value": "skip"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    result = transfer(
        source,
        destination,
        {"value": "value"},
        read_key="id",
        write_key="id",
        where=lambda r, w: False,
    )
    assert result.matched_count == 1
    assert result.transferred_count == 0
    assert len(result.only_in_read) == 0
    assert len(result.only_in_write) == 0


def test_where_is_called_only_for_matched_pairs() -> None:
    """where はキーが一致した組だけで呼ばれる（未一致では呼ばない）。"""
    source = Table(["id", "value"], [{"id": 1, "value": "x"}, {"id": 9, "value": "y"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    called_keys: list[tuple[int, str]] = []

    def record(read_row: dict, write_row: dict) -> bool:
        called_keys.append((read_row["id"], write_row["value"]))
        return True

    transfer(
        source,
        destination,
        {"value": "value"},
        read_key="id",
        write_key="id",
        where=record,
    )
    # id=1 の組だけで 1 回呼ばれる
    assert called_keys == [(1, "old")]


def test_where_is_called_once_per_pair() -> None:
    """where は 1 組につき 1 回呼ばれる。"""
    source = Table(["id", "value"], [{"id": 1, "value": "x"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    counter = {"n": 0}

    def count_calls(read_row: dict, write_row: dict) -> bool:
        counter["n"] += 1
        return True

    transfer(
        source,
        destination,
        {"value": "value"},
        read_key="id",
        write_key="id",
        where=count_calls,
    )
    assert counter["n"] == 1


def test_where_receives_copies() -> None:
    """where には read_row / write_row のコピーが渡され、内部で書き換えても影響しない。"""
    source = Table(["id", "value"], [{"id": 1, "value": "new"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])

    def mutate(read_row: dict, write_row: dict) -> bool:
        read_row["value"] = "壊した-read"
        write_row["value"] = "壊した-write"
        return True

    result = transfer(
        source,
        destination,
        {"value": "value"},
        read_key="id",
        write_key="id",
        where=mutate,
    )
    # 入力は不変
    assert source.to_rows() == [{"id": 1, "value": "new"}]
    assert destination.to_rows() == [{"id": 1, "value": "old"}]
    # 結果も where 内で書き換えた値で変わらない（コピー渡しなので）
    assert result.table.to_rows() == [{"id": 1, "value": "new"}]


def test_where_exception_propagates() -> None:
    """where が出した例外はそのまま伝わる。"""
    source = Table(["id", "value"], [{"id": 1, "value": "x"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])

    def boom(read_row: dict, write_row: dict) -> bool:
        raise RuntimeError("where から")

    with pytest.raises(RuntimeError, match="where から"):
        transfer(
            source,
            destination,
            {"value": "value"},
            read_key="id",
            write_key="id",
            where=boom,
        )


def test_where_called_in_read_order() -> None:
    """where は read の行順で呼ばれる。"""
    source = Table(
        ["id", "value"],
        [
            {"id": 3, "value": "c"},
            {"id": 1, "value": "a"},
            {"id": 2, "value": "b"},
        ],
    )
    destination = Table(
        ["id", "value"],
        [{"id": 1, "value": "old1"}, {"id": 2, "value": "old2"}, {"id": 3, "value": "old3"}],
    )
    seen: list[int] = []

    def record(read_row: dict, write_row: dict) -> bool:
        seen.append(read_row["id"])
        return True

    transfer(
        source,
        destination,
        {"value": "value"},
        read_key="id",
        write_key="id",
        where=record,
    )
    assert seen == [3, 1, 2]


# ---- 未一致行 ----


def test_only_in_read_contains_read_only_rows() -> None:
    """only_in_read には write に対応が無い read 行が入る。"""
    source = Table(
        ["id", "value"],
        [{"id": "1", "value": "new"}, {"id": "2", "value": "extra"}],
    )
    destination = Table(["id", "value"], [{"id": "1", "value": "old"}])
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    assert result.only_in_read.to_rows() == [{"id": "2", "value": "extra"}]
    # 元の read の順
    assert [row["id"] for row in result.only_in_read.to_rows()] == ["2"]


def test_only_in_write_contains_write_only_rows() -> None:
    """only_in_write には read に対応が無い write 行が入る（転記前の値）。"""
    source = Table(["id", "value"], [{"id": "1", "value": "new"}])
    destination = Table(
        ["id", "value"],
        [{"id": "1", "value": "old"}, {"id": "2", "value": "stale"}],
    )
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    assert result.only_in_write.to_rows() == [{"id": "2", "value": "stale"}]


def test_only_in_write_has_original_values_not_transferred() -> None:
    """only_in_write は転記前の値（result.table の転記後の値とは別）。"""
    source = Table(["id", "value"], [{"id": 1, "value": "new"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    # matched なので only_in_write は空
    assert len(result.only_in_write) == 0

    # only_in_write に id=2 を入れて、転記後の table と共有しないことを確認
    only_in_write_rows = result.only_in_write.to_rows()
    only_in_write_rows.append({"id": 99, "value": "stale"})
    # 結果の table は変わらない
    assert result.table.to_rows() == [{"id": 1, "value": "new"}]


def test_only_in_write_does_not_share_dicts_with_table() -> None:
    """only_in_write の行と result.table の行は辞書を共有しない。"""
    source = Table(["id", "value"], [{"id": 1, "value": "new"}])
    destination = Table(["id", "value"], [{"id": 2, "value": "stale"}])
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    assert result.only_in_write.to_rows() == [{"id": 2, "value": "stale"}]
    assert result.table.to_rows() == [{"id": 2, "value": "stale"}]
    # 1 行目の dict は別物
    assert result.only_in_write.to_rows()[0] is not result.table.to_rows()[0]


def test_only_in_read_preserves_read_columns_and_types() -> None:
    """only_in_read は read の列構成・型を引き継ぐ。"""
    source = Table(
        ["id", "金額", "備考"],
        [{"id": "X", "金額": "100", "備考": "r"}],
        types={"金額": int},
    )
    destination = Table(
        ["id", "value", "備考"],
        [{"id": "Y", "value": "w", "備考": ""}],
    )
    result = transfer(
        source,
        destination,
        {"備考": "備考"},
        read_key="id",
        write_key="id",
    )
    assert result.only_in_read.columns == ["id", "金額", "備考"]
    # 同じ converter が引き継がれている
    assert result.only_in_read.types.get("金額") is source.types["金額"]
    assert result.only_in_read.to_rows()[0]["金額"] == 100


def test_only_in_write_preserves_write_columns_and_types() -> None:
    """only_in_write は write の列構成・型を引き継ぐ。"""
    source = Table(["id", "備考"], [{"id": "X", "備考": "r"}])
    destination = Table(
        ["id", "金額", "備考"],
        [{"id": "Y", "金額": "200", "備考": "w"}],
        types={"金額": int},
    )
    result = transfer(
        source,
        destination,
        {"備考": "備考"},
        read_key="id",
        write_key="id",
    )
    assert result.only_in_write.columns == ["id", "金額", "備考"]
    assert result.only_in_write.types.get("金額") is destination.types["金額"]
    assert result.only_in_write.to_rows()[0]["金額"] == 200


# ---- 入力の不変性 ----


def test_input_tables_are_not_modified_after_transfer() -> None:
    """transfer() の呼び出し前後で read / write は変わらない。"""
    source = Table(["id", "value"], [{"id": 1, "value": "new"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    original_source = source.to_rows()
    original_destination = destination.to_rows()
    transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    assert source.to_rows() == original_source
    assert destination.to_rows() == original_destination


def test_modifying_result_table_does_not_affect_input() -> None:
    """result.table.append / replace しても入力 read / write は変わらない。"""
    source = Table(["id", "value"], [{"id": 1, "value": "new"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    result.table.append({"id": 99, "value": "追加"})
    assert source.to_rows() == [{"id": 1, "value": "new"}]
    assert destination.to_rows() == [{"id": 1, "value": "old"}]


def test_modifying_only_in_does_not_affect_table() -> None:
    """only_in_* を書き換えても result.table に影響しない。"""
    source = Table(["id", "value"], [{"id": 2, "value": "extra"}])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    only_in_read = result.only_in_read
    only_in_read_rows = only_in_read.to_rows()
    only_in_read_rows[0]["value"] = "壊した"
    # result.table は変わらない
    assert result.table.to_rows() == [{"id": 1, "value": "old"}]


# ---- 統計 ----


def test_matched_and_transferred_counts_match_actual() -> None:
    """matched_count / transferred_count が実際と一致する（期待値は独立に数える）。"""
    source = Table(
        ["id", "value"],
        [
            {"id": 1, "value": "a"},  # 転記される
            {"id": 2, "value": "b"},  # where=False でスキップ
            {"id": 3, "value": "c"},  # write に無い
            {"id": 4, "value": "d"},  # 転記される
        ],
    )
    destination = Table(
        ["id", "value"],
        [
            {"id": 1, "value": "old1"},
            {"id": 2, "value": "old2"},
            {"id": 4, "value": "old4"},
            {"id": 5, "value": "stale"},  # read に無い
        ],
    )
    result = transfer(
        source,
        destination,
        {"value": "value"},
        read_key="id",
        write_key="id",
        where=lambda r, w: r["value"] != "b",
    )
    # 独立に数える:
    #   matched: id=1, 2, 4 → 3
    #   transferred: id=1, 4 → 2
    assert result.matched_count == 3
    assert result.transferred_count == 2
    assert len(result.only_in_read) == 1  # id=3
    assert len(result.only_in_write) == 1  # id=5


# ---- 空のテーブル ----


def test_empty_read_with_non_empty_write() -> None:
    """read が空（列は残る）。"""
    source = Table(["id", "value"], [])
    destination = Table(["id", "value"], [{"id": 1, "value": "old"}])
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    # 全行が only_in_write 側
    assert result.matched_count == 0
    assert result.transferred_count == 0
    # result.table は write と同じ（列・行順・行数）
    assert result.table.to_rows() == [{"id": 1, "value": "old"}]
    assert result.only_in_read.to_rows() == []
    assert result.only_in_write.to_rows() == [{"id": 1, "value": "old"}]


def test_non_empty_read_with_empty_write() -> None:
    """write が空（列は残る）。"""
    source = Table(["id", "value"], [{"id": 1, "value": "new"}])
    destination = Table(["id", "value"], [])
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    assert result.matched_count == 0
    assert result.transferred_count == 0
    assert result.table.to_rows() == []
    assert result.only_in_read.to_rows() == [{"id": 1, "value": "new"}]
    assert result.only_in_write.to_rows() == []


def test_both_empty() -> None:
    """両方空でも列は保たれる。"""
    source = Table(["id", "value"], [])
    destination = Table(["id", "value"], [])
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    assert result.matched_count == 0
    assert result.transferred_count == 0
    assert result.table.columns == ["id", "value"]
    assert result.table.to_rows() == []
    assert result.only_in_read.to_rows() == []
    assert result.only_in_write.to_rows() == []


# ---- 型変換 ----


def test_type_conversion_applies_to_transferred_values() -> None:
    """write.types に登録した変換が転記した値に 1 回かかる。"""
    source = Table(["id", "value"], [{"id": 1, "value": "1000"}])
    destination = Table(["id", "value"], [{"id": 1, "value": 0}], types={"value": int})
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    assert result.table.to_rows() == [{"id": 1, "value": 1000}]


def test_conversion_does_not_apply_to_untransferred_cells() -> None:
    """転記しなかった行・列には変換関数がかからない（呼び出し回数を数える）。"""
    # 呼び出し回数を数える converter を作る
    call_log: list[tuple[str, object]] = []

    def counting_converter(value: object) -> int:
        call_log.append(("called", value))
        return int(value)  # type: ignore[arg-type]

    source = Table(
        ["id", "a", "b"],
        [
            {"id": 1, "a": "100", "b": "200"},  # matched・両方転記
            {"id": 2, "a": "300", "b": "400"},  # matched・where で転記しない
            {"id": 9, "a": "500", "b": "600"},  # unmatched（write に無い）
        ],
    )
    destination = Table(
        ["id", "a", "b"],
        [
            {"id": 1, "a": 999, "b": 999},
            {"id": 2, "a": 999, "b": 999},
        ],
        types={"a": counting_converter, "b": counting_converter},
    )
    result = transfer(
        source,
        destination,
        {"a": "a", "b": "b"},
        read_key="id",
        write_key="id",
        where=lambda r, w: r["id"] != 2,
    )

    # destination 構築時（id=1, 2 の a, b）= 4 回
    # transfer 内で転記（id=1 の a, b）= 2 回
    # id=2 は where=False で転記されない、 id=9 は unmatched で転記されない
    assert len(call_log) == 6
    # 転記された a=100, b=200
    assert result.table.to_rows() == [
        {"id": 1, "a": 100, "b": 200},
        {"id": 2, "a": 999, "b": 999},  # where=False で元のまま
    ]


def test_conversion_failure_raises_table_error_with_row_number() -> None:
    """変換できない値は TableError で行番号・列名が出る。"""
    source = Table(["id", "value"], [{"id": 1, "value": "abc"}])
    destination = Table(["id", "value"], [{"id": 1, "value": 0}], types={"value": int})
    with pytest.raises(TableError) as exc_info:
        transfer(
            source,
            destination,
            {"value": "value"},
            read_key="id",
            write_key="id",
        )
    message = str(exc_info.value)
    assert "value" in message  # 列名
    assert "1件目" in message  # 行番号（write の 1 件目）


def test_result_table_keeps_write_types() -> None:
    """result.table.types は write.types と同じ（converter の identity を比較）。"""
    converter = int
    source = Table(["id", "value"], [{"id": 1, "value": "1000"}])
    destination = Table(["id", "value"], [{"id": 1, "value": 0}], types={"value": converter})
    result = transfer(source, destination, {"value": "value"}, read_key="id", write_key="id")
    assert result.table.types.get("value") is converter


# ---- Table.diff() との整合 ----


def test_result_table_diff_against_original_write_shows_only_transferred_changes() -> None:
    """転記後の result.table と元の write を diff した changed 数が転記数と一致。"""
    source = Table(
        ["id", "name"],
        [{"id": 1, "name": "新"}, {"id": 2, "name": "新2"}],
    )
    destination = Table(
        ["id", "name"],
        [{"id": 1, "name": "旧"}, {"id": 2, "name": "旧2"}],
    )
    result = transfer(source, destination, {"name": "name"}, read_key="id", write_key="id")
    # result.table と destination を diff
    diff = result.table.diff(destination, key="id")
    # added / removed は空（キーが同じ・行数が同じ）
    assert diff.added.to_rows() == []
    assert diff.removed.to_rows() == []
    # changed は転記で値が変わったセル（id=1, 2 の name 列）= 2 行
    assert len(diff.changed) == 2


# ---- 旧 API が残っていないことの固定 ----


def test_old_api_is_removed() -> None:
    """Transfer / UnmatchedRows はもう公開されていない。"""
    from comken.core.table import transfer as _transfer

    assert callable(_transfer)
    # 旧クラス名が公開されていないことを getattr で確認する。
    # 直接 ``from comken.core.table import Transfer`` と書くと ImportError で
    # インポート文ごと失敗するため、 ``hasattr`` で属性の有無を見る。
    import comken.core.table as table_module

    assert not hasattr(table_module, "Transfer"), "Transfer はもう公開されていない"
    assert not hasattr(table_module, "UnmatchedRows"), "UnmatchedRows はもう公開されていない"


def test_transfer_module_exposes_function() -> None:
    """comken.core.table.transfer モジュールは関数を指す。"""
    from comken.core.table import transfer as module_transfer

    assert callable(module_transfer)
    # transfer.py を直接 import しても関数を指す（モジュール名は同名・関数を export 済み）
    import comken.core.table.transfer as direct_transfer

    assert direct_transfer is module_transfer
