"""comken/internal/salesforce_api.py — 社内 Salesforce API 呼び出しの薄い玄関。

``comken.toolbox.salesforce`` の SalesforceBase を介さず、
``example_libs.v0000.salesforce``（社内ライブラリ）を直接ロードする。
メソッドは提供しない（下地のみ）。

    with SalesforceApi() as api:
        api._module.<method>(...)   # 社内ライブラリのメソッドを直接呼ぶ

メソッドのラッパ追加は社内ライブラリの API 仕様確認後に書き足す。
"""

from __future__ import annotations

from comken.internal.base import InternalLibraryBase

SALESFORCE_LIBRARY_NAME = "example_libs.v0000.salesforce"


class SalesforceApi:
    """社内 Salesforce API 呼び出しの薄い玄関。

    ``example_libs.v0000.salesforce`` を ``comken.internal.base.InternalLibraryBase``
    経由でロードするコンテキストマネージャ。``__enter__`` でモジュールをロードし、
    ``__exit__`` で開放する。
    現状は下地の実装のみで、メソッド（query / report_run / request 等）は
    提供しない。メソッドの追加は社内ライブラリの API 仕様確認後に書き足す。

    使用例::

        with SalesforceApi() as api:
            api._module.query("SELECT Id FROM Account")  # 直接モジュールアクセス

    社内ライブラリが見つからない場合、
    ``comken.internal.exceptions.InternalLibraryNotFoundError`` が送出される。

    Raises:
        InternalLibraryNotFoundError: 社内ライブラリ ``example_libs.v0000.salesforce``
            が import できない場合。
    """

    def __init__(self) -> None:
        self._library = InternalLibraryBase(SALESFORCE_LIBRARY_NAME)

    def __enter__(self) -> SalesforceApi:
        self._module = self._library.load()
        return self

    def __exit__(self, *args: object) -> None:
        self._module = None


__all__ = ["SalesforceApi", "SALESFORCE_LIBRARY_NAME"]
