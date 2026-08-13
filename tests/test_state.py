from pathlib import Path

import pytest

from comken import dry_run
from comken.exceptions import (
    StateFileCorruptedError,
    StateLowerCaseNameError,
    StateValueTypeError,
)
from comken.state import State


class TestState:
    def test_returns_default_when_file_does_not_exist(self, tmp_path: Path) -> None:
        state = State(tmp_path / "state.ini")

        assert state.get("MISSING") is None
        assert state.get("MISSING", default="初期値") == "初期値"

    @pytest.mark.parametrize(
        ("value", "expected_type"),
        [
            ("data.csv", str),
            (42, int),
            (3.5, float),
            (True, bool),
            (["a", "b"], list),
            ("2026-08-13", str),
        ],
    )
    def test_round_trips_with_same_type(
        self, tmp_path: Path, value: bool | int | float | str | list[str], expected_type: type
    ) -> None:
        path = tmp_path / "state.ini"
        State(path).set("VALUE", value)

        actual = State(path).get("VALUE")

        assert actual == value
        assert type(actual) is expected_type

    def test_dry_run_does_not_change_file_or_memory(self, tmp_path: Path) -> None:
        path = tmp_path / "state.ini"
        state = State(path)
        state.set("LAST_FILE", "before.csv")
        before = path.read_bytes()

        with dry_run():
            state.set("LAST_FILE", "after.csv")

        assert path.read_bytes() == before
        assert state.get("LAST_FILE") == "before.csv"

    @pytest.mark.parametrize("value", [[1, 2, 3], {"key": "value"}, [["nested"]]])
    def test_rejects_unsupported_value_without_changing_file(
        self, tmp_path: Path, value: object
    ) -> None:
        path = tmp_path / "state.ini"
        state = State(path)
        state.set("VALUE", "before")
        before = path.read_bytes()

        with pytest.raises(StateValueTypeError):
            state.set("VALUE", value)  # type: ignore[arg-type]  # 実行時の型検証を確認する

        assert path.read_bytes() == before
        assert state.get("VALUE") == "before"

    def test_rejects_unsupported_value_during_dry_run(self, tmp_path: Path) -> None:
        state = State(tmp_path / "state.ini")

        with dry_run(), pytest.raises(StateValueTypeError):
            state.set("VALUE", [1])  # type: ignore[list-item]  # 実行時の型検証を確認する

    def test_raises_dedicated_error_for_corrupted_file(self, tmp_path: Path) -> None:
        path = tmp_path / "state.ini"
        path.write_text("[STATE\nLAST_FILE = broken", encoding="utf-8")

        with pytest.raises(StateFileCorruptedError):
            State(path)

    def test_does_not_leave_temporary_file(self, tmp_path: Path) -> None:
        path = tmp_path / "state.ini"

        State(path).set("LAST_FILE", "data.csv")

        assert list(tmp_path.glob("state.ini.*.tmp")) == []

    def test_rejects_lower_case_key(self, tmp_path: Path) -> None:
        with pytest.raises(StateLowerCaseNameError):
            State(tmp_path / "state.ini").set("last_file", "data.csv")
