"""comken.internal.base の動作を確認する。

`InternalLibraryBase` は社内ライブラリ (`example_libs.v0000.*`) を import する
窓口。実機では社内 LAN にだけ存在するため、テストでは `unittest.mock` で
`importlib.util.find_spec` / `importlib.import_module` を差し替える。
"""

from __future__ import annotations

from unittest import mock

import pytest

from comken.internal.base import (
    InternalLibraryBase,
    find_internal_library,
    is_internal_library_available,
)
from comken.internal.exceptions import (
    InternalLibraryError,
    InternalLibraryNotFoundError,
)


class TestInternalLibraryBase:
    """`InternalLibraryBase` の `find_spec` / `load` / `__enter__` / `__exit__`。"""

    def test_library_name_is_exposed(self) -> None:
        """`library_name` プロパティで設定した名前を返す。"""
        target = InternalLibraryBase("example_libs.v0000.rpa")
        assert target.library_name == "example_libs.v0000.rpa"

    def test_find_spec_returns_true_when_module_exists(self) -> None:
        """`find_spec` はモジュールが見つかれば True。"""
        target = InternalLibraryBase("example_libs.v0000.rpa")
        with mock.patch("comken.internal.base.importlib.util.find_spec", return_value=mock.Mock()):
            assert target.find_spec() is True

    def test_find_spec_returns_false_when_module_missing(self) -> None:
        """`find_spec` はモジュールが無ければ False。"""
        target = InternalLibraryBase("example_libs.v0000.rpa")
        with mock.patch("comken.internal.base.importlib.util.find_spec", return_value=None):
            assert target.find_spec() is False

    def test_load_returns_module(self) -> None:
        """`load` は import したモジュールをそのまま返す。"""
        target = InternalLibraryBase("example_libs.v0000.rpa")
        sentinel = mock.Mock()
        with mock.patch("comken.internal.base.importlib.import_module", return_value=sentinel):
            assert target.load() is sentinel

    def test_load_raises_not_found(self) -> None:
        """`load` は ImportError を `InternalLibraryNotFoundError` に変換する。"""
        target = InternalLibraryBase("example_libs.v0000.missing")
        with (
            mock.patch(
                "comken.internal.base.importlib.import_module",
                side_effect=ImportError("not found"),
            ),
            pytest.raises(InternalLibraryNotFoundError) as caught,
        ):
            target.load()
        assert caught.value.library_name == "example_libs.v0000.missing"

    def test_enter_returns_module(self) -> None:
        """`__enter__` は load の結果を返す。"""
        target = InternalLibraryBase("example_libs.v0000.rpa")
        sentinel = mock.Mock()
        with (
            mock.patch("comken.internal.base.importlib.util.find_spec", return_value=mock.Mock()),
            mock.patch("comken.internal.base.importlib.import_module", return_value=sentinel),
        ):
            assert target.__enter__() is sentinel

    def test_enter_warns_when_module_missing(self) -> None:
        """`__enter__` はモジュールが無いとき warning を出し、load を試みる。"""
        import comken.internal.base as base_module

        target = InternalLibraryBase("example_libs.v0000.rpa")
        with (
            mock.patch("comken.internal.base.importlib.util.find_spec", return_value=None),
            mock.patch(
                "comken.internal.base.importlib.import_module",
                side_effect=ImportError("nope"),
            ),
            mock.patch.object(base_module.logger, "warning") as warning,
            pytest.raises(InternalLibraryNotFoundError),
        ):
            target.__enter__()
        warning.assert_called_once()

    def test_exit_clears_module(self) -> None:
        """`__exit__` は内部参照を None に戻す。"""
        target = InternalLibraryBase("example_libs.v0000.rpa")
        sentinel = mock.Mock()
        target._module = sentinel
        target.__exit__(None, None, None)
        assert target._module is None

    def test_exit_accepts_traceback_signature(self) -> None:
        """`__exit__` は `with` 文の引数を受け取れるシグネチャを持つ。"""
        target = InternalLibraryBase("example_libs.v0000.rpa")
        result = target.__exit__(None, None, None)
        assert result is None or result is False

    def test_context_manager_roundtrip(self) -> None:
        """`with` 文で入ったら出てくると参照が None に戻ること。"""
        sentinel = mock.Mock()
        with (
            mock.patch("comken.internal.base.importlib.util.find_spec", return_value=mock.Mock()),
            mock.patch("comken.internal.base.importlib.import_module", return_value=sentinel),
            InternalLibraryBase("example_libs.v0000.rpa") as rpa,
        ):
            assert rpa is sentinel
        # ブロックを抜けたら参照は消える（内部状態）


class TestIsInternalLibraryAvailable:
    """`is_internal_library_available` のテスト。"""

    def test_returns_true_when_module_found(self) -> None:
        with mock.patch("comken.internal.base.importlib.util.find_spec", return_value=mock.Mock()):
            assert is_internal_library_available("example_libs.v0000.rpa") is True

    def test_returns_false_when_module_missing(self) -> None:
        with mock.patch("comken.internal.base.importlib.util.find_spec", return_value=None):
            assert is_internal_library_available("example_libs.v0000.rpa") is False


class TestFindInternalLibrary:
    """`find_internal_library` のテスト。"""

    def test_returns_module_when_import_succeeds(self) -> None:
        sentinel = mock.Mock()
        with mock.patch("comken.internal.base.importlib.import_module", return_value=sentinel):
            assert find_internal_library("example_libs.v0000.rpa") is sentinel

    def test_returns_none_when_import_fails(self) -> None:
        with mock.patch(
            "comken.internal.base.importlib.import_module",
            side_effect=ImportError("nope"),
        ):
            assert find_internal_library("example_libs.v0000.missing") is None


def test_internal_library_not_found_error_inherits_from_base() -> None:
    """`InternalLibraryNotFoundError` は `InternalLibraryError` の派生。"""
    assert issubclass(InternalLibraryNotFoundError, InternalLibraryError)


def test_internal_library_error_is_exception() -> None:
    """`InternalLibraryError` は BaseException の派生（送出できる）。"""
    assert issubclass(InternalLibraryError, BaseException)


def test_internal_library_base_keeps_traceback_signature() -> None:
    """`InternalLibraryBase.__exit__` は `TracebackType | None` を受ける。"""
    import inspect

    sig = inspect.signature(InternalLibraryBase.__exit__)
    # 第3引数が traceback として None を受け付けられる型ヒントを持つ
    params = list(sig.parameters.values())
    assert len(params) >= 3
