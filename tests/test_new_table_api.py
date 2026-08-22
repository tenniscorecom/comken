"""確定した Table / CSV / Transfer API の契約テスト。"""

import pytest

from comken.core.table import Table, Transfer, compare_tables
from comken.exceptions.table import (
    TableColumnNotFoundError,
    TableDuplicateKeyError,
    TableError,
    TableMergeColumnCollisionError,
    TableMergeSuffixError,
    TransferDestinationMultipleMatchError,
    TransferMappingError,
    TransferRowError,
)
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel


def test_table_supports_memory_operations() -> None:
    table = Table(
        ["id", "name", "group"],
        [{"id": "1", "name": "山田", "group": "A"}],
        types={"id": int},
    )

    assert table.read() == [{"id": 1, "name": "山田", "group": "A"}]
    assert table.count() == 1
    assert table.column("name") == ["山田"]
    assert table.select("id", "name").read() == [{"id": 1, "name": "山田"}]
    assert table.filter(lambda row: row["group"] == "A").count() == 1
    assert table.index("id")[1]["name"] == "山田"


def test_table_merge_concat_and_group_by() -> None:
    left = Table(["id", "value"], [{"id": 1, "value": "a"}])
    right = Table(["id", "label"], [{"id": 1, "label": "A"}])

    assert left.merge(right, on="id").read() == [{"id": 1, "value": "a", "label": "A"}]
    assert left.merge(right, on="id", how="inner").count() == 1
    with pytest.raises(TableError):
        left.concat(right)
    assert left.group_by("id")[1].count() == 1


def test_table_merge_keeps_overlapping_columns_with_suffixes() -> None:
    left = Table(["id", "name", "left_only"], [{"id": 1, "name": "旧", "left_only": "L"}])
    right = Table(
        ["id", "name", "right_only"],
        [{"id": 1, "name": "新", "right_only": "R"}],
    )

    result = left.merge(right, on="id")

    assert result.columns == ["id", "name_read", "left_only", "name_write", "right_only"]
    assert result.read() == [
        {"id": 1, "name_read": "旧", "left_only": "L", "name_write": "新", "right_only": "R"}
    ]
    assert left.column("name") == ["旧"]
    assert right.column("name") == ["新"]


def test_table_merge_left_fills_unmatched_right_columns() -> None:
    left = Table(["id", "value"], [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}])
    right = Table(["id", "label"], [{"id": 1, "label": "A"}])

    assert left.merge(right, on="id").read()[1] == {"id": 2, "value": "b", "label": ""}


def test_table_merge_rejects_invalid_suffixes_collision_and_missing_key() -> None:
    left = Table(["id", "name", "name_read"], [{"id": 1, "name": "a", "name_read": "x"}])
    right = Table(["id", "name"], [{"id": 1, "name": "b"}])
    with pytest.raises(TableMergeSuffixError):
        left.merge(right, on="id", suffixes=("", "_right"))
    with pytest.raises(TableMergeColumnCollisionError):
        left.merge(right, on="id")
    with pytest.raises(TableColumnNotFoundError):
        left.merge(right, on="missing")


def test_table_merge_accepts_custom_suffixes() -> None:
    read = Table(["id", "name"], [{"id": 1, "name": "old"}])
    write = Table(["id", "name"], [{"id": 1, "name": "new"}])

    result = read.merge(write, on="id", suffixes=("_before", "_after"))

    assert result.read() == [{"id": 1, "name_before": "old", "name_after": "new"}]


