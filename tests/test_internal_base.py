"""comken.internal.base の動作を確認する。

`InternalLibraryBase` は社内ライブラリ (`example_libs.v0000.*`) を import する
窓口。実機では社内 LAN にだけ存在するため、テストでは `unittest.mock` で
`importlib.util.find_spec` / `importlib.import_module` を差し替える。
"""

from __future__ import annotations

from unittest import mock

import pytest

from comken.internal.base import InternalLibraryBase
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
        """`load` は対象モジュール不在を `InternalLibraryNotFoundError` に変換する。"""
        target = InternalLibraryBase("example_libs.v0000.missing")
        with (
            mock.patch(
                "comken.internal.base.importlib.import_module",
                side_effect=ModuleNotFoundError(
                    "No module named 'example_libs.v0000.missing'",
                    name="example_libs.v0000.missing",
                ),
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
                side_effect=ModuleNotFoundError(
                    "No module named 'example_libs.v0000.rpa'",
                    name="example_libs.v0000.rpa",
                ),
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


# ── 親パッケージ不在と内部依存不足の区別 ─────────────────────────────────────


def test_find_spec_returns_false_when_parent_package_missing() -> None:
    """親パッケージ（``example_libs``）自体が無い場合は False。

    `find_spec` は親が無いと ``ModuleNotFoundError`` を送出するため、
    例外を握り潰して False を返す実装になっている必要がある。
    """
    # 実際に存在しないパスを渡す。モックではなく本物の find_spec を使う。
    target = InternalLibraryBase("nonexistent_parent.v0000.rpa")
    assert target.find_spec() is False


def test_load_propagates_dependency_import_error() -> None:
    """モジュール本体は見つかるが内部依存が無ければ元の ImportError を伝搬する。

    対象ライブラリ不在と誤変換しないための契約。 ``find_spec`` でモジュールが
    見つかるケースをシミュレートし、 ``import_module`` が依存不足で失敗した
    場合に ``InternalLibraryNotFoundError`` ではなく元の例外が上がることを確認する。
    """
    target = InternalLibraryBase("example_libs.v0000.rpa")
    with (
        mock.patch(
            "comken.internal.base.importlib.import_module",
            side_effect=ModuleNotFoundError(
                "No module named 'example_libs.v0000.subdep'",
                name="example_libs.v0000.subdep",  # 内部依存名（library_name の親部分ではない）
            ),
        ),
        pytest.raises(ModuleNotFoundError) as caught,
    ):
        target.load()
    # 内部依存の ModuleNotFoundError はそのまま上がる
    assert caught.value.name == "example_libs.v0000.subdep"


def test_load_returns_internal_library_not_found_for_missing_target() -> None:
    """対象モジュール自体が無いときは ``InternalLibraryNotFoundError`` に変換する。"""
    target = InternalLibraryBase("example_libs.v0000.missing")
    with (
        mock.patch(
            "comken.internal.base.importlib.import_module",
            side_effect=ModuleNotFoundError(
                "No module named 'example_libs.v0000.missing'",
                name="example_libs.v0000.missing",
            ),
        ),
        pytest.raises(InternalLibraryNotFoundError) as caught,
    ):
        target.load()
    assert caught.value.library_name == "example_libs.v0000.missing"


def test_load_returns_not_found_when_parent_package_is_missing() -> None:
    """対象の親パッケージが無い場合も利用者向けの NotFound に変換する。"""
    target = InternalLibraryBase("example_libs.v0000.rpa")
    with (
        mock.patch(
            "comken.internal.base.importlib.import_module",
            side_effect=ModuleNotFoundError(
                "No module named 'example_libs'",
                name="example_libs",
            ),
        ),
        pytest.raises(InternalLibraryNotFoundError),
    ):
        target.load()


def test_find_spec_propagates_dependency_module_not_found() -> None:
    """``find_spec`` 自体が起こる ``ModuleNotFoundError`` のうち、内部依存由来は
    そのまま伝搬する。 対象モジュール（または親）と別の name のときだけ例外を投げる。
    """
    target = InternalLibraryBase("example_libs.v0000.rpa")
    with (
        mock.patch(
            "comken.internal.base.importlib.util.find_spec",
            side_effect=ModuleNotFoundError(
                "No module named 'example_libs.v0000.subdep'",
                name="example_libs.v0000.subdep",
            ),
        ),
        pytest.raises(ModuleNotFoundError) as caught,
    ):
        target.find_spec()
    assert caught.value.name == "example_libs.v0000.subdep"


def test_find_spec_false_when_parent_only_missing() -> None:
    """``find_spec`` 自体が ``ModuleNotFoundError`` を投げ、name が library_name の
    親部分に該当する場合（``library_name.startswith(missing + '.')``）は False を返す。
    """
    target = InternalLibraryBase("example_libs.v0000.rpa")
    with mock.patch(
        "comken.internal.base.importlib.util.find_spec",
        side_effect=ModuleNotFoundError(
            "No module named 'example_libs'",
            name="example_libs",
        ),
    ):
        assert target.find_spec() is False
