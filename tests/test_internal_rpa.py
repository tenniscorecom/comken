"""comken.internal.rpa の動作を確認する。

`comken.internal.rpa` は社内 RPA 基盤 (``example_libs.rpa``) を静的 import で
呼び出す薄いラッパー。 実機では社内 LAN にだけ存在するため、テストでは
``sys.modules`` にダミーモジュールを注入して差し替える。
"""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from comken.internal import rpa as rpa_module
from comken.internal.exceptions import InternalLibraryNotFoundError
from comken.internal.rpa import RPA_LIBRARY_NAME, backoffice, intranet


@pytest.fixture
def fake_example_libs_rpa(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """``example_libs`` と ``example_libs.rpa`` のダミーを ``sys.modules`` へ注入する。

    静的 import (``from example_libs import rpa``) をモックするため、 ``comken``
    の Python プロセス上のモジュール表に直接入れる。 ``monkeypatch`` が自動で
    テスト後に元へ戻す。
    """
    fake_rpa = mock.Mock()
    fake_example_libs = mock.Mock()
    fake_example_libs.rpa = fake_rpa
    monkeypatch.setitem(sys.modules, "example_libs", fake_example_libs)
    monkeypatch.setitem(sys.modules, "example_libs.rpa", fake_rpa)
    return fake_rpa


def _remove_example_libs(monkeypatch: pytest.MonkeyPatch) -> None:
    """``example_libs`` が無い状態を強制する。 ``sys.modules`` から取り除く。"""
    for name in ("example_libs.rpa", "example_libs"):
        monkeypatch.delitem(sys.modules, name, raising=False)


def test_rpa_library_name_is_public() -> None:
    """`RPA_LIBRARY_NAME` に社内ライブラリの名前が設定されている（バージョン無し）。"""
    assert RPA_LIBRARY_NAME == "example_libs.rpa"


class TestBackoffice:
    """`backoffice` のテスト。"""

    def test_calls_backoffice_target_on_rpa(self, fake_example_libs_rpa: mock.Mock) -> None:
        """`backoffice` は RPA モジュールの `backoffice.rpta` を呼ぶ。"""
        fake_example_libs_rpa.backoffice.rpta.return_value = "ok"
        sentinel_main = mock.Mock()
        result = backoffice(sentinel_main, "project")
        fake_example_libs_rpa.backoffice.rpta.assert_called_once_with(sentinel_main, "project")
        assert result == "ok"

    def test_raises_not_found_when_example_libs_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``example_libs`` が無いとき ``InternalLibraryNotFoundError`` が送出される。"""
        _remove_example_libs(monkeypatch)
        with pytest.raises(InternalLibraryNotFoundError):
            backoffice(lambda: None, "project")


class TestIntranet:
    """`intranet` のテスト。"""

    def test_calls_intranet_target_on_rpa(self, fake_example_libs_rpa: mock.Mock) -> None:
        """`intranet` は RPA モジュールの `intranet.rpta` を呼ぶ。"""
        fake_example_libs_rpa.intranet.rpta.return_value = "ok"
        sentinel_main = mock.Mock()
        result = intranet(sentinel_main, "project")
        fake_example_libs_rpa.intranet.rpta.assert_called_once_with(sentinel_main, "project")
        assert result == "ok"

    def test_raises_not_found_when_example_libs_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``example_libs`` が無いとき ``InternalLibraryNotFoundError`` が送出される。"""
        _remove_example_libs(monkeypatch)
        with pytest.raises(InternalLibraryNotFoundError):
            intranet(lambda: None, "project")


def test_rpa_module_lists_public_names() -> None:
    """公開名 (`backoffice`, `intranet`, `RPA_LIBRARY_NAME`) だけが露出する。"""
    public = set(dir(rpa_module))
    for name in ("backoffice", "intranet", "RPA_LIBRARY_NAME"):
        assert name in public


def test_rpa_handles_exception_in_main(fake_example_libs_rpa: mock.Mock) -> None:
    """`main` 内で例外が出ても RPA の例外に変換されない（呼び出し側で扱う）。"""
    fake_example_libs_rpa.backoffice.rpta.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        backoffice(lambda: None, "project")


def test_rpa_project_name_is_passed_through(fake_example_libs_rpa: mock.Mock) -> None:
    """`project_name` 引数がそのまま RPA 側に渡る。"""
    fake_example_libs_rpa.backoffice.rpta.return_value = None
    backoffice(lambda: None, "my-project")
    args, _ = fake_example_libs_rpa.backoffice.rpta.call_args
    assert args[1] == "my-project"
