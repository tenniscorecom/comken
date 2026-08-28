"""Salesforce の差し替え可能な OAuth 認証方式。"""

import urllib.parse
from unittest.mock import MagicMock, patch

import pytest

from comken.exceptions import SalesforceAuthError
from comken.toolbox.salesforce import (
    ClientCredentialsAuth,
    RefreshTokenAuth,
    SalesforceBase,
)

DOMAIN_URL = "https://example.my.salesforce.com"
INSTANCE_URL = "https://instance.my.salesforce.com"

# 認証は必ずここを通るので、差し替え先はこの1本だけ。毎回フルパスを書くと
# 行が長くなるうえ、モジュールを移したときの直し漏れが起きやすい
_REQUESTS_POST = "comken.toolbox.salesforce.oauth_refresh.requests.post"


class _TestSalesforce(SalesforceBase):
    """認証方式の差し替えを検証するための組織クラス。"""

    OWNER = "test_salesforce_auth / テスト"


def _response(body: dict, status_code: int = 200) -> MagicMock:
    response = MagicMock(status_code=status_code, text="")
    response.json.return_value = body
    return response


class TestRefreshTokenAuth:
    def test_authorization_url_contains_required_values_and_state(self):
        url, state = RefreshTokenAuth.authorization_url(
            "CID", "https://localhost/callback", DOMAIN_URL, state="STATE"
        )
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        assert state == "STATE"
        assert query == {
            "response_type": ["code"],
            "client_id": ["CID"],
            "redirect_uri": ["https://localhost/callback"],
            "scope": ["api refresh_token"],
            "state": ["STATE"],
        }

    def test_exchange_code_returns_auth_and_reports_initial_refresh_token(self):
        saved_tokens: list[str] = []
        response = _response(
            {"access_token": "ACCESS", "instance_url": INSTANCE_URL, "refresh_token": "REFRESH"}
        )
        with patch(_REQUESTS_POST, return_value=response):
            auth = RefreshTokenAuth.exchange_code(
                "CID",
                "SECRET",
                "CODE",
                "https://localhost/callback",
                DOMAIN_URL,
                on_refresh_token=saved_tokens.append,
            )
        assert isinstance(auth, RefreshTokenAuth)
        assert saved_tokens == ["REFRESH"]

    def test_refresh_omits_optional_secret_and_saves_rotated_token(self):
        saved_tokens: list[str] = []
        response = _response(
            {"access_token": "ACCESS", "instance_url": INSTANCE_URL, "refresh_token": "ROTATED"}
        )
        with patch(_REQUESTS_POST, return_value=response) as post:
            result = RefreshTokenAuth(
                "CID", "REFRESH", DOMAIN_URL, on_refresh_token=saved_tokens.append
            ).fetch()
        assert result == ("ACCESS", INSTANCE_URL)
        assert "client_secret" not in post.call_args.kwargs["data"]
        assert saved_tokens == ["ROTATED"]

    def test_refresh_sends_secret_when_required(self):
        response = _response({"access_token": "ACCESS", "instance_url": INSTANCE_URL})
        with patch(_REQUESTS_POST, return_value=response) as post:
            RefreshTokenAuth(
                "CID",
                "REFRESH",
                DOMAIN_URL,
                client_secret="SECRET",
            ).fetch()
        assert post.call_args.kwargs["data"]["client_secret"] == "SECRET"

    def test_auth_error_redacts_refresh_token(self):
        response = MagicMock(status_code=400, text="invalid REFRESH")
        with (
            patch(_REQUESTS_POST, return_value=response),
            pytest.raises(SalesforceAuthError) as raised,
        ):
            RefreshTokenAuth("CID", "REFRESH", DOMAIN_URL).fetch()
        assert "REFRESH" not in str(raised.value)

    def test_exchange_code_with_prefix_saves_to_dpapi_without_explicit_callback(self):
        """prefix だけ渡せば、書き戻し用の関数を呼び出し側で書かなくても DPAPI へ保存される。"""
        response = _response(
            {"access_token": "ACCESS", "instance_url": INSTANCE_URL, "refresh_token": "REFRESH"}
        )
        with (
            patch(_REQUESTS_POST, return_value=response),
            patch("comken.toolbox.credentials.save_credential") as save_credential,
        ):
            RefreshTokenAuth.exchange_code(
                "CID",
                "SECRET",
                "CODE",
                "https://localhost/callback",
                DOMAIN_URL,
                prefix="site_a",
            )
        save_credential.assert_called_once_with("site_a_refresh_token", "REFRESH")

    def test_exchange_code_explicit_callback_overrides_prefix(self):
        """on_refresh_token を明示的に渡したときは prefix の既定より優先されることを確認する。"""
        saved_tokens: list[str] = []
        response = _response(
            {"access_token": "ACCESS", "instance_url": INSTANCE_URL, "refresh_token": "REFRESH"}
        )
        with (
            patch(_REQUESTS_POST, return_value=response),
            patch("comken.toolbox.credentials.save_credential") as save_credential,
        ):
            RefreshTokenAuth.exchange_code(
                "CID",
                "SECRET",
                "CODE",
                "https://localhost/callback",
                DOMAIN_URL,
                prefix="site_a",
                on_refresh_token=saved_tokens.append,
            )
        assert saved_tokens == ["REFRESH"]
        save_credential.assert_not_called()

    def test_from_credentials_saves_rotated_token_to_same_prefix(self):
        credentials = MagicMock(client_id="CID", client_secret="SECRET", refresh_token="REFRESH")
        with (
            patch("comken.toolbox.credentials.Credentials", return_value=credentials),
            patch("comken.toolbox.credentials.save_credential") as save_credential,
        ):
            auth = RefreshTokenAuth.from_credentials(DOMAIN_URL, "site_a")
            auth._on_refresh_token("ROTATED")
        save_credential.assert_called_once_with("site_a_refresh_token", "ROTATED")


