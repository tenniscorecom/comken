"""Excel の ``engine="com"`` 経路（pywin32 経由）の契約テスト。

CI など pywin32 / Excel が無い環境では ``ExcelCOMHandler`` の import 自体に
失敗するため、ファイル先頭で ``win32com`` の import を要求する。``importorskip``
に失敗したテストファイルは pytest が丸ごと skip 扱いにする。
"""

from __future__ import annotations

import warnings
from typing import Any
from unittest.mock import MagicMock

import pytest

# pywin32 が無い CI ではこの import 時点で失敗してテストファイル全体が skip される。
# ``Excel.__enter__`` は関数内 import するので、ここでは直接使わないが、
# ファイル先頭で import できることを確認することで ``engine='com'`` のテスト群を
# まとめて skip できる。
win32com = pytest.importorskip("win32com")

from comken.exceptions import (  # noqa: E402
    ExcelFileNotFoundError,
    InvalidTableOperationError,
)
from comken.toolbox.excel import Excel  # noqa: E402


class _FakeSheets:
    """``ExcelCOMHandler`` 互換の ``_wb.Sheets`` スタブ。

    テスト用にシート名一覧・件数・イテレーションを提供する。
    """

    def __init__(self, names: list[str]) -> None:
        self._names = list(names)

    @property
    def Count(self) -> int:
        return len(self._names)

    def __iter__(self) -> _FakeSheets:
        self._index = 0
        return self

    def __next__(self) -> _FakeSheet:
        if self._index >= len(self._names):
            raise StopIteration
        sheet = _FakeSheet(self._names[self._index])
        self._index += 1
        return sheet


class _FakeSheet:
    def __init__(self, name: str) -> None:
        self.Name = name


def _build_com_excel(
    tmp_path, *, names: list[str], read_calls: list[dict[str, Any]] | None = None
) -> tuple[Excel, MagicMock]:
    """``engine='com'`` でテスト用の Excel を開く。

    ``ExcelCOMHandler`` を ``MagicMock`` で差し替え、Excel 実機が無い環境でも
    ``__enter__`` を通過できるようにする。``.read()`` の戻り値は呼び出し時に
    履歴を残すため、テスト側で検証できる。
    """
    path = tmp_path / "book.xlsx"
    path.write_bytes(b"")  # ファイルが存在することだけ示す（中身は使わない）
    read_calls_ref: list[dict[str, Any]] = read_calls if read_calls is not None else []

    fake_sheets = _FakeSheets(names)
    fake_com = MagicMock()
    fake_com._wb.Sheets = fake_sheets
    fake_com.last_row.side_effect = lambda name: 5
    fake_com.read.side_effect = lambda sheet_name, header_row=1: (
        read_calls_ref.append({"sheet": sheet_name, "header_row": header_row}) or MagicMock()
    )

    excel = Excel(path, engine="com", local_copy=False)
    excel._com_handler = fake_com  # __enter__ を経由せず直接差し込む
    excel._is_open = True
    excel._is_closed = False
    return excel, fake_com


def test_com_engine_list_sheets_returns_all_names(tmp_path) -> None:
    """``list_sheets()`` が ``_wb.Sheets`` の名前を順序通り返すこと。"""
    excel, _ = _build_com_excel(tmp_path, names=["案件一覧", "集計", "PY_顧客"])
    assert excel.list_sheets() == ["案件一覧", "集計", "PY_顧客"]


def test_com_engine_count_sheets_returns_count(tmp_path) -> None:
    """``count_sheets()`` が ``Sheets.Count`` を返すこと。"""
    excel, _ = _build_com_excel(tmp_path, names=["Sheet1", "Sheet2", "Sheet3"])
    assert excel.count_sheets() == 3


