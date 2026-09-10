"""comken/toolbox/salesforce/auth/oauth_refresh.py — Refresh Token Flow

初回に認可コードから ``refresh_token`` を取り、以降は ``refresh_token`` で
アクセストークンを更新し続ける方式。Salesforce 側で refresh_token を
ローテーションして返してきた場合は、新トークンを DPAPI に保存する
（``from_credentials`` は ``_on_refresh_token_via_credentials``、
``exchange_code(prefix=...)`` は ``_on_refresh_token_via_prefix`` が組み立てる）。

DPAPI の保管形式は ``{prefix: {"api_refresh_token": ...}}`` の入れ子構造。
項目名に ``api_`` を付けているのは、Salesforce 以外の認証情報（ブラウザの
ログインパスワード等）と区別するため（この項目名は Salesforce の認証情報
専用で、他のサイトの `Credentials` が同じ項目名を使う必要はない）。

``from_credentials`` は client_id 等を読むのに ``Credentials(prefix)`` を
既に作っているため、書き戻しも**同じインスタンス**の ``Credentials.save()``
を使う（読み書きで prefix を渡す場所が分かれると、将来どちらかだけ prefix の
扱いを変えたときに気づけずずれる事故につながる）。一方 ``exchange_code`` は
初回登録で読み込みが無い（まだ何も登録されていない）ため、書き込み専用に
その場で ``Credentials(prefix)`` を作る。
"""

# 定義中の RefreshTokenOAuth を戻り値の型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
import secrets
import urllib.parse
from collections.abc import Callable
from typing import TYPE_CHECKING, Self

import requests

from comken.core.timer import measure
from comken.exceptions import SalesforceAuthError, SalesforceConnectionError

if TYPE_CHECKING:
    from comken.toolbox.credentials import Credentials

logger = logging.getLogger(__name__)

AUTHORIZATION_PATH = "/services/oauth2/authorize"
AUTHORIZATION_CODE_GRANT = "authorization_code"
REFRESH_TOKEN_GRANT = "refresh_token"
RESPONSE_TYPE = "code"
TOKEN_PATH = "/services/oauth2/token"
TIMEOUT_SECONDS = 60


def _on_refresh_token_via_credentials(credentials: Credentials) -> Callable[[str], None]:
    """新しい refresh_token を、読み込みに使った Credentials と同じ site へ書き戻す。

    ``from_credentials`` が使う。 prefix 文字列を経由して別途
    ``Credentials(prefix)`` を作り直すのではなく、 読み込みに使った同じ
    インスタンスの ``save()`` を使うことで、 読み書きが必ず同じ site を指す
    ようにする。
    """

    def _save(refresh_token: str) -> None:
        logger.debug("新しい refresh_token を DPAPI へ保存します")
        credentials.api_refresh_token = refresh_token
        credentials.save()
        logger.debug("refresh_token を DPAPI へ保存しました")

    return _save


def _on_refresh_token_via_prefix(prefix: str) -> Callable[[str], None]:
    """新しい refresh_token を DPAPI（ ``{prefix: {"api_refresh_token": ...}}`` ）へ書き戻す。

    ``exchange_code(prefix=...)`` が使う。初回登録の時点では読み込みに使った
    Credentials が無いため、書き込み専用にその場でインスタンスを作る。
    """

    def _save(refresh_token: str) -> None:
        from comken.toolbox.credentials import save_credential

        logger.debug("新しい refresh_token を DPAPI へ保存します: prefix=%s", prefix)
        save_credential(prefix, "api_refresh_token", refresh_token)
        logger.debug("refresh_token を DPAPI へ保存しました: prefix=%s", prefix)

    return _save


