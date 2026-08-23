"""SalesforceApi の下地実装テスト。

``example_libs.v0000.salesforce`` が import できない環境でも、インスタンス化と
SALESFORCE_LIBRARY_NAME 定数の確認が可能。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from comken.internal.exceptions import InternalLibraryNotFoundError
from comken.internal.salesforce_api import SALESFORCE_LIBRARY_NAME, SalesforceApi


def test_salesforce_library_name_is_correct() -> None:
    """SALESFORCE_LIBRARY_NAME 定数の値を確認する。"""
    assert SALESFORCE_LIBRARY_NAME == "example_libs.v0000.salesforce"


def test_module_loads_on_enter() -> None:
    """__enter__ でモジュールがロードされる。"""
    fake_module = object()
    with patch("comken.internal.salesforce_api.InternalLibraryBase") as mock_base:
        mock_base.return_value.load.return_value = fake_module
        with SalesforceApi() as api:
            mock_base.return_value.load.assert_called_once()
            assert api._module is fake_module


def test_module_is_none_on_exit() -> None:
    """__exit__ で _module が None になる。"""
    fake_module = object()
    with patch("comken.internal.salesforce_api.InternalLibraryBase") as mock_base:
        mock_base.return_value.load.return_value = fake_module
        api = SalesforceApi()
        # __enter__ を直接呼んで _module をセット
        api.__enter__()
        assert api._module is fake_module
        # __exit__ を呼ぶと _module が None になる
        api.__exit__(None, None, None)
        assert api._module is None


def test_internal_library_not_found_raises() -> None:
    """社内ライブラリが見つからない場合、InternalLibraryNotFoundError が出る。"""
    with (
        patch("comken.internal.salesforce_api.InternalLibraryBase") as mock_base,
        pytest.raises(InternalLibraryNotFoundError),
    ):
        mock_base.return_value.load.side_effect = InternalLibraryNotFoundError(
            "example_libs.v0000.salesforce"
        )
        with SalesforceApi():
            pass


def test_is_context_manager() -> None:
    """SalesforceApi がコンテキストマネージャとして使える。"""
    api = SalesforceApi()
    assert hasattr(api, "__enter__")
    assert hasattr(api, "__exit__")


def test_module_loads_real_library_when_available() -> None:
    """社内ライブラリが利用可能な環境では _module に実モジュールが入る。"""
    try:
        with SalesforceApi() as api:
            assert api._module is not None
    except InternalLibraryNotFoundError:
        # 社内ライブラリが利用できない環境ではスキップ
        pytest.skip("社内ライブラリが利用できないためスキップ")
