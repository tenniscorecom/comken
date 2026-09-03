"""comken.exceptions.rpa の動作を確認する。

`InternalLibraryError` は社内ライブラリ呼び出しに失敗したときの基底例外。
`InternalLibraryNotFoundError` / `InternalLibraryVersionMismatchError` が
具体的な派生として定義される。`comken.exceptions` から re-export されている
ため、利用側は `from comken.exceptions import InternalLibraryError` で取れる。
"""

from __future__ import annotations

import pytest

import comken.exceptions
from comken.exceptions import (
    ComkenError,
    InternalLibraryError,
    InternalLibraryNotFoundError,
    InternalLibraryVersionMismatchError,
)


class TestInternalLibraryError:
    """`InternalLibraryError` のテスト。"""

    def test_inherits_from_comken_error(self) -> None:
        """`InternalLibraryError` は `ComkenError` の派生。"""
        assert issubclass(InternalLibraryError, ComkenError)

    def test_is_an_exception(self) -> None:
        """`raise` できる。"""
        with pytest.raises(InternalLibraryError):
            raise InternalLibraryError("基底なので直接は送らない想定")

    def test_message_is_preserved(self) -> None:
        """`str()` で引数のメッセージが返る。"""
        assert str(InternalLibraryError("boom")) == "boom"

    def test_caught_by_comken_error(self) -> None:
        """`except ComkenError` で捕捉できる（広域 catch の契約）。"""
        with pytest.raises(ComkenError):
            try:
                raise InternalLibraryError("boom")
            except ComkenError:
                raise


class TestInternalLibraryNotFoundError:
    """`InternalLibraryNotFoundError` のテスト。"""

    def test_inherits_from_internal_library_error(self) -> None:
        assert issubclass(InternalLibraryNotFoundError, InternalLibraryError)

    def test_inherits_from_comken_error(self) -> None:
        assert issubclass(InternalLibraryNotFoundError, ComkenError)

    def test_library_name_is_attached(self) -> None:
        """`library_name` 属性に渡した名前が入る。"""
        err = InternalLibraryNotFoundError("kensetsu_libs.rpa")
        assert err.library_name == "kensetsu_libs.rpa"

    def test_message_includes_library_name(self) -> None:
        """エラーメッセージにライブラリ名が入る（画面で原因が分かる）。"""
        err = InternalLibraryNotFoundError("kensetsu_libs.rpa")
        assert "kensetsu_libs.rpa" in str(err)

    def test_can_be_raised_and_caught(self) -> None:
        """送出・捕捉が普通にできる。"""
        with pytest.raises(InternalLibraryNotFoundError) as caught:
            raise InternalLibraryNotFoundError("missing")
        assert caught.value.library_name == "missing"


class TestInternalLibraryVersionMismatchError:
    """`InternalLibraryVersionMismatchError` のテスト。"""

    def test_inherits_from_internal_library_error(self) -> None:
        assert issubclass(InternalLibraryVersionMismatchError, InternalLibraryError)

    def test_inherits_from_comken_error(self) -> None:
        assert issubclass(InternalLibraryVersionMismatchError, ComkenError)

    def test_library_and_required_version_are_attached(self) -> None:
        """`library_name` / `required_version` が属性として残る。"""
        err = InternalLibraryVersionMismatchError("kensetsu_libs.rpa", "0000")
        assert err.library_name == "kensetsu_libs.rpa"
        assert err.required_version == "0000"

    def test_message_includes_both(self) -> None:
        """メッセージにライブラリ名と要求バージョン両方が出る。"""
        err = InternalLibraryVersionMismatchError("kensetsu_libs.rpa", "0000")
        text = str(err)
        assert "kensetsu_libs.rpa" in text
        assert "0000" in text

    def test_can_be_raised_and_caught(self) -> None:
        """送出・捕捉が普通にできる。"""
        with pytest.raises(InternalLibraryVersionMismatchError) as caught:
            raise InternalLibraryVersionMismatchError("lib", "1.2.3")
        assert caught.value.required_version == "1.2.3"


def test_comken_exceptions_reexports_internal_library_classes() -> None:
    """`comken.exceptions` から `InternalLibrary*` クラスが直接取れる。"""
    assert comken.exceptions.InternalLibraryError is InternalLibraryError
    assert comken.exceptions.InternalLibraryNotFoundError is InternalLibraryNotFoundError
    assert (
        comken.exceptions.InternalLibraryVersionMismatchError is InternalLibraryVersionMismatchError
    )


def test_comken_exceptions_all_declares_internal_library_classes() -> None:
    """`comken.exceptions.__all__` に `InternalLibrary*` が含まれている。"""
    for name in (
        "InternalLibraryError",
        "InternalLibraryNotFoundError",
        "InternalLibraryVersionMismatchError",
    ):
        assert name in comken.exceptions.__all__, (
            f"{name} が comken.exceptions.__all__ に含まれていない"
        )


def test_internal_library_error_caught_broadly() -> None:
    """`InternalLibraryError` は `except ComkenError` でまとめて拾える。"""
    # 派生を 2 種類試す
    with pytest.raises(ComkenError):
        raise InternalLibraryNotFoundError("lib")
    with pytest.raises(ComkenError):
        raise InternalLibraryVersionMismatchError("lib", "v1")
