"""
salesforce/oauth.py — アクセストークンの取得

OAuth 2.0 クライアントクレデンシャルフローでトークンを取る。
接続アプリの client_id / client_secret だけを使い、ユーザー名・パスワード・
セキュリティトークンは使わない。

このフローは**リフレッシュトークンを発行しない**（公式ドキュメントに
"This flow doesn't support refresh tokens." と明記がある）。そのため
「リフレッシュトークンをどこに保管し、いつ更新するか」という運用が発生しない。

アクセストークンの有効期限は固定値ではなく、接続アプリのセッションポリシー →
ユーザーのプロファイル → 組織のセッション設定、の順で決まる。つまり残り秒数を
コード側で計算する意味がないため、**期限を測らず 401 が返ったら取り直す**
（取り直しは Salesforce 側が行う。詳しくは docs/Salesforce設計メモ.md）。

将来 JWT ベアラーフローへ移る場合は、fetch() が同じ形（アクセストークンと
instance_url のタプル）を返すクラスを作って差し替える。
準備は docs/Salesforce_JWTと鍵配布.md にある。
"""

import logging

import requests

from ..exceptions import SalesforceAuthError, SalesforceConnectionError

logger = logging.getLogger(__name__)

TOKEN_PATH = "/services/oauth2/token"
GRANT_TYPE = "client_credentials"
TIMEOUT_SECONDS = 60


class ClientCredentialsAuth:
    """クライアントクレデンシャルフローでアクセストークンを取得する。

    使い方:
        auth = ClientCredentialsAuth(
            client_id="接続アプリの Consumer Key",
            client_secret="接続アプリの Consumer Secret",
            domain_url="https://your-domain.my.salesforce.com",
        )
        access_token, instance_url = auth.fetch()
    """

    def __init__(self, client_id: str, client_secret: str, domain_url: str) -> None:
        """
        Args:
            client_id: 接続アプリの Consumer Key。
            client_secret: 接続アプリの Consumer Secret。
            domain_url: 組織の My Domain の URL
                （例: "https://foo.my.salesforce.com"）。
                Sandbox は "https://foo--sandbox.sandbox.my.salesforce.com"。
                このフローは My Domain が必須で、login.salesforce.com では動かない。
        """
        self._client_id = client_id
        self._client_secret = client_secret
        self._domain_url = domain_url.rstrip("/")

    def fetch(self) -> tuple[str, str]:
        """アクセストークンと instance_url を取得して返す。

        期限切れのたびに呼び直してよい（毎回まっさらなトークンが返る）。

        Returns:
            (アクセストークン, instance_url) のタプル。

        Raises:
            SalesforceAuthError: 認証に失敗した場合。
            SalesforceConnectionError: ネットワークの問題で接続できない場合。
        """
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
            # NOTE: response.text には client_secret は含まれないが、
            #       値そのものをログに出さないよう例外メッセージにだけ載せる
            raise SalesforceAuthError(response.status_code, response.text)

        body = response.json()
        logger.debug("アクセストークンを取得しました: %s", body.get("instance_url"))
        return body["access_token"], body["instance_url"]
