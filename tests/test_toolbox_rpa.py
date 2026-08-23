"""`comken.toolbox.rpa` の互換シム動作を確認する。

旧パスから名前を取り出すと FutureWarning が出るが、
``import comken.toolbox.rpa`` だけでは警告が出ない。
旧例外名は新例外と**同じクラス**として解決されるため、
``except RpaLibraryNotFoundError`` で新しい ``InternalLibraryNotFoundError`` も捕捉できる。
"""

from __future__ import annotations

import importlib
import warnings

import pytest

import comken
import comken.exceptions
import comken.toolbox.rpa as legacy_rpa
from comken.internal.exceptions import InternalLibraryNotFoundError


def test_legacy_rpa_module_import_is_warning_free() -> None:
    """``import comken.toolbox.rpa`` だけでは警告が出ない。"""
    # importlib.reload で再 import し、import 中に出る警告を capture する。
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        importlib.reload(legacy_rpa)
    assert all("comken.toolbox.rpa" not in str(w.message) for w in recorded), (
        f"import 中に警告が出た: {[str(w.message) for w in recorded]}"
    )


def test_legacy_rpa_attribute_access_emits_future_warning() -> None:
    """旧パスから backoffice / intranet を取り出すと FutureWarning。"""
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        # 旧パスを経由して backoffice を取得
        _ = legacy_rpa.backoffice
    assert any(issubclass(w.category, FutureWarning) for w in recorded), (
        "FutureWarning が出なかった"
    )


def test_legacy_rpa_rpa_library_name_emits_future_warning() -> None:
    """RPA_LIBRARY_NAME も旧パスから取り出すと FutureWarning。"""
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        _ = legacy_rpa.RPA_LIBRARY_NAME
    assert any(issubclass(w.category, FutureWarning) for w in recorded)


def test_legacy_rpa_delegates_to_internal_rpa() -> None:
    """``comken.toolbox.rpa.backoffice`` は ``comken.internal.rpa.backoffice`` と同一。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        assert (
            legacy_rpa.backoffice
            is __import__("comken.internal.rpa", fromlist=["backoffice"]).backoffice
        )
        assert (
            legacy_rpa.intranet is __import__("comken.internal.rpa", fromlist=["intranet"]).intranet
        )


# ── comken.exceptions の遅延公開 ─────────────────────────────────────────────


def test_import_comken_does_not_warn() -> None:
    """``import comken`` だけでは RPA 関連の警告は出ない。"""
    importlib.invalidate_caches()
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        # 既に import 済みだが再 import して中の警告を capture
        importlib.reload(comken)
    rpa_warnings = [w for w in recorded if "Rpa" in str(w.message)]
    assert rpa_warnings == [], f"import 中に RPA 関連の警告が出た: {rpa_warnings}"


def test_import_comken_exceptions_does_not_warn() -> None:
    """``import comken.exceptions`` だけでは RPA 関連の警告は出ない。"""
    importlib.invalidate_caches()
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        importlib.reload(comken.exceptions)
    rpa_warnings = [w for w in recorded if "Rpa" in str(w.message)]
    assert rpa_warnings == [], f"import 中に RPA 関連の警告が出た: {rpa_warnings}"


def test_old_rpa_exception_name_emits_future_warning() -> None:
    """旧例外名 ``RpaLibraryNotFoundError`` を取り出すと FutureWarning。"""
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        _ = comken.exceptions.RpaLibraryNotFoundError
    assert any(issubclass(w.category, FutureWarning) for w in recorded), (
        "FutureWarning が出なかった"
    )


def test_old_rpa_exception_resolves_to_new_class() -> None:
    """``comken.exceptions.RpaLibraryNotFoundError`` は新例外と同一クラス。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        assert comken.exceptions.RpaLibraryNotFoundError is InternalLibraryNotFoundError


def test_new_internal_library_not_found_caught_by_old_rpa_alias() -> None:
    """``except RpaLibraryNotFoundError`` で新 ``InternalLibraryNotFoundError`` を捕捉できる。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        # 旧例外名で取得（中身は InternalLibraryNotFoundError と同一クラス）
        RpaLibraryNotFoundError: type[InternalLibraryNotFoundError] = (
            comken.exceptions.RpaLibraryNotFoundError  # type: ignore[assignment]
        )

    with pytest.raises(RpaLibraryNotFoundError):
        # 新しい例外を送出して、旧例外名で捕捉する
        raise InternalLibraryNotFoundError("example_libs.v0000.rpa")
