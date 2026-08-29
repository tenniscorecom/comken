"""確定した Table / CSV API の契約テスト。

Transfer 関連は tests/test_transfer.py へ移した。
"""

import pytest

from comken.core.table import Table, compare_tables
from comken.exceptions.table import (
    TableDuplicateKeyError,
    TableError,
    TransferMappingError,
)
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel


def test_table_supports_memory_operations() -> None:
    table = Table(
        ["id", "name", "group"],
        [{"id": "1", "name": "山田", "group": "A"}],
        types={"id": int},
    )

    assert table.read_rows() == [{"id": 1, "name": "山田", "group": "A"}]
    assert table[0] == {"id": 1, "name": "山田", "group": "A"}
    table[0]["id"] = 2
    assert table[0]["id"] == 1
    with pytest.raises(IndexError):
        table[1]
    assert table.count() == 1
    assert table.column("name") == ["山田"]
    assert table.select("id", "name").read_rows() == [{"id": 1, "name": "山田"}]
    assert table.filter(lambda row: row["group"] == "A").count() == 1
    assert table.index("id")[1]["name"] == "山田"


def test_table_concat_and_group_by() -> None:
    left = Table(["id", "value"], [{"id": 1, "value": "a"}])
    right = Table(["id", "label"], [{"id": 1, "label": "A"}])

    with pytest.raises(TableError):
        left.concat(right)
    assert left.group_by("id")[1].count() == 1


