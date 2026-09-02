"""SalesforceAPI の下地実装テスト。

``example_libs.salesforce`` が import できない環境でも、インスタンス化と
SALESFORCE_LIBRARY_NAME 定数の確認が可能。
"""

from __future__ import annotations

import sys
from unittest import mock

import pytest

from comken.exceptions import TableNotOpenError
from comken.internal.exceptions import InternalLibraryNotFoundError
from comken.internal.salesforce_api import SALESFORCE_LIBRARY_NAME, SalesforceAPI


@pytest.fixture
def fake_example_libs_salesforce(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """``example_libs`` / ``example_libs.salesforce`` のダミーを ``sys.modules`` へ注入する。"""
    fake_salesforce = mock.Mock()
    fake_example_libs = mock.Mock()
    fake_example_libs.salesforce = fake_salesforce
    monkeypatch.setitem(sys.modules, "example_libs", fake_example_libs)
    monkeypatch.setitem(sys.modules, "example_libs.salesforce", fake_salesforce)
    return fake_salesforce


def _remove_example_libs(monkeypatch: pytest.MonkeyPatch) -> None:
    """``example_libs`` が無い状態を強制する。"""
    for name in ("example_libs.salesforce", "example_libs"):
        monkeypatch.delitem(sys.modules, name, raising=False)


def test_salesforce_library_name_is_correct() -> None:
    """SALESFORCE_LIBRARY_NAME 定数の値を確認する（バージョン無し）。"""
    assert SALESFORCE_LIBRARY_NAME == "example_libs.salesforce"


def test_module_loads_on_enter(fake_example_libs_salesforce: mock.Mock) -> None:
    """__enter__ でモジュールが読み込まれる。"""
    with SalesforceAPI() as api:
        assert api._module is fake_example_libs_salesforce


def test_module_is_none_on_exit(fake_example_libs_salesforce: mock.Mock) -> None:
    """__exit__ で _module が None になる。"""
    api = SalesforceAPI()
    api.__enter__()
    assert api._module is fake_example_libs_salesforce
    api.__exit__(None, None, None)
    assert api._module is None


def test_internal_library_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """``example_libs`` が無いと ``__enter__`` で ``InternalLibraryNotFoundError`` が出る。"""
    _remove_example_libs(monkeypatch)
    with (
        pytest.raises(InternalLibraryNotFoundError),
        SalesforceAPI(),
    ):
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


def test_query_delegates_to_module(fake_example_libs_salesforce: mock.Mock) -> None:
    """query() は社内モジュールの query() を呼ぶ。"""
    fake_example_libs_salesforce.query.return_value = [{"Id": "001"}]
    with SalesforceAPI() as api:
        result = api.query("SELECT Id FROM Account")
    assert result == [{"Id": "001"}]
    fake_example_libs_salesforce.query.assert_called_once_with("SELECT Id FROM Account")


def test_report_run_delegates_to_module(fake_example_libs_salesforce: mock.Mock) -> None:
    """report_run() は社内モジュールの report_run() を呼ぶ。"""
    fake_example_libs_salesforce.report_run.return_value = [{"row": 1}]
    with SalesforceAPI() as api:
        result = api.report_run("report_id_123")
    assert result == [{"row": 1}]
    fake_example_libs_salesforce.report_run.assert_called_once_with("report_id_123")


def test_request_delegates_to_module(fake_example_libs_salesforce: mock.Mock) -> None:
    """request() は社内モジュールの request() を呼ぶ。"""
    fake_example_libs_salesforce.request.return_value = {"success": True}
    with SalesforceAPI() as api:
        result = api.request("GET", "/path", component="/v1", body={"key": "value"})
    assert result == {"success": True}
    fake_example_libs_salesforce.request.assert_called_once_with(
        "GET", "/path", component="/v1", body={"key": "value"}
    )


def test_data_path_delegates_to_module(fake_example_libs_salesforce: mock.Mock) -> None:
    """data_path() は社内モジュールの data_path() を呼ぶ。"""
    fake_example_libs_salesforce.data_path.return_value = "/services/data/v1/path"
    with SalesforceAPI() as api:
        result = api.data_path("/path")
    assert result == "/services/data/v1/path"
    fake_example_libs_salesforce.data_path.assert_called_once_with("/path")


def test_credential_prefix_constant() -> None:
    """CREDENTIAL_PREFIX クラス定数の値を確認する。"""
    assert SalesforceAPI.CREDENTIAL_PREFIX == "SALESFORCE"


def test_methods_raise_outside_with_block() -> None:
    """with ブロック外でメソッドを呼ぶと TableNotOpenError。"""
    api = SalesforceAPI()
    with pytest.raises(TableNotOpenError):
        api.query("SELECT Id FROM Account")
    with pytest.raises(TableNotOpenError):
        api.report_run("report_id")
    with pytest.raises(TableNotOpenError):
        api.request("GET", "/path")
    with pytest.raises(TableNotOpenError):
        api.data_path("/path")
