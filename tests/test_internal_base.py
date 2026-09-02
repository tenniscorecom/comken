"""comken.internal.base の動作を確認する。

`comken.internal.base.raise_if_target_missing` は静的 import が失敗したときに
``ModuleNotFoundError`` を ``InternalLibraryNotFoundError`` に変換するヘルパー。
対象自体（またはその親）が無いときだけ変換し、内部依存不足はそのまま呼び出し元へ
伝える。
"""

from __future__ import annotations

import pytest

from comken.internal.base import raise_if_target_missing
from comken.internal.exceptions import (
    InternalLibraryError,
    InternalLibraryNotFoundError,
)


def test_internal_library_not_found_error_inherits_from_base() -> None:
    """`InternalLibraryNotFoundError` は `InternalLibraryError` の派生。"""
    assert issubclass(InternalLibraryNotFoundError, InternalLibraryError)


def test_internal_library_error_is_exception() -> None:
    """`InternalLibraryError` は BaseException の派生（送出できる）。"""
    assert issubclass(InternalLibraryError, BaseException)


# ── 対象（または親）が無い場合は NotFound に変換する ────────────────────────


def test_raises_not_found_when_target_module_missing() -> None:
    """対象モジュール自体が見つからないとき ``InternalLibraryNotFoundError`` を送出する。"""
    exc = ModuleNotFoundError(
        "No module named 'example_libs.missing'",
        name="example_libs.missing",
    )
    with pytest.raises(InternalLibraryNotFoundError) as caught:
        raise_if_target_missing("example_libs.missing", exc)
    assert caught.value.library_name == "example_libs.missing"


def test_raises_not_found_when_parent_package_missing() -> None:
    """親パッケージが見つからない場合も ``InternalLibraryNotFoundError`` を送出する。

    ``library_name.startswith(missing_name + '.')`` で親部分一致を見る。
    """
    exc = ModuleNotFoundError(
        "No module named 'example_libs'",
        name="example_libs",
    )
    with pytest.raises(InternalLibraryNotFoundError) as caught:
        raise_if_target_missing("example_libs.rpa", exc)
    assert caught.value.library_name == "example_libs.rpa"


def test_raises_not_found_chains_original_exception() -> None:
    """送出する ``InternalLibraryNotFoundError`` は元の ``ModuleNotFoundError`` を
    ``__cause__`` に残す（``raise ... from exc`` の契約）。"""
    exc = ModuleNotFoundError(
        "No module named 'example_libs.rpa'",
        name="example_libs.rpa",
    )
    with pytest.raises(InternalLibraryNotFoundError) as caught:
        raise_if_target_missing("example_libs.rpa", exc)
    assert caught.value.__cause__ is exc


# ── 内部依存不足の場合は何もしない（呼び出し元で raise される） ──────────


def test_no_conversion_for_unrelated_missing_dependency() -> None:
    """対象でも親でもない依存が無い場合は何もしない。

    呼び出し元が ``raise`` で元の ``ModuleNotFoundError`` を伝搬する契約のため、
    ``raise_if_target_missing`` 自身は例外を上げない。
    """
    exc = ModuleNotFoundError(
        "No module named 'example_libs.subdep'",
        name="example_libs.subdep",
    )
    # 戻りは None で、例外も送出しない
    assert raise_if_target_missing("example_libs.rpa", exc) is None


def test_no_conversion_when_name_attribute_is_none() -> None:
    """``exc.name`` が無い（None）ときは誤変換を避けるため何もしない。"""
    exc = ModuleNotFoundError("No module named something")
    # ModuleNotFoundError に name を渡さなければ ``name`` は None
    assert exc.name is None
    assert raise_if_target_missing("example_libs.rpa", exc) is None


def test_no_conversion_when_dependency_matches_substring_not_prefix() -> None:
    """``library_name`` の途中と一致しても親部分一致でなければ何もしない。

    例えば ``library_name='example_libs.rpa'`` で ``missing_name='example_libs.r'``
    のような接頭辞一致は対象に含まれない。
    """
    exc = ModuleNotFoundError(
        "No module named 'example_libs.r'",
        name="example_libs.r",
    )
    assert raise_if_target_missing("example_libs.rpa", exc) is None
