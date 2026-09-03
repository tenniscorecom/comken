"""comken.toolbox.rpa の動作を確認する。

`comken.toolbox.rpa` は社内 RPA 基盤 (``kensetsu_libs.rpa``) を静的 import で
呼び出す薄いラッパー。 実機では社内 LAN にだけ存在するため、テストでは
``sys.modules`` にダミーモジュールを注入して差し替える。
"""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from comken.exceptions.rpa import InternalLibraryNotFoundError
from comken.toolbox import rpa as rpa_module
from comken.toolbox.rpa import RPA_LIBRARY_NAME, backoffice, intranet


@pytest.fixture
def fake_kensetsu_libs_rpa(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """``kensetsu_libs`` と ``kensetsu_libs.rpa`` のダミーを ``sys.modules`` へ注入する。

    静的 import (``from kensetsu_libs import rpa``) をモックするため、 ``comken``
    の Python プロセス上のモジュール表に直接入れる。 ``monkeypatch`` が自動で
    テスト後に元へ戻す。
    """
    fake_rpa = mock.Mock()
    fake_kensetsu_libs = mock.Mock()
    fake_kensetsu_libs.rpa = fake_rpa
    monkeypatch.setitem(sys.modules, "kensetsu_libs", fake_kensetsu_libs)
    monkeypatch.setitem(sys.modules, "kensetsu_libs.rpa", fake_rpa)
    return fake_rpa


def _remove_kensetsu_libs(monkeypatch: pytest.MonkeyPatch) -> None:
    """``kensetsu_libs`` が無い状態を強制する。 ``sys.modules`` から取り除く。"""
    for name in ("kensetsu_libs.rpa", "kensetsu_libs"):
        monkeypatch.delitem(sys.modules, name, raising=False)


def test_rpa_library_name_is_public() -> None:
    """`RPA_LIBRARY_NAME` に社内ライブラリの名前が設定されている（バージョン無し）。"""
    assert RPA_LIBRARY_NAME == "kensetsu_libs.rpa"


class TestBackoffice:
    """`backoffice` のテスト。"""

    def test_calls_backoffice_target_on_rpa(self, fake_kensetsu_libs_rpa: mock.Mock) -> None:
        """`backoffice` は RPA モジュールの `backoffice.rpa_run` を呼ぶ。"""
        fake_kensetsu_libs_rpa.backoffice.rpa_run.return_value = "ok"
        sentinel_main = mock.Mock()
        result = backoffice(sentinel_main, "project")
        fake_kensetsu_libs_rpa.backoffice.rpa_run.assert_called_once_with(sentinel_main, "project")
        assert result == "ok"

    def test_raises_not_found_when_kensetsu_libs_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``kensetsu_libs`` が無いとき ``InternalLibraryNotFoundError`` が送出される。"""
        _remove_kensetsu_libs(monkeypatch)
        with pytest.raises(InternalLibraryNotFoundError):
            backoffice(lambda: None, "project")


class TestIntranet:
    """`intranet` のテスト。"""

    def test_calls_intranet_target_on_rpa(self, fake_kensetsu_libs_rpa: mock.Mock) -> None:
        """`intranet` は RPA モジュールの `intranet.rpa_run` を呼ぶ。"""
        fake_kensetsu_libs_rpa.intranet.rpa_run.return_value = "ok"
        sentinel_main = mock.Mock()
        result = intranet(sentinel_main, "project")
        fake_kensetsu_libs_rpa.intranet.rpa_run.assert_called_once_with(sentinel_main, "project")
        assert result == "ok"

    def test_raises_not_found_when_kensetsu_libs_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``kensetsu_libs`` が無いとき ``InternalLibraryNotFoundError`` が送出される。"""
        _remove_kensetsu_libs(monkeypatch)
        with pytest.raises(InternalLibraryNotFoundError):
            intranet(lambda: None, "project")


def test_rpa_module_lists_public_names() -> None:
    """公開名 (`backoffice`, `intranet`, `RPA_LIBRARY_NAME`) だけが露出する。"""
    public = set(dir(rpa_module))
    for name in ("backoffice", "intranet", "RPA_LIBRARY_NAME"):
        assert name in public


def test_rpa_handles_exception_in_main(fake_kensetsu_libs_rpa: mock.Mock) -> None:
    """`main` 内で例外が出ても RPA の例外に変換されない（呼び出し側で扱う）。"""
    fake_kensetsu_libs_rpa.backoffice.rpa_run.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        backoffice(lambda: None, "project")


def test_rpa_project_name_is_passed_through(fake_kensetsu_libs_rpa: mock.Mock) -> None:
    """`project_name` 引数がそのまま RPA 側に渡る。"""
    fake_kensetsu_libs_rpa.backoffice.rpa_run.return_value = None
    backoffice(lambda: None, "my-project")
    args, _ = fake_kensetsu_libs_rpa.backoffice.rpa_run.call_args
    assert args[1] == "my-project"


# ── _raise_if_target_missing の単体テスト ─────────────────────────────


def _raise(library_name: str, exc: ModuleNotFoundError) -> None:
    """テスト用に `_raise_if_target_missing` を取り出す。"""
    rpa_module._raise_if_target_missing(library_name, exc)


def test_raises_not_found_when_target_module_missing() -> None:
    """対象モジュール自体が見つからないとき ``InternalLibraryNotFoundError`` を送出する。"""
    exc = ModuleNotFoundError(
        "No module named 'kensetsu_libs.missing'",
        name="kensetsu_libs.missing",
    )
    with pytest.raises(InternalLibraryNotFoundError) as caught:
        _raise("kensetsu_libs.missing", exc)
    assert caught.value.library_name == "kensetsu_libs.missing"


def test_raises_not_found_when_parent_package_missing() -> None:
    """親パッケージが見つからない場合も ``InternalLibraryNotFoundError`` を送出する。

    ``library_name.startswith(missing_name + '.')`` で親部分一致を見る。
    """
    exc = ModuleNotFoundError(
        "No module named 'kensetsu_libs'",
        name="kensetsu_libs",
    )
    with pytest.raises(InternalLibraryNotFoundError) as caught:
        _raise("kensetsu_libs.rpa", exc)
    assert caught.value.library_name == "kensetsu_libs.rpa"


def test_propagates_original_when_unrelated_dependency_missing() -> None:
    """対象でも親でもない依存が無い場合は何もしない。

    呼び出し元が ``raise`` で元の ``ModuleNotFoundError`` を伝搬する契約のため、
    ``_raise_if_target_missing`` 自身は例外を上げない。
    """
    exc = ModuleNotFoundError(
        "No module named 'kensetsu_libs.subdep'",
        name="kensetsu_libs.subdep",
    )
    assert _raise("kensetsu_libs.rpa", exc) is None
