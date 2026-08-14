"""comken/salesforce/__init__.py — Salesforce API 連携（requests）。

1インスタンスが1組織を受け持つ:

    from comken.salesforce import Salesforce

    with Salesforce(
        client_id=..., client_secret=..., domain_url="https://your-domain.my.salesforce.com"
    ) as sf:
        records = sf.query("SELECT Id, Name FROM Account")
        rows = sf.report.run("00O000000000001")
        sf.metrics.log_summary()

組織を増やすときは、組織ごとに Salesforce を作る。組織固有の処理が必要なら
`Salesforce` を継承して利用プロジェクト側でメソッドを足す。
認証は `oauth_credentials.py` と `oauth_refresh.py` の2方式を用意している。
`client.py` のOAuth import先が、`Salesforce.from_credentials()`で使う方式を決める。
設計の背景は docs/salesforce.md を参照。

    Salesforce             1組織ぶんの API クライアント（入口）
    ReportApi              レポート API。Salesforce.report が持っている
    CredentialsOAuth       Client Credentials Flow
    RefreshOAuth           Authorization Code + Refresh Token Flow
    ApiMetrics             API 呼び出しの計測。Salesforce.metrics が持っている
    ApiUsage               組織の 24 時間 API 消費量
    ComponentStat          呼び出し元ごとの集計
    RetryReason            リトライ理由の定数
"""

from __future__ import annotations

try:
    import requests as _requests  # noqa: F401  # 依存の有無をここで確かめるだけ
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "comken.salesforce は requests を使います。requests が入っていません。\n"
        "オフライン環境では、共有フォルダの wheel から\n"
        "  pip install --no-index --find-links <wheel置き場> requests\n"
        "で入れてください。requests を使わない機能（Excel・CSV 等）は\n"
        "comken.salesforce を import しなければ影響を受けません。"
    ) from e

from .client import Salesforce
from .metrics import ApiMetrics, ApiUsage, ComponentStat, RetryReason
from .oauth_credentials import ClientCredentialsAuth
from .oauth_credentials import OAuth as CredentialsOAuth
from .oauth_refresh import OAuth as RefreshOAuth
from .oauth_refresh import RefreshTokenAuth
from .report import ReportApi
from .rotation import SalesforceCredentialRotator

__all__ = [
    "Salesforce",
    "ReportApi",
    "ClientCredentialsAuth",
    "RefreshTokenAuth",
    "CredentialsOAuth",
    "RefreshOAuth",
    "ApiMetrics",
    "ApiUsage",
    "ComponentStat",
    "RetryReason",
    "SalesforceCredentialRotator",
]
