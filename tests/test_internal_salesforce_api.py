"""SalesforceAPI の下地実装テスト。

``example_libs.v0000.salesforce`` が import できない環境でも、インスタンス化と
SALESFORCE_LIBRARY_NAME 定数の確認が可能。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from comken.internal.exceptions import InternalLibraryNotFoundError
from comken.internal.salesforce_api import SALESFORCE_LIBRARY_NAME, SalesforceAPI


def test_salesforce_library_name_is_correct() -> None:
    """SALESFORCE_LIBRARY_NAME 定数の値を確認する。"""
    assert SALESFORCE_LIBRARY_NAME == "example_libs.v0000.salesforce"


def test_module_loads_on_enter() -> None:
    """__enter__ でモジュールがロードされる。"""
    fake_module = object()
    with patch("comken.internal.salesforce_api.InternalLibraryBase") as mock_base:
        mock_base.return_value.load.return_value = fake_module
        with SalesforceAPI() as api:
            mock_base.return_value.load.assert_called_once()
            assert api._module is fake_module


def test_module_is_none_on_exit() -> None:
    """__exit__ で _module が None になる。"""
    fake_module = object()
    with patch("comken.internal.salesforce_api.InternalLibraryBase") as mock_base:
        mock_base.return_value.load.return_value = fake_module
        api = SalesforceAPI()
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
        with SalesforceAPI():
            pass


def test_is_context_manager() -> None:
    """SalesforceAPI がコンテキストマネージャとして使える。"""
    api = SalesforceAPI()
    assert hasattr(api, "__enter__")
    assert hasattr(api, "__exit__")


def test_module_loads_real_library_when_available() -> None:
    """社内ライブラリが利用可能な環境では _module に実モジュールが入る。"""
    try:
        with SalesforceAPI() as api:
            assert api._module is not None
    except InternalLibraryNotFoundError:
        # 社内ライブラリが利用できない環境ではスキップ
        pytest.skip("社内ライブラリが利用できないためスキップ")


def test_query_delegates_to_module() -> None:
    """query() は社内モジュールの query() を呼ぶ。"""
    fake_module = MagicMock()
    fake_module.query.return_value = [{"Id": "001"}]
    with patch("comken.internal.salesforce_api.InternalLibraryBase") as mock_base:
        mock_base.return_value.load.return_value = fake_module
        with SalesforceAPI() as api:
            result = api.query("SELECT Id FROM Account")
    assert result == [{"Id": "001"}]
    fake_module.query.assert_called_once_with("SELECT Id FROM Account")


def test_report_run_delegates_to_module() -> None:
    """report_run() は社内モジュールの report_run() を呼ぶ。"""
    fake_module = MagicMock()
    fake_module.report_run.return_value = [{"row": 1}]
    with patch("comken.internal.salesforce_api.InternalLibraryBase") as mock_base:
        mock_base.return_value.load.return_value = fake_module
        with SalesforceAPI() as api:
            result = api.report_run("report_id_123")
    assert result == [{"row": 1}]
    fake_module.report_run.assert_called_once_with("report_id_123")


def test_request_delegates_to_module() -> None:
    """request() は社内モジュールの request() を呼ぶ。"""
    fake_module = MagicMock()
    fake_module.request.return_value = {"success": True}
    with patch("comken.internal.salesforce_api.InternalLibraryBase") as mock_base:
        mock_base.return_value.load.return_value = fake_module
        with SalesforceAPI() as api:
            result = api.request("GET", "/path", component="/v1", body={"key": "value"})
    assert result == {"success": True}
    fake_module.request.assert_called_once_with(
        "GET", "/path", component="/v1", body={"key": "value"}
    )


def test_data_path_delegates_to_module() -> None:
    """data_path() は社内モジュールの data_path() を呼ぶ。"""
    fake_module = MagicMock()
    fake_module.data_path.return_value = "/services/data/v1/path"
    with patch("comken.internal.salesforce_api.InternalLibraryBase") as mock_base:
        mock_base.return_value.load.return_value = fake_module
        with SalesforceAPI() as api:
            result = api.data_path("/path")
    assert result == "/services/data/v1/path"
    fake_module.data_path.assert_called_once_with("/path")


def test_credential_prefix_constant() -> None:
    """CREDENTIAL_PREFIX クラス定数の値を確認する。"""
    assert SalesforceAPI.CREDENTIAL_PREFIX == "SALESFORCE"


def test_methods_raise_outside_with_block() -> None:
    """with ブロック外でメソッドを呼ぶと RuntimeError。"""
    api = SalesforceAPI()
    with pytest.raises(RuntimeError):
        api.query("SELECT Id FROM Account")
    with pytest.raises(RuntimeError):
        api.report_run("report_id")
    with pytest.raises(RuntimeError):
        api.request("GET", "/path")
    with pytest.raises(RuntimeError):
        api.data_path("/path")
