"""Salesforce の差し替え可能な OAuth 認証方式。"""

from __future__ import annotations

import urllib.parse
from unittest.mock import MagicMock, patch

import pytest

from comken.exceptions import SalesforceAuthError
from comken.salesforce import CredentialsOAuth, RefreshOAuth, Salesforce

DOMAIN_URL = "https://example.my.salesforce.com"
INSTANCE_URL = "https://instance.my.salesforce.com"


def _response(body: dict, status_code: int = 200) -> MagicMock:
    response = MagicMock(status_code=status_code, text="")
    response.json.return_value = body
    return response


class TestRefreshOAuth:
    def test_authorization_url_contains_required_values_and_state(self):
        url, state = RefreshOAuth.authorization_url(
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
        with patch("comken.salesforce.oauth_refresh.requests.post", return_value=response):
            auth = RefreshOAuth.exchange_code(
                "CID",
                "SECRET",
                "CODE",
                "https://localhost/callback",
                DOMAIN_URL,
                on_refresh_token=saved_tokens.append,
            )
        assert isinstance(auth, RefreshOAuth)
        assert saved_tokens == ["REFRESH"]

    def test_refresh_omits_optional_secret_and_saves_rotated_token(self):
        saved_tokens: list[str] = []
        response = _response(
            {"access_token": "ACCESS", "instance_url": INSTANCE_URL, "refresh_token": "ROTATED"}
        )
        with patch("comken.salesforce.oauth_refresh.requests.post", return_value=response) as post:
            result = RefreshOAuth(
                "CID", "REFRESH", DOMAIN_URL, on_refresh_token=saved_tokens.append
            ).fetch()
        assert result == ("ACCESS", INSTANCE_URL)
        assert "client_secret" not in post.call_args.kwargs["data"]
        assert saved_tokens == ["ROTATED"]

    def test_refresh_sends_secret_when_required(self):
        response = _response({"access_token": "ACCESS", "instance_url": INSTANCE_URL})
        with patch("comken.salesforce.oauth_refresh.requests.post", return_value=response) as post:
            RefreshOAuth(
                "CID",
                "REFRESH",
                DOMAIN_URL,
                client_secret="SECRET",
            ).fetch()
        assert post.call_args.kwargs["data"]["client_secret"] == "SECRET"

    def test_auth_error_redacts_refresh_token(self):
        response = MagicMock(status_code=400, text="invalid REFRESH")
        with (
            patch("comken.salesforce.oauth_refresh.requests.post", return_value=response),
            pytest.raises(SalesforceAuthError) as raised,
        ):
            RefreshOAuth("CID", "REFRESH", DOMAIN_URL).fetch()
        assert "REFRESH" not in str(raised.value)

    def test_from_credentials_saves_rotated_token_to_same_prefix(self):
        credentials = MagicMock(client_id="CID", client_secret="SECRET", refresh_token="REFRESH")
        with (
            patch("comken.credentials.Credentials", return_value=credentials),
            patch("comken.credentials.save_credential") as save_credential,
        ):
            auth = RefreshOAuth.from_credentials(DOMAIN_URL, "site_a")
            auth._on_refresh_token("ROTATED")
        save_credential.assert_called_once_with("site_a_refresh_token", "ROTATED")


class TestCredentialsOAuth:
    def test_from_credentials_reads_same_prefix(self):
        credentials = MagicMock(client_id="CID", client_secret="SECRET")
        with patch("comken.credentials.Credentials", return_value=credentials) as load:
            auth = CredentialsOAuth.from_credentials(DOMAIN_URL, "site_a")
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
            patch("comken.salesforce.client.requests.Session", return_value=session),
            Salesforce(auth=auth) as client,
        ):
            assert client.query("SELECT Id FROM Account") == []
        assert auth.fetch.call_count == 2
