"""確定した Table / CSV / Transfer API の契約テスト。"""

import pytest

from comken.core.table import Table, Transfer
from comken.exceptions.table import TableError, TransferDestinationMultipleMatchError
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
    result = Transfer(source, destination, read_key=["group", "id"], write_key=["group", "id"]).run(
        mapping={"value": "value"}
    )
    assert result.read() == [
        {"group": "A", "id": 1, "value": "new"},
        {"group": "B", "id": 2, "value": "add"},
    ]

    duplicate = Table(
        ["group", "id", "value"],
        [
            {"group": "A", "id": 1, "value": "one"},
            {"group": "A", "id": 1, "value": "two"},
        ],
    )
    with pytest.raises(TransferDestinationMultipleMatchError):
        Transfer(source, duplicate, read_key=["group", "id"], write_key=["group", "id"]).run(
            mapping={"value": "value"}
        )


def test_transfer_returns_updated_table_without_mapping_items(tmp_path) -> None:
    source = Table(["id", "name"], [{"id": 1, "name": "山田"}])
    destination = Table(["id", "name"], [{"id": 1, "name": "旧"}])

    updated = Transfer(source, destination, read_key="id", write_key="id").run(
        mapping={"name": "name"}
    )

    assert updated.read() == [{"id": 1, "name": "山田"}]
