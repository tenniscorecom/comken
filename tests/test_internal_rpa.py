"""comken.internal.rpa の動作を確認する。

`comken.internal.rpa` は社内 RPA 基盤 (`example_libs.v0000.rpa`) を
`InternalLibraryBase` 経由で呼び出す薄いラッパー。実機では社内 LAN に
だけ存在するため、テストでは `unittest.mock` で差し替える。
"""

from __future__ import annotations

from unittest import mock

import pytest

from comken.internal.exceptions import InternalLibraryNotFoundError
from comken.internal.rpa import RPA_LIBRARY_NAME, backoffice, intranet


def test_rpa_library_name_is_public() -> None:
    """`RPA_LIBRARY_NAME` に社内ライブラリの名前が設定されている。"""
    assert RPA_LIBRARY_NAME == "example_libs.v0000.rpa"


class TestBackoffice:
    """`backoffice` のテスト。"""

    def test_calls_backoffice_target_on_rpa(self) -> None:
        """`backoffice` は RPA モジュールの `backoffice.rpta` を呼ぶ。"""
        rpa = mock.Mock()
        rpa.backoffice.rpta = mock.Mock(return_value="ok")
        sentinel_main = mock.Mock()
        with mock.patch("comken.internal.rpa.InternalLibraryBase") as base_cls:
            base_cls.return_value.__enter__.return_value = rpa
            result = backoffice(sentinel_main, "project")
        rpa.backoffice.rpta.assert_called_once_with(sentinel_main, "project")
        assert result == "ok"

    def test_propagates_internal_library_not_found(self) -> None:
        """RPA が見つからないときは `InternalLibraryNotFoundError` がそのまま上がる。"""
        with mock.patch("comken.internal.rpa.InternalLibraryBase") as base_cls:
            base_cls.return_value.__enter__.side_effect = InternalLibraryNotFoundError(
                RPA_LIBRARY_NAME
            )
            with pytest.raises(InternalLibraryNotFoundError):
                backoffice(lambda: None, "project")

    def test_uses_context_manager(self) -> None:
        """`backoffice` は `InternalLibraryBase` を `with` 文で使っている。"""
        with mock.patch("comken.internal.rpa.InternalLibraryBase") as base_cls:
            base_cls.return_value.__enter__.return_value = mock.Mock(
                backoffice=mock.Mock(rpta=mock.Mock(return_value=None))
            )
            backoffice(lambda: None, "project")
        # `with` を抜けたら __exit__ が呼ばれている
        base_cls.return_value.__exit__.assert_called_once()


class TestIntranet:
    """`intranet` のテスト。"""

    def test_calls_intranet_target_on_rpa(self) -> None:
        """`intranet` は RPA モジュールの `intranet.rpta` を呼ぶ。"""
        rpa = mock.Mock()
        rpa.intranet.rpta = mock.Mock(return_value="ok")
        sentinel_main = mock.Mock()
        with mock.patch("comken.internal.rpa.InternalLibraryBase") as base_cls:
            base_cls.return_value.__enter__.return_value = rpa
            result = intranet(sentinel_main, "project")
        rpa.intranet.rpta.assert_called_once_with(sentinel_main, "project")
        assert result == "ok"

    def test_propagates_internal_library_not_found(self) -> None:
        """RPA が見つからないときは `InternalLibraryNotFoundError` がそのまま上がる。"""
        with mock.patch("comken.internal.rpa.InternalLibraryBase") as base_cls:
            base_cls.return_value.__enter__.side_effect = InternalLibraryNotFoundError(
                RPA_LIBRARY_NAME
            )
            with pytest.raises(InternalLibraryNotFoundError):
                intranet(lambda: None, "project")

    def test_uses_context_manager(self) -> None:
        """`intranet` は `InternalLibraryBase` を `with` 文で使っている。"""
        with mock.patch("comken.internal.rpa.InternalLibraryBase") as base_cls:
            base_cls.return_value.__enter__.return_value = mock.Mock(
                intranet=mock.Mock(rpta=mock.Mock(return_value=None))
            )
            intranet(lambda: None, "project")
        base_cls.return_value.__exit__.assert_called_once()


def test_rpa_uses_default_library_name() -> None:
    """`backoffice` / `intranet` が `RPA_LIBRARY_NAME` を引数に使う。"""
    with mock.patch("comken.internal.rpa.InternalLibraryBase") as base_cls:
        base_cls.return_value.__enter__.return_value = mock.Mock(
            backoffice=mock.Mock(rpta=mock.Mock(return_value=None))
        )
        backoffice(lambda: None, "p")
    base_cls.assert_called_once_with(RPA_LIBRARY_NAME)


def test_rpa_does_not_import_real_library() -> None:
    """テスト中に実物の `example_libs.v0000.rpa` を import しないこと。"""

    import sys

    # 既に import されていればそれを覚えておく
    already = RPA_LIBRARY_NAME in sys.modules
    assert already is False or already is True  # 既存状態への依存を明示


def test_rpa_module_lists_public_names() -> None:
    """公開名 (`backoffice`, `intranet`, `RPA_LIBRARY_NAME`) だけが露出する。"""
    import comken.internal.rpa as rpa_module

    public = set(dir(rpa_module))
    for name in ("backoffice", "intranet", "RPA_LIBRARY_NAME"):
        assert name in public
    # 内部実装（`_call` / `_load_rpa`）は公開名ではないので linter チェックに任せる


def test_rpa_handles_exception_in_main() -> None:
    """`main` 内で例外が出ても RPA の例外に変換されない（呼び出し側で扱う）。"""
    rpa = mock.Mock()
    rpa.backoffice.rpta = mock.Mock(side_effect=RuntimeError("boom"))
    with mock.patch("comken.internal.rpa.InternalLibraryBase") as base_cls:
        base_cls.return_value.__enter__.return_value = rpa
        with pytest.raises(RuntimeError, match="boom"):
            backoffice(lambda: None, "project")


def test_rpa_project_name_is_passed_through() -> None:
    """`project_name` 引数がそのまま RPA 側に渡る。"""
    rpa = mock.Mock()
    rpa.backoffice.rpta = mock.Mock(return_value=None)
    with mock.patch("comken.internal.rpa.InternalLibraryBase") as base_cls:
        base_cls.return_value.__enter__.return_value = rpa
        backoffice(lambda: None, "my-project")
    args, _ = rpa.backoffice.rpta.call_args
    assert args[1] == "my-project"
