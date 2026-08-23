"""comken/internal/salesforce_api.py — 社内 Salesforce API 呼び出しの薄いラッパー。

``comken.toolbox.salesforce`` の API を薄くラップして ``comken.internal`` 配下から
使えるようにする。詳細は実装時に詰める。``comken/toolbox/rpa.py`` と同じパターンで、
社内 ``example_libs.v0000.salesforce`` への薄いラッパーとして機能する。
"""

from __future__ import annotations

from comken.internal.base import InternalLibraryBase

SALESFORCE_LIBRARY_NAME = "example_libs.v0000.salesforce"


class SalesforceApi:
    """社内 Salesforce API 呼び出しの薄いラッパー。

    使用例::

        with SalesforceApi() as api:
            api.query("SELECT Id FROM Account")
    """

    def __init__(self) -> None:
        self._library = InternalLibraryBase(SALESFORCE_LIBRARY_NAME)

    def __enter__(self) -> SalesforceApi:
        self._module = self._library.load()
        return self

    def __exit__(self, *args: object) -> None:
        self._module = None


__all__ = ["SalesforceApi", "SALESFORCE_LIBRARY_NAME"]
