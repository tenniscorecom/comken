"""OAuthリダイレクトを自動で受け取るローカルサーバー（callback_server.py）のテスト。

wait_for_callback() は実際にソケットをbindしてブロッキングで待ち受けるため、
「ブラウザからのリダイレクト」役を別スレッドで発火させて確かめる。
timeout系のテストはすぐ失敗するよう、短い timeout_seconds を使う。
"""

import threading
import time
import urllib.request

import pytest

from comken.exceptions import SalesforceAuthError
from comken.toolbox.salesforce.auth.callback_server import (
    is_localhost_callback,
    parse_redirect_url,
    wait_for_callback,
)

# 他のテストやプロセスと衝突しにくい、このテスト専用のポート。
_TEST_PORT = 18765
_CALLBACK_URL = f"http://localhost:{_TEST_PORT}/callback"


def _fire_redirect(query: str, delay: float = 0.05) -> None:
    """別スレッドから、ブラウザのリダイレクトを模したGETを送る。"""

    def _request() -> None:
        time.sleep(delay)
        urllib.request.urlopen(f"{_CALLBACK_URL}?{query}", timeout=5)

    threading.Thread(target=_request, daemon=True).start()


class TestIsLocalhostCallback:
    def test_localhost_is_true(self):
        assert is_localhost_callback("http://localhost:8080/callback") is True

    def test_loopback_ip_is_true(self):
        assert is_localhost_callback("http://127.0.0.1:8080/callback") is True

    def test_other_host_is_false(self):
        assert is_localhost_callback("https://example.com/callback") is False


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


class TestWaitForCallback:
    def test_receives_code_and_state(self):
        _fire_redirect("code=CODE123&state=STATE123")
        result = wait_for_callback(_CALLBACK_URL, timeout_seconds=5)
        assert result.code == "CODE123"
        assert result.state == "STATE123"

    def test_raises_on_denied_authorization(self):
        _fire_redirect("error=access_denied&error_description=User+denied")
        with pytest.raises(SalesforceAuthError):
            wait_for_callback(_CALLBACK_URL, timeout_seconds=5)

    def test_times_out_when_nothing_arrives(self):
        with pytest.raises(TimeoutError):
            wait_for_callback(_CALLBACK_URL, timeout_seconds=0.2)

    def test_stops_listening_after_one_request(self):
        """1件受け取ったら閉じるので、ポートは再利用できる（listenし続けない）。"""
        _fire_redirect("code=FIRST&state=S1")
        wait_for_callback(_CALLBACK_URL, timeout_seconds=5)

        _fire_redirect("code=SECOND&state=S2")
        result = wait_for_callback(_CALLBACK_URL, timeout_seconds=5)
        assert result.code == "SECOND"
