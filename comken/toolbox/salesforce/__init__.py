"""comken/toolbox/salesforce/__init__.py — Salesforce API 連携（requests）。

1インスタンスが1組織を受け持つ。**入口は組織クラス**（`sites/`）:

    from comken.toolbox.salesforce.sites import Solution

    with Solution() as sf:
        records = sf.query("SELECT Id, Name FROM Account")
        rows = sf.report.get("00O000000000001")
        sf.metrics.log_summary()

URL と認証情報のシステム名は組織クラスがクラス定数として持つので、
呼び出し側は何も渡さなくてよい。組織を増やすときは `sites/` にクラスを足す。
**認証の既定は Refresh Token Flow。** 組織クラスをそのまま使えばこれになる。

    with Solution() as sf:                                    # 既定（本番もこれ）
        ...

Client Credentials Flow は `client_secret` だけでアクセストークンを取れてしまい、
漏えいすると実行ユーザーとして操作されるため、本番では使わない。
**開発中に手元で動かしたいときだけ** `auth=` で明示的に渡す。

    from comken.toolbox.salesforce import ClientCredentialsOAuth

    with Solution(auth=ClientCredentialsOAuth(cid, secret, domain)) as sf:  # 開発時だけ
        ...

設計の背景は docs/開発/salesforce-authentication.md を参照。

    SalesforceBase         1組織ぶんの API クライアントの土台（組織クラスで継承する）
    BulkQueryAPI           Bulk API 2.0 のクエリジョブ。SalesforceBase.bulk_query が持っている
    BulkIngestAPI          Bulk API 2.0 の Ingest ジョブ。SalesforceBase.bulk_ingest が持っている
    ReportAPI              レポート API。SalesforceBase.report が持っている
    DataLoaderCLI          Salesforce Data Loader の CLI 呼び出し（サブプロセス実行）
    DataLoaderResult       DataLoaderCLI.run() の戻り値
    RefreshTokenOAuth      Authorization Code + Refresh Token Flow（既定）
    ClientCredentialsOAuth Client Credentials Flow（開発時に auth= で渡す）
    APIMetrics             API 呼び出しの計測。SalesforceBase.metrics が持っている
    APIUsage               組織の 24 時間 API 消費量
    ComponentStat          呼び出し元ごとの集計
    RetryReason            リトライ理由の定数
"""

from types import ModuleType
from typing import TYPE_CHECKING

from comken.toolbox.salesforce.bulk_ingest import BulkIngestAPI, BulkIngestResult
from comken.toolbox.salesforce.bulk_query import BulkQueryAPI
from comken.toolbox.salesforce.dataloader import DataLoaderCLI, DataLoaderResult
from comken.toolbox.salesforce.metrics import (
    APIMetrics,
    APIUsage,
    ComponentStat,
    RetryReason,
)
from comken.toolbox.salesforce.report import ReportAPI

# requests の存在チェックだけ先に行う。依存が無い環境でもこのパッケージを
# import だけはできるようにしておき、実際に API を叩く経路
# （`oauth_credentials` / `oauth_refresh` / `client` / `rotation` 等）で
# `import requests` が走った時点で ImportError が出る。
_requests: ModuleType | None
try:
    import requests as _requests  # 依存の有無をここで確かめるだけ
except ImportError:
    _requests = None

# `requests` を直接 import するモジュールは遅延ロードする。`report` のような
# requests 非依存モジュールだけ使う場合（BO 環境）にパッケージ全体を
# import 可能にするため
_LAZY_TARGETS: dict[str, str] = {
    "SalesforceBase": "comken.toolbox.salesforce.client",
    "ClientCredentialsOAuth": "comken.toolbox.salesforce.auth.oauth_credentials",
    "RefreshTokenOAuth": "comken.toolbox.salesforce.auth.oauth_refresh",
    "SalesforceCredentialRotator": "comken.toolbox.salesforce.auth.rotation",
}

if TYPE_CHECKING:
    # 型チェッカー（pyright 等）は __getattr__ の戻り値を追えず、遅延対象を
    # 全て object 型と見なしてしまう（継承・属性アクセス・呼び出しが軒並み
    # エラーになる）。TYPE_CHECKING はここでだけ True 扱いになり実行時には
    # 一切評価されないため、requests 非依存という遅延importの目的を壊さずに
    # 型だけ正しく解決できる。
    from comken.toolbox.salesforce.auth.oauth_credentials import ClientCredentialsOAuth
    from comken.toolbox.salesforce.auth.oauth_refresh import RefreshTokenOAuth
    from comken.toolbox.salesforce.auth.rotation import SalesforceCredentialRotator
    from comken.toolbox.salesforce.client import SalesforceBase


def __getattr__(name: str) -> object:
    """`from ... import X` の X を必要になったタイミングでだけ import する。

    Raises:
        AttributeError: 定義されていない属性を要求したとき。
    """
    module_name = _LAZY_TARGETS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """`dir(comken.toolbox.salesforce)` で遅延対象も返す。"""
    return sorted(set(__all__) | set(_LAZY_TARGETS))


__all__ = [
    "SalesforceBase",
    "ReportAPI",
    "BulkQueryAPI",
    "BulkIngestAPI",
    "BulkIngestResult",
    "DataLoaderCLI",
    "DataLoaderResult",
    "ClientCredentialsOAuth",
    "RefreshTokenOAuth",
    "APIMetrics",
    "APIUsage",
    "ComponentStat",
    "RetryReason",
    "SalesforceCredentialRotator",
]
