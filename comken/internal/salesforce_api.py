"""comken/internal/salesforce_api.py — 社内 Salesforce API 呼び出しの薄い玄関。

``comken.toolbox.salesforce.SalesforceBase`` と同等の API を提供する薄いラッパ。
認証（Auth Refresh Token / Rotation / Metrics）は toolbox/salesforce 側に残し、
本クラスは社内ライブラリ ``example_libs.v0000.salesforce`` のメソッドを呼ぶ
ラッパとして機能する。
最終的には社内ライブラリを comken に直接取り込むため、バージョンチェックは
実装しない（社内ライブラリの存在自体が一時的）。
"""

from __future__ import annotations

from typing import Any

from comken.core.timer import measure
from comken.exceptions import TableNotOpenError
from comken.internal.base import InternalLibraryBase
from comken.internal.names import INTERNAL_LIBRARY_ROOT

SALESFORCE_LIBRARY_NAME = f"{INTERNAL_LIBRARY_ROOT}.salesforce"


class SalesforceAPI:
    """社内 Salesforce API 呼び出しの薄い玄関。

    ``example_libs.v0000.salesforce`` を ``comken.internal.base.InternalLibraryBase``
    経由でロードするコンテキストマネージャ。``__enter__`` でモジュールをロードし、
    ``__exit__`` で開放する。

    使用例::

        with SalesforceAPI() as api:
            rows = api.query("SELECT Id, Name FROM Account")

    認証（Auth Refresh Token / Rotation / Metrics）は toolbox/salesforce 側に
    集約しており、本クラスでは扱わない。

    Attributes:
        CREDENTIAL_PREFIX: 認証情報のキー名の頭（社内ライブラリ用）。

    社内ライブラリが見つからない場合、
    ``comken.internal.exceptions.InternalLibraryNotFoundError`` が送出される。

    Raises:
        InternalLibraryNotFoundError: 社内ライブラリ ``example_libs.v0000.salesforce``
            が import できない場合。
    """

    CREDENTIAL_PREFIX = "SALESFORCE"

    def __init__(self) -> None:
        self._library = InternalLibraryBase(SALESFORCE_LIBRARY_NAME)
        # 社内ライブラリ ``example_libs.v0000.salesforce`` のメソッドは comken 側に
        # 型情報がない。 規約上、 Protocol のような複雑な仕組みは導入せず、
        # 局所的に ``Any`` を使ってメソッド呼び出しを許可する。
        self._module: Any | None = None

    def __enter__(self) -> SalesforceAPI:
        self._module = self._library.load()
        return self

    def __exit__(self, *args: object) -> None:
        self._module = None

    def request(
        self,
        method: str,
        path: str,
        *,
        component: str = "",
        body: dict | None = None,
    ) -> dict:
        """社内ライブラリ経由で HTTP リクエストを送り、JSON を返す。

        Args:
            method: HTTP メソッド（GET / POST / PATCH / DELETE）。
            path: API のパス。
            component: 計測での呼び出し元の区別。
            body: JSON で送る辞書（省略可）。

        Returns:
            レスポンスの JSON を辞書に変換したもの。

        Raises:
            TableNotOpenError: ``with`` ブロック外で呼ばれた場合。
        """
        if self._module is None:
            raise TableNotOpenError("SalesforceAPI")
        return self._module.request(method, path, component=component, body=body)

    def data_path(self, path: str) -> str:
        """data API のエンドポイント URL を返す。

        Args:
            path: API の相対パス。

        Returns:
            バージョン付きのエンドポイント URL。

        Raises:
            TableNotOpenError: ``with`` ブロック外で呼ばれた場合。
        """
        if self._module is None:
            raise TableNotOpenError("SalesforceAPI")
        return self._module.data_path(path)

    @measure
    def query(self, soql: str) -> list[dict]:
        """SOQL クエリを実行し、結果を list[dict] で返す。

        Args:
            soql: 実行する SOQL クエリ文字列。

        Returns:
            レコードの辞書のリスト。

        Raises:
            TableNotOpenError: ``with`` ブロック外で呼ばれた場合。
        """
        if self._module is None:
            raise TableNotOpenError("SalesforceAPI")
        return self._module.query(soql)

    @measure
    def report_run(self, report_id: str) -> list[dict]:
        """レポートを実行し、結果を list[dict] で返す。

        Args:
            report_id: 実行するレポートの Id。

        Returns:
            レポート結果の辞書のリスト。

        Raises:
            TableNotOpenError: ``with`` ブロック外で呼ばれた場合。
        """
        if self._module is None:
            raise TableNotOpenError("SalesforceAPI")
        return self._module.report_run(report_id)


__all__ = ["SalesforceAPI", "SALESFORCE_LIBRARY_NAME"]