class RefreshTokenOAuth:
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
    def from_credentials(cls, domain_url: str, prefix: str) -> Self:
        """DPAPIに保存したOAuth資格情報から認証を作る。"""
        from comken.toolbox.credentials import Credentials

        logger.debug(
            "DPAPI から OAuth 資格情報を読みます: prefix=%s domain_url=%s", prefix, domain_url
        )
        credentials = Credentials(prefix)
        # 値そのものはログに出さない（client_id / client_secret / refresh_token は秘密）
        return cls(
            credentials.api_client_id,
            credentials.api_refresh_token,
            domain_url,
            client_secret=credentials.api_client_secret,
            on_refresh_token=_on_refresh_token_via_credentials(credentials),
        )

    @measure
    def request_token(self) -> tuple[str, str]:
        """refresh_token を使ってアクセストークンを取得する。"""
        data = {
            "grant_type": REFRESH_TOKEN_GRANT,
            "client_id": self._client_id,
            "refresh_token": self._refresh_token,
        }
        if self._client_secret is not None:
            data["client_secret"] = self._client_secret
        logger.debug(
            "refresh_token でアクセストークンを取得します: domain_url=%s client_secret=%s",
            self._domain_url,
            "あり" if self._client_secret else "なし",
        )
        body = _post_token(self._domain_url, data, secrets_to_redact=tuple(data.values()))
        rotated_token = body.get("refresh_token")
        if isinstance(rotated_token, str) and rotated_token != self._refresh_token:
            logger.debug("Salesforce 側で refresh_token がローテーションされたので差し替えます")
            if self._on_refresh_token is not None:
                self._on_refresh_token(rotated_token)
            self._refresh_token = rotated_token
        access_token, instance_url = _token_pair(body)
        logger.debug("アクセストークンを取得しました: instance_url=%s", instance_url)
        return access_token, instance_url

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
        # state は CSRF 検証用の使い捨て値だが、認可の秘密の一部なのでログには出さない
        logger.debug(
            "認可 URL を組み立てます: domain_url=%s redirect_uri=%s scope=%s state=%s",
            domain_url,
            redirect_uri,
            scope,
            "指定あり" if state else "自動生成",
        )
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
        prefix: str = "",
        on_refresh_token: Callable[[str], None] | None = None,
    ) -> Self:
        """認可コードを交換し、取得した refresh_token を持つ認証部品を返す。

        初回に受け取った refresh_token を DPAPI へ書き戻す処理は、
        呼び出し側で毎回書かなくてよいよう ``prefix`` を渡すだけで済む
        （``from_credentials`` と同じ書き戻し先: ``{prefix: {"api_refresh_token": ...}}``）。
        独自の保存先を使うときだけ ``on_refresh_token`` を明示的に渡す
        （その場合は ``prefix`` より優先する）。
        """
        resolved_callback = on_refresh_token or (
            _on_refresh_token_via_prefix(prefix) if prefix else None
        )
        logger.debug(
            "認可コードを交換します: domain_url=%s redirect_uri=%s prefix=%s 保存先=%s",
            domain_url,
            redirect_uri,
            prefix or "（なし）",
            "指定のコールバック" if on_refresh_token else ("DPAPI" if prefix else "保存しない"),
        )
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
        logger.debug("認可コードの交換に成功し refresh_token を受け取りました")
        if resolved_callback is not None:
            resolved_callback(refresh_token)
        return cls(
            client_id,
            refresh_token,
            domain_url,
            client_secret=client_secret,
            on_refresh_token=resolved_callback,
        )


def _post_token(
    domain_url: str,
    data: dict[str, str],
    *,
    secrets_to_redact: tuple[str, ...],
) -> dict:
    url = f"{domain_url}{TOKEN_PATH}"
    # リクエストの中身（client_secret・code・refresh_token）は秘密なので、
    # ログに残すのは宛先 URL と grant_type、結果のステータスコードだけにする。
    logger.debug(
        "トークンエンドポイントへ POST します: url=%s grant_type=%s", url, data["grant_type"]
    )
    try:
        response = requests.post(url, data=data, timeout=TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as e:
        logger.debug("トークンエンドポイントへ接続できませんでした: url=%s", url)
        raise SalesforceConnectionError(url, e) from e
    logger.debug("トークンエンドポイントの応答: status=%d", response.status_code)
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


__all__ = ["RefreshTokenOAuth"]