def test_csv_is_string_by_default_and_types_are_explicit(tmp_path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("id,name\n1,山田\n", encoding="utf-8-sig")

    with CSV(path, types={"id": int}) as csv_file:
        assert csv_file.read().read() == [{"id": 1, "name": "山田"}]


def test_csv_reads_pending_table_and_does_not_save_after_exception(tmp_path) -> None:
    path = tmp_path / "data.csv"
    path.write_text("id,date\n1,2026-08-22\n", encoding="utf-8-sig")

    with pytest.raises(RuntimeError), CSV(path, types={"id": int}) as csv_file:
        csv_file.replace([{"id": 2, "date": "2026-08-23"}])
        assert csv_file.read().read() == [{"id": 2, "date": "2026-08-23"}]
        raise RuntimeError
    assert "2026-08-22" in path.read_text(encoding="utf-8-sig")


def test_excel_create_table_uses_start_cell_and_its_actual_ref(tmp_path) -> None:
    path = tmp_path / "data.xlsx"
    with Excel(path) as excel:
        sheet = excel.create_data_sheet("data")
        sheet._worksheet["A1"] = "unrelated"
        table = sheet.create_table("items", Table(["id"], [{"id": 1}]), "C3")
        assert sheet._worksheet.tables["PY_T_items"].ref == "C3:C4"
        assert table.read().read() == [{"id": "1"}]


def test_transfer_supports_composite_update_add_and_duplicate() -> None:
    source = Table(
        ["group", "id", "value"],
        [
            {"group": "A", "id": 1, "value": "new"},
            {"group": "B", "id": 2, "value": "add"},
        ],
    )
    destination = Table(["group", "id", "value"], [{"group": "A", "id": 1, "value": "old"}])
    result = Transfer(
        source,
        destination,
        {"value": "value"},
        read_key=["group", "id"],
        write_key=["group", "id"],
    ).run()
    assert result.read() == [
        {"group": "A", "id": 1, "value": "new"},
    ]

    duplicate = Table(
        ["group", "id", "value"],
        [
            {"group": "A", "id": 1, "value": "one"},
            {"group": "A", "id": 1, "value": "two"},
        ],
    )
    with pytest.raises(TransferDestinationMultipleMatchError):
        Transfer(
            source,
            duplicate,
            {"value": "value"},
            read_key=["group", "id"],
            write_key=["group", "id"],
        ).run()


def test_transfer_returns_updated_table_without_mapping_items(tmp_path) -> None:
    source = Table(["id", "name"], [{"id": 1, "name": "山田"}])
    destination = Table(["id", "name"], [{"id": 1, "name": "旧"}])

    original_source = source.read()
    original_destination = destination.read()
    updated = Transfer(source, destination, {"name": "name"}, read_key="id", write_key="id").run()

    assert updated.read() == [{"id": 1, "name": "山田"}]
    assert updated is not destination
    assert source.read() == original_source
    assert destination.read() == original_destination


def test_transfer_maps_before_transform_and_skipped_changes_are_discarded() -> None:
    source = Table(["id", "name"], [{"id": 1, "name": "new"}])
    destination = Table(["id", "name"], [{"id": 1, "name": "old"}])

    def transform(_read_row, working_row):
        assert working_row["name"] == "new"
        working_row["name"] = "NEW"
        return Transfer.APPLY

    result = Transfer(source, destination, {"name": "name"}, read_key="id", write_key="id").run(
        transform=transform
    )
    assert result.read()[0]["name"] == "NEW"

    skipped = Transfer(source, destination, {"name": "name"}, read_key="id", write_key="id").run(
        transform=lambda _read, row: row.update(name="ignored") or False
    )
    assert skipped.read()[0]["name"] == "old"


def test_table_public_rows_are_copies_and_duplicate_keys_raise() -> None:
    table = Table(["id"], [{"id": 1}, {"id": 1}])
    first = next(iter(table))
    first["id"] = 2
    assert table.read()[0]["id"] == 1
    with pytest.raises(TableDuplicateKeyError):
        table.index("id")


def test_table_filter_predicate_cannot_change_source() -> None:
    table = Table(["id", "name"], [{"id": 1, "name": "before"}])

    def change_row(row):
        row["name"] = "changed"
        return True

    filtered = table.filter(change_row)

    assert table.read() == [{"id": 1, "name": "before"}]
    assert filtered.read() == [{"id": 1, "name": "before"}]


def test_compare_tables_accepts_different_column_order() -> None:
    read = Table(["id", "name", "area"], [{"id": 1, "name": "A", "area": "東"}])
    write = Table(["area", "id", "name"], [{"area": "東", "id": 1, "name": "A"}])

    comparison = compare_tables(read, write, read_key="id", write_key="id")

    assert comparison.same.count() == 1


def test_compare_tables_accepts_different_key_names() -> None:
    read = Table(["read_id", "name"], [{"read_id": 1, "name": "A"}])
    write = Table(["write_id", "name"], [{"write_id": 1, "name": "A"}])

    comparison = compare_tables(read, write, read_key="read_id", write_key="write_id")

    assert comparison.same.read() == [{"read_id": 1, "name": "A"}]


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


def test_transfer_rejects_missing_key_column_and_reports_source_row_number() -> None:
    read = Table(["id", "name"], [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}])
    write = Table(["id", "name"], [{"id": 1, "name": "old"}, {"id": 2, "name": "old"}])

    with pytest.raises(TableColumnNotFoundError):
        Transfer(read, write, {"name": "name"}, read_key="missing", write_key="id").run()
    with pytest.raises(TransferRowError, match="転記元の2件目"):
        Transfer(read, write, {"name": "name"}, read_key="id", write_key="id").run(
            transform=lambda row, _working: "invalid" if row["id"] == 2 else Transfer.APPLY
        )


def test_transfer_rows_and_compare_tables_are_directional() -> None:
    read = Table(
        ["id", "value"],
        [{"id": "1", "value": "new"}, {"id": "2", "value": "read-only"}],
    )
    write = Table(
        ["id", "value"],
        [{"id": "1", "value": "old"}, {"id": "3", "value": "write-only"}],
    )
    transfer = Transfer(read, write, {"value": "value"}, read_key="id", write_key="id")

    assert list(transfer.transfer_rows())[1][1] is None
    assert len(list(transfer.matched_rows())) == 1
    rows = list(transfer.transfer_rows())
    rows[0][1]["value"] = "edited"
    assert transfer.result().read()[0]["value"] == "edited"
    comparison = compare_tables(read, write, read_key="id", write_key="id")
    assert comparison.only_in_read.read() == [{"id": "2", "value": "read-only"}]
    assert comparison.only_in_write.read() == [{"id": "3", "value": "write-only"}]
    assert comparison.changed.count() == 1