def test_com_engine_last_row_delegates_to_handler(tmp_path) -> None:
    """``last_row(sheet_name)`` が ``ExcelCOMHandler.last_row`` を呼ぶこと。"""
    excel, fake_com = _build_com_excel(tmp_path, names=["Sheet1"])
    assert excel.last_row("Sheet1") == 5
    fake_com.last_row.assert_called_once_with("Sheet1")


def test_com_engine_exists_sheet_finds_matching_name(tmp_path) -> None:
    """``exists_sheet(name)`` がシートの有無を返すこと。"""
    excel, _ = _build_com_excel(tmp_path, names=["Sheet1", "Sheet2"])
    assert excel.exists_sheet("Sheet1") is True
    assert excel.exists_sheet("存在しない") is False


def test_com_engine_read_delegates_to_handler(tmp_path) -> None:
    """``engine='com'`` の ``read()`` は ``ExcelCOMHandler.read`` に委譲すること。"""
    excel, fake_com = _build_com_excel(tmp_path, names=["Sheet1"])
    excel.read("Sheet1", header_row=2)
    fake_com.read.assert_called_once_with("Sheet1", header_row=2)


def test_com_engine_local_copy_none_warns_once(tmp_path) -> None:
    """``engine='com'`` で ``local_copy`` 未指定のとき警告が ``__enter__`` で1度出ること。

    警告は ``__enter__`` で出る。``ExcelCOMHandler`` を ``MagicMock`` で
    差し替えて実 Excel を起動せずに ``__enter__`` を完走させ、``warnings``
    の記録を検証する。同じインスタンスで ``__enter__`` を2回呼んでも
    2回目は警告が出ない（クラスパターン対策）。
    """
    path = tmp_path / "book.xlsx"
    path.write_bytes(b"")

    fake_com = MagicMock()
    fake_com.__enter__.return_value = fake_com
    fake_com.__exit__.return_value = False

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "comken.toolbox.windows.handler.ExcelCOMHandler",
            MagicMock(return_value=fake_com),
        )
        with (
            pytest.warns(UserWarning, match="local_copy を明示"),
            Excel(path, engine="com", local_copy=None) as excel,
        ):
            # 既に開いている状態で __enter__ を再呼び出ししても警告は出ない
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                excel.__enter__()
            assert not [w for w in caught if "local_copy を明示" in str(w.message)]


def test_com_engine_local_copy_explicit_does_not_warn(tmp_path) -> None:
    """``local_copy=True`` または ``False`` を明示したときは警告が出ないこと。"""
    path = tmp_path / "book.xlsx"
    path.write_bytes(b"")
    fake_com = MagicMock()
    fake_com.__enter__.return_value = fake_com
    fake_com.__exit__.return_value = False

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "comken.toolbox.windows.handler.ExcelCOMHandler",
                MagicMock(return_value=fake_com),
            )
            with Excel(path, engine="com", local_copy=False):
                pass
    assert not [w for w in caught if "local_copy を明示" in str(w.message)]


def test_openpyxl_engine_com_handler_raises(tmp_path) -> None:
    """``engine='openpyxl'`` の ``Excel`` で ``com_handler`` を触ると例外。"""
    path = tmp_path / "book.xlsx"
    with Excel(path) as excel, pytest.raises(InvalidTableOperationError, match="com_handler"):
        _ = excel.com_handler


def test_com_engine_sheet_method_raises(tmp_path) -> None:
    """``engine='com'`` で ``sheet()`` を呼ぶと ``InvalidTableOperationError``。"""
    excel, _ = _build_com_excel(tmp_path, names=["Sheet1"])
    with pytest.raises(InvalidTableOperationError, match="engine='com'"):
        excel.sheet("Sheet1")


def test_com_engine_requires_existing_file(tmp_path) -> None:
    """``engine='com'`` で存在しないファイルを ``__enter__`` するとエラー。"""
    missing = tmp_path / "missing.xlsx"
    excel = Excel(missing, engine="com", local_copy=False)
    with pytest.raises(ExcelFileNotFoundError):
        excel.__enter__()
