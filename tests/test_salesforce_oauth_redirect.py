"""OAuthリダイレクトURLの解析（oauth_redirect.py）のテスト。"""

import pytest

from comken.exceptions import SalesforceAuthError
from comken.toolbox.salesforce.auth.oauth_redirect import parse_redirect_url

_CALLBACK_URL = "http://localhost:8080/callback"


class TestParseRedirectUrl:
    def test_extracts_code_and_state(self):
        result = parse_redirect_url(f"{_CALLBACK_URL}?code=CODE123&state=STATE123")
        assert result.code == "CODE123"
        assert result.state == "STATE123"

    def test_missing_code_raises(self):
        with pytest.raises(SalesforceAuthError):
            parse_redirect_url(f"{_CALLBACK_URL}?state=STATE123")

    def test_error_response_is_included_in_message(self):
        with pytest.raises(SalesforceAuthError) as exc_info:
            parse_redirect_url(f"{_CALLBACK_URL}?error=access_denied&error_description=Denied")
        assert "Denied" in str(exc_info.value)
