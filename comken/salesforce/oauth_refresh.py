"""comken/salesforce/oauth_refresh.py — Refresh Token Flow"""

from __future__ import annotations

import secrets
import urllib.parse
from collections.abc import Callable

import requests

from ..exceptions import SalesforceAuthError, SalesforceConnectionError

AUTHORIZATION_PATH = "/services/oauth2/authorize"
AUTHORIZATION_CODE_GRANT = "authorization_code"
REFRESH_TOKEN_GRANT = "refresh_token"
RESPONSE_TYPE = "code"
TOKEN_PATH = "/services/oauth2/token"
TIMEOUT_SECONDS = 60


class OAuth:
    """保存済み refresh_token でアクセストークンを更新する。"""

    def __init__(
        self,
        client_id: str,
        refresh_token: str,
        domain_url: str,
        *,
        client_secret: str | None = None,
        on_refresh_token: Callable[[str], None] | None = None,
    ) -> None:
        self._client_id = client_id
        self._refresh_token = refresh_token
        self._domain_url = domain_url.rstrip("/")
        self._client_secret = client_secret
        self._on_refresh_token = on_refresh_token

    @classmethod
    def from_credentials(cls, domain_url: str, prefix: str) -> OAuth:
        """DPAPIに保存したOAuth資格情報から認証を作る。"""
        from ..credentials import Credentials, save_credential

        credentials = Credentials(prefix)

        def _save_rotated_token(refresh_token: str) -> None:
            save_credential(f"{prefix}_refresh_token", refresh_token)

        return cls(
            credentials.client_id,
            credentials.refresh_token,
            domain_url,
            client_secret=credentials.client_secret,
            on_refresh_token=_save_rotated_token,
        )

    def fetch(self) -> tuple[str, str]:
        """refresh_token を使ってアクセストークンを取得する。"""
        data = {
            "grant_type": REFRESH_TOKEN_GRANT,
            "client_id": self._client_id,
            "refresh_token": self._refresh_token,
        }
        if self._client_secret is not None:
            data["client_secret"] = self._client_secret
        body = _post_token(self._domain_url, data, secrets_to_redact=tuple(data.values()))
        rotated_token = body.get("refresh_token")
        if isinstance(rotated_token, str) and rotated_token != self._refresh_token:
            if self._on_refresh_token is not None:
                self._on_refresh_token(rotated_token)
            self._refresh_token = rotated_token
        return _token_pair(body)

    @staticmethod
    def authorization_url(
        client_id: str,
        redirect_uri: str,
        domain_url: str,
        *,
        scope: str = "api refresh_token",
        state: str | None = None,
    ) -> tuple[str, str]:
        """利用者がブラウザで開く認可 URL と CSRF 検証用 state を返す。"""
        actual_state = state or secrets.token_urlsafe(32)
        query = urllib.parse.urlencode(
            {
                "response_type": RESPONSE_TYPE,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": actual_state,
            }
        )
        return f"{domain_url.rstrip('/')}{AUTHORIZATION_PATH}?{query}", actual_state

    @classmethod
    def exchange_code(
        cls,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
        domain_url: str,
        *,
        on_refresh_token: Callable[[str], None] | None = None,
    ) -> OAuth:
        """認可コードを交換し、取得した refresh_token を持つ認証部品を返す。"""
        token_request = {
            "grant_type": AUTHORIZATION_CODE_GRANT,
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        body = _post_token(
            domain_url.rstrip("/"),
            token_request,
            secrets_to_redact=(client_secret, code),
        )
        refresh_token = body.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise SalesforceAuthError(200, "認証レスポンスに refresh_token がありません")
        if on_refresh_token is not None:
            on_refresh_token(refresh_token)
        return cls(
            client_id,
            refresh_token,
            domain_url,
            client_secret=client_secret,
            on_refresh_token=on_refresh_token,
        )


def _post_token(
    domain_url: str,
    data: dict[str, str],
    *,
    secrets_to_redact: tuple[str, ...],
) -> dict:
    url = f"{domain_url}{TOKEN_PATH}"
    try:
        response = requests.post(url, data=data, timeout=TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as e:
        raise SalesforceConnectionError(url, e) from e
    if response.status_code >= 400:
        detail = response.text
        for secret in secrets_to_redact:
            if secret:
                detail = detail.replace(secret, "***")
        raise SalesforceAuthError(response.status_code, detail)
    try:
        body = response.json()
    except ValueError as e:
        raise SalesforceAuthError(response.status_code, "認証レスポンスの形式が不正です") from e
    if not isinstance(body, dict):
        raise SalesforceAuthError(response.status_code, "認証レスポンスの形式が不正です")
    return body


def _token_pair(body: dict) -> tuple[str, str]:
    try:
        return body["access_token"], body["instance_url"]
    except (KeyError, TypeError) as e:
        raise SalesforceAuthError(200, "認証レスポンスの形式が不正です") from e


# 方式を明示して直接使いたい場合の互換名。切替用の名前はOAuth。
RefreshTokenAuth = OAuth

__all__ = ["OAuth", "RefreshTokenAuth"]
