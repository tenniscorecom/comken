"""comken/internal/salesforce_api.py — 社内 Salesforce API 呼び出しの薄い玄関。

``comken.toolbox.salesforce.SalesforceBase`` と同等の API を提供する薄いラッパ。
認証（Auth Refresh Token / Rotation / Metrics）は toolbox/salesforce 側に残し、
本クラスは社内ライブラリ ``example_libs.salesforce`` のメソッドを呼ぶ
ラッパとして機能する。

``example_libs.salesforce`` は ``__enter__`` 内で静的 import する。
``ModuleNotFoundError`` は ``comken.internal.base.raise_if_target_missing`` で
``InternalLibraryNotFoundError`` に変換する。 静的 import にしたのは
pyright の型検査・IDE 補完を効かせるためで、ライブラリのバージョンに
依存しなくなったので importlib ベースの動的 import は必要なくなった。
最終的には社内ライブラリを comken に直接取り込むため、バージョンチェックは
実装しない（社内ライブラリの存在自体が一時的）。
"""

from __future__ import annotations

from typing import Any

from comken.core.table import Table
from comken.core.timer import measure
from comken.exceptions import TableNotOpenError
from comken.internal.base import raise_if_target_missing

SALESFORCE_LIBRARY_NAME = "example_libs.salesforce"


class SalesforceAPI:
    """社内 Salesforce API 呼び出しの薄い玄関。

    ``example_libs.salesforce`` を ``__enter__`` 内で静的 import し、
    ``ModuleNotFoundError`` を ``comken.internal.base.raise_if_target_missing``
    経由で ``InternalLibraryNotFoundError`` に変換する。

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
        InternalLibraryNotFoundError: 社内ライブラリ ``example_libs.salesforce``
            が import できない場合。
    """

    CREDENTIAL_PREFIX = "SALESFORCE"

    def __init__(self) -> None:
        # 社内ライブラリ ``example_libs.salesforce`` のメソッドは comken 側に
        # 型情報がない。 規約上、 Protocol のような複雑な仕組みは導入せず、
        # 局所的に ``Any`` を使ってメソッド呼び出しを許可する。
        self._module: Any | None = None

    def __enter__(self) -> SalesforceAPI:
        try:
            # 社内 LAN にだけ存在する（自宅PC・CI では未インストール）
            from example_libs import salesforce  # type: ignore[reportMissingImports]
        except ModuleNotFoundError as exc:
            raise_if_target_missing(SALESFORCE_LIBRARY_NAME, exc)
            raise
        self._module = salesforce
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
    def query(self, soql: str) -> Table:
        """SOQL クエリを実行し、結果を Table で返す。

        列は SOQL からはメタデータが取れないため、**1 件目から推測**する。
        0 件のときは列が空の ``Table`` を返す（``records[0]`` からの推測に
        依存しない）。``toolbox.salesforce.SalesforceBase.query()`` と同じ前提。

        Args:
            soql: 実行する SOQL クエリ文字列。

        Returns:
            SOQL の結果を表す ``Table``。

        Raises:
            TableNotOpenError: ``with`` ブロック外で呼ばれた場合。
        """
        if self._module is None:
            raise TableNotOpenError("SalesforceAPI")
        records = self._module.query(soql)
        # 0 件のときは ``records[0]`` を見ずに空の列を返す（明示的に書く）
        columns = list(records[0]) if records else []
        return Table(columns, records)

    @measure
    def report_run(self, report_id: str) -> Table:
        """レポートを実行し、結果を Table で返す。

        社内ライブラリ ``example_libs.salesforce`` の ``report_run`` は
        ``SalesforceBase.report.get()`` と同じ ``[{表示名: 値}, ...]`` 形式を返す
        ため、1 件目から列を推測する。0 件のときは列が空の ``Table`` を返す
        （``records[0]`` からの推測に依存しない）。 ``toolbox.salesforce`` 側の
        ``get()`` は ``detailColumns`` から列を取れるため列落ちしないが、
        社内ライブラリ側の戻り値スキーマが同等かどうかは呼び出し側で必要なら
        確認すること。

        Args:
            report_id: 実行するレポートの Id。

        Returns:
            レポート結果を表す ``Table``。

        Raises:
            TableNotOpenError: ``with`` ブロック外で呼ばれた場合。
        """
        if self._module is None:
            raise TableNotOpenError("SalesforceAPI")
        records = self._module.report_run(report_id)
        columns = list(records[0]) if records else []
        return Table(columns, records)


__all__ = ["SalesforceAPI", "SALESFORCE_LIBRARY_NAME"]