class TestClientCredentialsAuth:
    def test_from_credentials_reads_same_prefix(self):
        credentials = MagicMock(client_id="CID", client_secret="SECRET")
        with patch("comken.toolbox.credentials.Credentials", return_value=credentials) as load:
            auth = ClientCredentialsAuth.from_credentials(DOMAIN_URL, "site_a")
        load.assert_called_once_with("site_a")
        assert auth._client_id == "CID"
        assert auth._client_secret == "SECRET"


class TestPluggableSalesforceAuth:
    def test_client_uses_supplied_auth_for_initial_and_401_authentication(self):
        auth = MagicMock()
        auth.fetch.side_effect = [("FIRST", INSTANCE_URL), ("SECOND", INSTANCE_URL)]
        session = MagicMock()
        session.headers = {}
        unauthorized = MagicMock(status_code=401, text="unauthorized", headers={})
        success = MagicMock(status_code=200, text='{"done": true, "records": []}')
        success.headers = {"Content-Type": "application/json"}
        success.json.return_value = {"done": True, "records": []}
        session.request.side_effect = [unauthorized, success]
        with (
            patch("comken.toolbox.salesforce.client.requests.Session", return_value=session),
            _TestSalesforce(auth=auth) as client,
        ):
            assert client.query("SELECT Id FROM Account") == []
        assert auth.fetch.call_count == 2


class TestAuthClassIsBuiltFromCredentials:
    """auth に「クラス」を渡したら DPAPI から組み立てる。

    利用側に ClientCredentialsAuth(cid, secret, url) と値を並べさせないため。
    既定（auth 省略）と同じ経路を通る。
    """

    def test_passing_a_class_reads_dpapi_with_the_class_prefix(self, monkeypatch):
        """Sandbox(auth=ClientCredentialsAuth) が CREDENTIAL_PREFIX で DPAPI を引く。"""
        called = {}

        class _FakeAuth:
            @classmethod
            def from_credentials(cls, domain_url, prefix):
                called["domain_url"] = domain_url
                called["prefix"] = prefix
                return cls()

            def fetch(self):
                return "TOKEN", DOMAIN_URL

        with patch("comken.toolbox.salesforce.client.requests.Session"):
            SalesforceBase(
                auth=_FakeAuth, domain_url=DOMAIN_URL, prefix="sandbox", org_name="sandbox"
            )

        assert called == {"domain_url": DOMAIN_URL, "prefix": "sandbox"}

    def test_passing_an_instance_is_used_as_is(self, monkeypatch):
        """作成済みインスタンスはそのまま使う（prefix / domain_url を見ない）。"""

        class _FakeAuth:
            @classmethod
            def from_credentials(cls, domain_url, prefix):  # 呼ばれたら失敗
                raise AssertionError("インスタンスを渡したら from_credentials は呼ばない")

            def fetch(self):
                return "TOKEN", DOMAIN_URL

        with patch("comken.toolbox.salesforce.client.requests.Session"):
            sf = SalesforceBase(auth=_FakeAuth(), org_name="sandbox")

        assert isinstance(sf.auth, _FakeAuth)