def test_csv_is_string_by_default_and_types_are_explicit(tmp_path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("id,name\n1,山田\n", encoding="utf-8-sig")

    with CSV(path, types={"id": int}) as csv_file:
        assert csv_file.read() == [{"id": 1, "name": "山田"}]


def test_csv_reads_pending_table_and_does_not_save_after_exception(tmp_path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("id,date\n1,2026-08-22\n", encoding="utf-8-sig")

    with pytest.raises(RuntimeError), CSV(path, types={"id": int}) as csv_file:
        csv_file.replace([{"id": 2, "date": "2026-08-23"}])
        assert csv_file.read() == [{"id": 2, "date": "2026-08-23"}]
        raise RuntimeError
    assert "2026-08-22" in path.read_text(encoding="utf-8-sig")


def test_excel_create_table_uses_start_cell_and_its_actual_ref(tmp_path) -> None:
    path = tmp_path / "data.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_data_sheet("data")
        sheet._worksheet["A1"] = "unrelated"
        table = sheet.create_table("items", Table(["id"], [{"id": 1}]), "C3")
        assert sheet._worksheet.tables["PY_T_items"].ref == "C3:C4"
        assert table.read() == [{"id": "1"}]


def test_table_public_rows_are_copies_and_duplicate_keys_raise() -> None:
    table = Table(["id"], [{"id": 1}, {"id": 1}])
    first = next(iter(table))
    first["id"] = 2
    assert table.read_rows()[0]["id"] == 1
    with pytest.raises(TableDuplicateKeyError):
        table.index("id")


def test_table_filter_predicate_cannot_change_source() -> None:
    table = Table(["id", "name"], [{"id": 1, "name": "before"}])

    def change_row(row):
        row["name"] = "changed"
        return True

    filtered = table.filter(change_row)

    assert table.read_rows() == [{"id": 1, "name": "before"}]
    assert filtered.read_rows() == [{"id": 1, "name": "before"}]


def test_compare_tables_accepts_different_column_order() -> None:
    read = Table(["id", "name", "area"], [{"id": 1, "name": "A", "area": "東"}])
    write = Table(["area", "id", "name"], [{"area": "東", "id": 1, "name": "A"}])

    comparison = compare_tables(read, write, read_key="id", write_key="id")

    assert comparison.same.count() == 1


def test_compare_tables_accepts_different_key_names() -> None:
    read = Table(["read_id", "name"], [{"read_id": 1, "name": "A"}])
    write = Table(["write_id", "name"], [{"write_id": 1, "name": "A"}])

    comparison = compare_tables(read, write, read_key="read_id", write_key="write_id")

    assert comparison.same.read_rows() == [{"read_id": 1, "name": "A"}]


@pytest.mark.parametrize("duplicate_side", ["read", "write"])
def test_compare_tables_rejects_duplicate_keys_on_both_sides(duplicate_side) -> None:
    unique = Table(["id", "name"], [{"id": 1, "name": "A"}])
    duplicate = Table(["id", "name"], [{"id": 1, "name": "A"}, {"id": 1, "name": "B"}])
    read, write = (duplicate, unique) if duplicate_side == "read" else (unique, duplicate)

    with pytest.raises(TableDuplicateKeyError):
        compare_tables(read, write, read_key="id", write_key="id")


def test_compare_tables_rejects_generated_column_collision() -> None:
    read = Table(["id", "name", "write_name"], [{"id": 1, "name": "A", "write_name": "x"}])
    write = Table(["id", "name", "write_name"], [{"id": 1, "name": "B", "write_name": "y"}])

    with pytest.raises(TransferMappingError):
        compare_tables(read, write, read_key="id", write_key="id")


def test_select_keeps_only_types_for_selected_columns() -> None:
    """``select()`` は選択されなかった列の変換関数まで持ち回らない。"""
    table = Table(
        ["id", "value"],
        [{"id": "1", "value": "1"}],
        types={"id": int, "value": int},
    )

    selected = table.select("id")

    assert selected.read_rows() == [{"id": 1}]
    # 選択した列の変換関数だけが残る（value の int は持ち越さない）
    assert selected.types == {"id": int}
    selected.append({"id": "2"})
    assert selected.read_rows() == [{"id": 1}, {"id": 2}]


def test_table_equals_table_by_content() -> None:
    """同じ列と全行を持つ ``Table`` は ``==`` で ``True`` になる（同一性ではない）。"""
    a = Table(["id", "name"], [{"id": 1, "name": "山田"}, {"id": 2, "name": "鈴木"}])
    b = Table(["id", "name"], [{"id": 1, "name": "山田"}, {"id": 2, "name": "鈴木"}])

    assert a == b
    assert b == a


def test_table_not_equal_when_column_order_differs() -> None:
    """列の順番が違う ``Table`` は等しくない（``concat`` が列順を揃える設計と揃える）。"""
    a = Table(["id", "name"], [{"id": 1, "name": "山田"}])
    b = Table(["name", "id"], [{"name": "山田", "id": 1}])

    assert a != b


def test_table_not_equal_when_rows_differ() -> None:
    """行が違えば等しくない。"""
    a = Table(["id"], [{"id": 1}])
    b = Table(["id"], [{"id": 2}])

    assert a != b
    assert a != b


def test_table_equals_ignores_types() -> None:
    """``types`` は比較に含めない（変換関数は表の中身ではないため）。"""
    with_types = Table(["id"], [{"id": "1"}], types={"id": int})
    without_types = Table(["id"], [{"id": 1}])

    # 実行時の値（types 適用後）で比較される = 等しい
    assert with_types.read_rows() == without_types.read_rows()
    assert with_types == without_types


def test_table_equals_list_still_works() -> None:
    """``Table == list[dict]`` の経路は今までのとおり動く。"""
    table = Table(["id", "name"], [{"id": 1, "name": "山田"}])

    assert table == [{"id": 1, "name": "山田"}]
    assert table != [{"id": 2, "name": "山田"}]


def test_table_not_equal_to_unrelated_type() -> None:
    """``str`` や ``int`` など無関係な型との比較は ``NotImplemented`` を返す。"""
    table = Table(["id"], [{"id": 1}])

    # ``!=`` は ``NotImplemented`` を ``True``（等しくない）に畳む
    assert table != "string"
    assert table != 42
    # ``==`` も ``NotImplemented`` を ``False`` に畳む
    assert table != "string"
