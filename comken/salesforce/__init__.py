"""comken/salesforce/__init__.py — Salesforce API 連携（requests）。

1インスタンスが1組織を受け持つ。**入口は組織クラス**（`sites/`）:

    from comken.salesforce.sites import Sandbox

    with Sandbox() as sf:
        records = sf.query("SELECT Id, Name FROM Account")
        rows = sf.report.run("00O000000000001")
        sf.metrics.log_summary()

URL と認証情報のシステム名は組織クラスがクラス定数として持つので、
呼び出し側は何も渡さなくてよい。組織を増やすときは `sites/` にクラスを足す。
認証は `oauth_credentials.py` と `oauth_refresh.py` の2方式を用意している。
`client.py` のOAuth import先が、どちらを使うかを決める。
設計の背景は docs/salesforce.md を参照。

    SalesforceBase         1組織ぶんの API クライアントの土台（組織クラスで継承する）
    ReportApi              レポート API。SalesforceBase.report が持っている
    CredentialsOAuth       Client Credentials Flow
    RefreshOAuth           Authorization Code + Refresh Token Flow
    ApiMetrics             API 呼び出しの計測。SalesforceBase.metrics が持っている
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

from .client import SalesforceBase
from .metrics import ApiMetrics, ApiUsage, ComponentStat, RetryReason
from .oauth_credentials import ClientCredentialsAuth
from .oauth_credentials import OAuth as CredentialsOAuth
from .oauth_refresh import OAuth as RefreshOAuth
from .oauth_refresh import RefreshTokenAuth
from .report import ReportApi
from .rotation import SalesforceCredentialRotator

__all__ = [
    "SalesforceBase",
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
