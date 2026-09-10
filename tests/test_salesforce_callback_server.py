"""OAuthリダイレクトを自動で受け取るローカルサーバー（callback_server.py）のテスト。

wait_for_callback() は実際にソケットをbindしてブロッキングで待ち受けるため、
「ブラウザからのリダイレクト」役を別スレッドで発火させて確かめる。
timeout系のテストはすぐ失敗するよう、短い timeout_seconds を使う。
"""

import contextlib
import threading
import time
import urllib.error
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
_STATE = "STATE123"


def _fire_request(url: str, delay: float = 0.05) -> None:
    """別スレッドから、ブラウザが送るGETを模して発火させる。

    無関係なリクエスト（favicon.ico・state不一致等）はサーバー側が404を返す
    想定のテストでも使うため、HTTPErrorは黙って無視する。タイムアウト系の
    テストではサーバーが先に閉じて接続拒否（URLError）になることもあるので
    それも無視する（テストの主眼は wait_for_callback() 側の挙動で、
    この発火スレッドの応答は見ない）。
    """

    def _request() -> None:
        time.sleep(delay)
        with contextlib.suppress(urllib.error.HTTPError, urllib.error.URLError):
            urllib.request.urlopen(url, timeout=5)

    threading.Thread(target=_request, daemon=True).start()


def _fire_redirect(query: str, delay: float = 0.05) -> None:
    """別スレッドから、callbackパスへのリダイレクトを模したGETを送る。"""
    _fire_request(f"{_CALLBACK_URL}?{query}", delay)


class TestIsLocalhostCallback:
    def test_localhost_is_true(self):
        assert is_localhost_callback("http://localhost:8080/callback") is True

    def test_loopback_ip_is_true(self):
        assert is_localhost_callback("http://127.0.0.1:8080/callback") is True

    def test_other_host_is_false(self):
        assert is_localhost_callback("https://example.com/callback") is False


class TestParseRedirectUrl:
    def test_extracts_code_and_state(self):
        result = parse_redirect_url(f"{_CALLBACK_URL}?code=CODE123&state={_STATE}")
        assert result.code == "CODE123"
        assert result.state == _STATE

    def test_missing_code_raises(self):
        with pytest.raises(SalesforceAuthError):
            parse_redirect_url(f"{_CALLBACK_URL}?state={_STATE}")

    def test_error_response_is_included_in_message(self):
        with pytest.raises(SalesforceAuthError) as exc_info:
            parse_redirect_url(f"{_CALLBACK_URL}?error=access_denied&error_description=Denied")
        assert "Denied" in str(exc_info.value)


class TestWaitForCallback:
    def test_receives_code_and_state(self):
        _fire_redirect(f"code=CODE123&state={_STATE}")
        result = wait_for_callback(_CALLBACK_URL, _STATE, timeout_seconds=5)
        assert result.code == "CODE123"
        assert result.state == _STATE

    def test_raises_on_denied_authorization(self):
        _fire_redirect("error=access_denied&error_description=User+denied")
        with pytest.raises(SalesforceAuthError):
            wait_for_callback(_CALLBACK_URL, _STATE, timeout_seconds=5)

    def test_times_out_when_nothing_arrives(self):
        with pytest.raises(TimeoutError):
            wait_for_callback(_CALLBACK_URL, _STATE, timeout_seconds=0.2)

    def test_reusable_across_sequential_calls(self):
        """1件受け取ったら閉じるので、次の呼び出しで同じポートを再利用できる。"""
        _fire_redirect(f"code=FIRST&state={_STATE}")
        wait_for_callback(_CALLBACK_URL, _STATE, timeout_seconds=5)

        _fire_redirect(f"code=SECOND&state={_STATE}")
        result = wait_for_callback(_CALLBACK_URL, _STATE, timeout_seconds=5)
        assert result.code == "SECOND"

    def test_ignores_unrelated_path_and_still_receives_the_real_redirect(self):
        """favicon.ico 等の無関係なリクエストに横取りされず、本物のリダイレクトを受け取る。"""
        _fire_request(f"http://localhost:{_TEST_PORT}/favicon.ico", delay=0.02)
        _fire_redirect(f"code=REAL&state={_STATE}", delay=0.1)

        result = wait_for_callback(_CALLBACK_URL, _STATE, timeout_seconds=5)

        assert result.code == "REAL"

    def test_ignores_state_mismatch_and_still_receives_the_real_redirect(self):
        """stateが一致しないcode=リクエスト（横取り・混線）に横取りされない。"""
        _fire_redirect("code=WRONG&state=WRONG-STATE", delay=0.02)
        _fire_redirect(f"code=REAL&state={_STATE}", delay=0.1)

        result = wait_for_callback(_CALLBACK_URL, _STATE, timeout_seconds=5)

        assert result.code == "REAL"

    def test_times_out_when_only_noise_arrives(self):
        """一致するリクエストが最後まで来なければ、ノイズだけではタイムアウトする。"""
        _fire_request(f"http://localhost:{_TEST_PORT}/favicon.ico", delay=0.02)
        _fire_redirect("code=WRONG&state=WRONG-STATE", delay=0.05)

        with pytest.raises(TimeoutError):
            wait_for_callback(_CALLBACK_URL, _STATE, timeout_seconds=0.5)
