"""comken/toolbox/salesforce/__init__.py — Salesforce API 連携（requests）。

1インスタンスが1組織を受け持つ。**入口は組織クラス**（`sites/`）:

    from comken.toolbox.salesforce.sites import Sandbox

    with Sandbox() as sf:
        records = sf.query("SELECT Id, Name FROM Account")
        rows = sf.report.run("00O000000000001")
        sf.metrics.log_summary()

URL と認証情報のシステム名は組織クラスがクラス定数として持つので、
呼び出し側は何も渡さなくてよい。組織を増やすときは `sites/` にクラスを足す。
**認証の既定は Refresh Token Flow。** 組織クラスをそのまま使えばこれになる。

    with Sandbox() as sf:                                    # 既定（本番もこれ）
        ...

Client Credentials Flow は `client_secret` だけでアクセストークンを取れてしまい、
漏えいすると実行ユーザーとして操作されるため、本番では使わない。
**開発中に手元で動かしたいときだけ** `auth=` で明示的に渡す。

    from comken.toolbox.salesforce import ClientCredentialsAuth

    with Sandbox(auth=ClientCredentialsAuth(cid, secret, domain)) as sf:  # 開発時だけ
        ...

設計の背景は docs/開発/salesforce-authentication.md を参照。

    SalesforceBase         1組織ぶんの API クライアントの土台（組織クラスで継承する）
    ReportApi              レポート API。SalesforceBase.report が持っている
    RefreshTokenAuth       Authorization Code + Refresh Token Flow（既定）
    ClientCredentialsAuth  Client Credentials Flow（開発時に auth= で渡す）
    ApiMetrics             API 呼び出しの計測。SalesforceBase.metrics が持っている
    ApiUsage               組織の 24 時間 API 消費量
    ComponentStat          呼び出し元ごとの集計
    RetryReason            リトライ理由の定数
"""

try:
    import requests as _requests  # noqa: F401  # 依存の有無をここで確かめるだけ
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "comken.toolbox.salesforce は requests を使います。requests が入っていません。\n"
        "オフライン環境では、共有フォルダの wheel から\n"
        "  pip install --no-index --find-links <wheel置き場> requests\n"
        "で入れてください。requests を使わない機能（Excel・CSV 等）は\n"
        "comken.toolbox.salesforce を import しなければ影響を受けません。"
    ) from e

from comken.toolbox.salesforce.client import SalesforceBase
from comken.toolbox.salesforce.metrics import ApiMetrics, ApiUsage, ComponentStat, RetryReason
from comken.toolbox.salesforce.oauth_credentials import ClientCredentialsAuth
from comken.toolbox.salesforce.oauth_refresh import RefreshTokenAuth
from comken.toolbox.salesforce.report import ReportApi
from comken.toolbox.salesforce.rotation import SalesforceCredentialRotator

__all__ = [
    "SalesforceBase",
    "ReportApi",
    "ClientCredentialsAuth",
    "RefreshTokenAuth",
    "ApiMetrics",
    "ApiUsage",
    "ComponentStat",
    "RetryReason",
    "SalesforceCredentialRotator",
]
