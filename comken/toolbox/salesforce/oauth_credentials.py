"""comken/toolbox/salesforce/oauth_credentials.py — Client Credentials Flow

``client_id`` と ``client_secret`` だけでアクセストークンを取りに行く方式。
リフレッシュトークンを使わないため、運用負荷が低い（失効・再認可の手続きが要らない）。

**client_secret だけでアクセストークンが取れてしまう点に注意。** Salesforce 側
（ECA）で「Run As」を有効にしておかないと、アクセスが API 実行ユーザー由来ではなく
接続アプリ所有者の権限で走る。``comken sf rotate`` で secret をローテーションできる。
"""

# 定義中の ClientCredentialsOAuth を戻り値の型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
from typing import Self

import requests

from comken.core.timer import measure
from comken.exceptions import SalesforceAuthError, SalesforceConnectionError

logger = logging.getLogger(__name__)

TOKEN_PATH = "/services/oauth2/token"
GRANT_TYPE = "client_credentials"
TIMEOUT_SECONDS = 60


class ClientCredentialsOAuth:
    """client_id と client_secret でアクセストークンを取得する。"""

    def __init__(self, client_id: str, client_secret: str, domain_url: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._domain_url = domain_url.rstrip("/")

    @classmethod
    def from_credentials(cls, domain_url: str, prefix: str) -> Self:
        """DPAPIに保存したclient_idとclient_secretから認証を作る。"""
        from comken.toolbox.credentials import Credentials

        credentials = Credentials(prefix)
        return cls(credentials.client_id, credentials.client_secret, domain_url)

    @measure
    def fetch(self) -> tuple[str, str]:
        """アクセストークンと instance_url を取得する。"""
        url = f"{self._domain_url}{TOKEN_PATH}"
        try:
            response = requests.post(
                url,
                data={
                    "grant_type": GRANT_TYPE,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException as e:
            raise SalesforceConnectionError(url, e) from e
        if response.status_code >= 400:
            detail = response.text
            if self._client_secret:
                detail = detail.replace(self._client_secret, "***")
            raise SalesforceAuthError(response.status_code, detail)
        try:
            body = response.json()
            access_token = body["access_token"]
            instance_url = body["instance_url"]
        except (ValueError, KeyError, TypeError) as e:
            raise SalesforceAuthError(response.status_code, "認証レスポンスの形式が不正です") from e
        logger.debug("アクセストークンを取得しました: %s", instance_url)
        return access_token, instance_url


__all__ = ["ClientCredentialsOAuth"]
