"""comken/toolbox/salesforce/__init__.py — Salesforce API 連携（requests）。

1インスタンスが1組織を受け持つ。**入口は組織クラス**（`sites/`）:

    from comken.toolbox.salesforce.sites import Sandbox

    with Sandbox() as sf:
        records = sf.query("SELECT Id, Name FROM Account")
        rows = sf.report.get("00O000000000001")
        sf.metrics.log_summary()

URL と認証情報のシステム名は組織クラスがクラス定数として持つので、
呼び出し側は何も渡さなくてよい。組織を増やすときは `sites/` にクラスを足す。
**認証の既定は Refresh Token Flow。** 組織クラスをそのまま使えばこれになる。

    with Sandbox() as sf:                                    # 既定（本番もこれ）
        ...

Client Credentials Flow は `client_secret` だけでアクセストークンを取れてしまい、
漏えいすると実行ユーザーとして操作されるため、本番では使わない。
**開発中に手元で動かしたいときだけ** `auth=` で明示的に渡す。

    from comken.toolbox.salesforce import ClientCredentialsOAuth

    with Sandbox(auth=ClientCredentialsOAuth(cid, secret, domain)) as sf:  # 開発時だけ
        ...

設計の背景は docs/開発/salesforce-authentication.md を参照。

    SalesforceBase         1組織ぶんの API クライアントの土台（組織クラスで継承する）
    ReportAPI              レポート API。SalesforceBase.report が持っている
    RefreshTokenOAuth      Authorization Code + Refresh Token Flow（既定）
    ClientCredentialsOAuth Client Credentials Flow（開発時に auth= で渡す）
    APIMetrics             API 呼び出しの計測。SalesforceBase.metrics が持っている
    APIUsage               組織の 24 時間 API 消費量
    ComponentStat          呼び出し元ごとの集計
    RetryReason            リトライ理由の定数
"""

from types import ModuleType

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
    "ClientCredentialsOAuth": "comken.toolbox.salesforce.oauth_credentials",
    "RefreshTokenOAuth": "comken.toolbox.salesforce.oauth_refresh",
    "SalesforceCredentialRotator": "comken.toolbox.salesforce.rotation",
}


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
    "ClientCredentialsOAuth",
    "RefreshTokenOAuth",
    "APIMetrics",
    "APIUsage",
    "ComponentStat",
    "RetryReason",
    "SalesforceCredentialRotator",
]
