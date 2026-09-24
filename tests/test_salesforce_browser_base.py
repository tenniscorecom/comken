"""comken.toolbox.browser.sites.salesforce.base のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線だけを確認する
（tests/test_browser_sites_ntt.py と同じ方針）。
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from comken.exceptions import SalesforceReportExportError, SiteNotStartedError
from comken.toolbox.browser import BrowserOptions, DownloadDir
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites.salesforce.base import (
    SalesforceSiteBase,
    _cookies_to_requests_session,
    _domain_of,
    _start_keep_alive,
)
from comken.toolbox.browser.sites.salesforce.pages.login_page import LoginPage

REPORT_URL_1 = "https://example.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE1AS/view"
REPORT_URL_2 = "https://example.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE2AS/view"


def _make_session(tmp_path, name: str = "test") -> BrowserSession:
    """Edge を起動せずに、Salesforce に紐づいた起動済みセッションを作る。"""
    session = BrowserSession(
        name=name,
        options=BrowserOptions(),
        download_dir=DownloadDir(path=tmp_path / f"dl_{name}"),
        profile_dir=None,
    )
    session._driver = MagicMock()
    session._site = SalesforceSiteBase()
    return session


class TestPublicApi:
    """URLがダミーのままの雛形。組織別クラスは comken.toolbox.browser.sites.salesforce にある。"""

    def test_class_attributes(self):
        assert SalesforceSiteBase.NAME
        assert SalesforceSiteBase.BASE_URL
        assert SalesforceSiteBase.OWNER == "comken"


# report_id_from_url() 自体のテストは tests/test_salesforce.py に集約してある
# （comken.toolbox.salesforce.report をそのまま使っているだけなので、ここでは複製しない）。


class TestGoLogin:
    """go_login() — 人が手動でログインする画面を開く。"""

    def test_opens_base_url(self, tmp_path):
        session = _make_session(tmp_path)
        sf = SalesforceSiteBase(session)

        sf.go_login()

        session._driver.get.assert_called_once_with(SalesforceSiteBase.BASE_URL)

    def test_raises_when_not_started(self):
        sf = SalesforceSiteBase()

        with pytest.raises(SiteNotStartedError):
            sf.go_login()


class TestWaitForManualLogin:
    """wait_for_manual_login() — 人がブラウザでログインを終えるのをEnter待ちする。"""

    def test_waits_for_enter_key(self, monkeypatch):
        calls = []
        monkeypatch.setattr("builtins.input", lambda prompt="": calls.append(prompt))

        SalesforceSiteBase().wait_for_manual_login()

        assert len(calls) == 1


class TestLoginPageLogin:
    """LoginPage.login() — ID/パスワードを入力してログインボタンを押す。"""

    def test_fills_username_and_password_and_clicks_login(self, tmp_path):
        session = _make_session(tmp_path)
        page = LoginPage(session)
        page._wait = MagicMock()
        element = MagicMock()
        page._wait.until.return_value = element

        page.login("user@example.com", "secret")

        element.send_keys.assert_any_call("user@example.com")
        element.send_keys.assert_any_call("secret")
        element.click.assert_called_once()


class TestLoginWithCredentials:
    """login_with_credentials() — DPAPIのID/パスワードでログインフォームへ入力する。"""

    def test_uses_credentials_to_login(self, tmp_path):
        session = _make_session(tmp_path)
        sf = SalesforceSiteBase(session)
        cred = MagicMock(username="user@example.com", password="secret")
        login_page = MagicMock()
        with (
            patch("comken.toolbox.credentials.Credentials", return_value=cred) as cred_class,
            patch.object(SalesforceSiteBase, "go_login", return_value=login_page) as go_login,
        ):
            sf.login_with_credentials("salesforce_temp")

        cred_class.assert_called_once_with("salesforce_temp")
        go_login.assert_called_once()
        login_page.login.assert_called_once_with("user@example.com", "secret")

    def test_falls_back_to_class_credential_prefix_when_omitted(self, tmp_path):
        """prefix省略時は、クラスの CREDENTIAL_PREFIX を使う。"""

        class _MyOrg(SalesforceSiteBase):
            CREDENTIAL_PREFIX = "salesforce_solution"

        session = _make_session(tmp_path)
        session._site = _MyOrg()
        sf = _MyOrg(session)
        cred = MagicMock(username="user@example.com", password="secret")
        with (
            patch("comken.toolbox.credentials.Credentials", return_value=cred) as cred_class,
            patch.object(SalesforceSiteBase, "go_login", return_value=MagicMock()),
        ):
            sf.login_with_credentials()

        cred_class.assert_called_once_with("salesforce_solution")

    def test_explicit_prefix_overrides_class_credential_prefix(self, tmp_path):
        """明示的に渡した prefix は、クラスの CREDENTIAL_PREFIX より優先される。"""

        class _MyOrg(SalesforceSiteBase):
            CREDENTIAL_PREFIX = "salesforce_solution"

        session = _make_session(tmp_path)
        session._site = _MyOrg()
        sf = _MyOrg(session)
        cred = MagicMock(username="user@example.com", password="secret")
        with (
            patch("comken.toolbox.credentials.Credentials", return_value=cred) as cred_class,
            patch.object(SalesforceSiteBase, "go_login", return_value=MagicMock()),
        ):
            sf.login_with_credentials("salesforce_temp")

        cred_class.assert_called_once_with("salesforce_temp")


class TestDomainOf:
    """_domain_of() — URLから scheme + netloc だけを取り出す。"""

    def test_extracts_scheme_and_netloc(self):
        assert _domain_of(REPORT_URL_1) == "https://example.my.salesforce.com"


class TestCookiesToRequestsSession:
    """_cookies_to_requests_session() — Seleniumのcookieをrequests.Sessionへ移す。"""

    def test_copies_all_cookies(self):
        driver_cookies = [
            {"name": "sid", "value": "ABC123", "domain": ".salesforce.com"},
            {"name": "other", "value": "XYZ", "domain": ".salesforce.com"},
        ]

        http_session = _cookies_to_requests_session(driver_cookies)

        cookie_dict = http_session.cookies.get_dict()
        assert cookie_dict == {"sid": "ABC123", "other": "XYZ"}

    def test_handles_empty_cookie_list(self):
        http_session = _cookies_to_requests_session([])

        assert http_session.cookies.get_dict() == {}


def _csv_response(body: bytes = b"col1,col2\n1,2\n"):
    response = MagicMock()
    response.status_code = 200
    response.headers = {
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=report.csv",
    }
    response.content = body
    return response


def _html_response(status: int = 200):
    response = MagicMock()
    response.status_code = status
    response.headers = {"Content-Type": "text/html; charset=UTF-8"}
    response.content = b"<html>login</html>"
    return response


class TestExportReports:
    """export_reports() — セッションCookieをrequestsへ引き継ぎ並列ダウンロードする。"""

    def test_downloads_reports_to_the_given_destinations(self, tmp_path):
        session = _make_session(tmp_path)
        session._driver.current_url = REPORT_URL_1
        session._driver.get_cookies.return_value = [
            {"name": "sid", "value": "TOKEN", "domain": ".salesforce.com"}
        ]
        sf = SalesforceSiteBase(session)

        http_session = MagicMock()
        http_session.get.side_effect = [
            _csv_response(b"report1"),
            _csv_response(b"report2"),
        ]
        destination_1 = tmp_path / "月次レポート.csv"
        destination_2 = tmp_path / "サブフォルダ" / "四半期レポート.csv"
        with patch(
            "comken.toolbox.browser.sites.salesforce.base.requests.Session",
            return_value=http_session,
        ):
            results = dict(
                sf.export_reports({REPORT_URL_1: destination_1, REPORT_URL_2: destination_2})
            )

        assert set(results) == {"00O5g00000ABCDE1AS", "00O5g00000ABCDE2AS"}
        assert results["00O5g00000ABCDE1AS"] == destination_1
        assert results["00O5g00000ABCDE2AS"] == destination_2
        assert destination_1.exists()
        assert destination_2.exists()

    def test_creates_parent_directory_of_destination(self, tmp_path):
        session = _make_session(tmp_path)
        session._driver.current_url = REPORT_URL_1
        session._driver.get_cookies.return_value = []
        sf = SalesforceSiteBase(session)

        http_session = MagicMock()
        http_session.get.return_value = _csv_response()
        destination = tmp_path / "nested" / "dir" / "report.csv"
        with patch(
            "comken.toolbox.browser.sites.salesforce.base.requests.Session",
            return_value=http_session,
        ):
            list(sf.export_reports({REPORT_URL_1: destination}))

        assert destination.exists()

    def test_raises_when_response_is_html(self, tmp_path):
        session = _make_session(tmp_path)
        session._driver.current_url = REPORT_URL_1
        session._driver.get_cookies.return_value = []
        sf = SalesforceSiteBase(session)

        http_session = MagicMock()
        http_session.get.return_value = _html_response()
        with (
            patch(
                "comken.toolbox.browser.sites.salesforce.base.requests.Session",
                return_value=http_session,
            ),
            pytest.raises(SalesforceReportExportError),
        ):
            list(sf.export_reports({REPORT_URL_1: tmp_path / "report.csv"}))

    def test_raises_when_not_started(self):
        sf = SalesforceSiteBase()

        with pytest.raises(SiteNotStartedError):
            list(sf.export_reports({REPORT_URL_1: "出力先/report.csv"}))


class TestStartKeepAlive:
    """_start_keep_alive() — export_reports() 中、ブラウザにURLを開かせ続ける暫定対処。"""

    def test_returns_none_thread_when_url_is_none(self, tmp_path):
        session = _make_session(tmp_path)

        thread, stop = _start_keep_alive(session, None, 300)

        assert thread is None
        assert not stop.is_set()

    def test_opens_url_repeatedly_until_stopped(self, tmp_path):
        session = _make_session(tmp_path)

        thread, stop = _start_keep_alive(session, REPORT_URL_1, 0.02)
        try:
            time.sleep(0.1)
        finally:
            stop.set()
            thread.join(timeout=1)

        assert not thread.is_alive()
        assert session._driver.get.call_count >= 2

    def test_survives_open_failure_and_keeps_running(self, tmp_path):
        session = _make_session(tmp_path)
        session._driver.get.side_effect = RuntimeError("開けませんでした")

        thread, stop = _start_keep_alive(session, REPORT_URL_1, 0.02)
        try:
            time.sleep(0.1)
        finally:
            stop.set()
            thread.join(timeout=1)

        assert not thread.is_alive()
        assert session._driver.get.call_count >= 2


class TestExportReportsKeepAlive:
    """export_reports() の keep_alive_report_id — ダウンロード終了後は必ず止まる。"""

    def test_keep_alive_thread_stops_after_completion(self, tmp_path):
        session = _make_session(tmp_path)
        session._driver.current_url = REPORT_URL_1
        session._driver.get_cookies.return_value = []
        sf = SalesforceSiteBase(session)

        http_session = MagicMock()
        http_session.get.return_value = _csv_response()
        with patch(
            "comken.toolbox.browser.sites.salesforce.base.requests.Session",
            return_value=http_session,
        ):
            list(
                sf.export_reports(
                    {REPORT_URL_1: tmp_path / "report.csv"},
                    keep_alive_report_id="00O5g00000ABCDE9AS",
                    keep_alive_interval=0.02,
                )
            )

        active_threads = [t for t in threading.enumerate() if t.name == "salesforce-keep-alive"]
        assert active_threads == []

    def test_keep_alive_url_is_built_from_current_domain(self, tmp_path):
        session = _make_session(tmp_path)
        session._driver.current_url = REPORT_URL_1
        session._driver.get_cookies.return_value = []
        sf = SalesforceSiteBase(session)

        def _slow_get(*args, **kwargs):
            time.sleep(0.1)
            return _csv_response()

        http_session = MagicMock()
        http_session.get.side_effect = _slow_get
        with patch(
            "comken.toolbox.browser.sites.salesforce.base.requests.Session",
            return_value=http_session,
        ):
            list(
                sf.export_reports(
                    {REPORT_URL_1: tmp_path / "report.csv"},
                    keep_alive_report_id="00O5g00000ABCDE9AS",
                    keep_alive_interval=0.02,
                )
            )

        session._driver.get.assert_any_call("https://example.my.salesforce.com/00O5g00000ABCDE9AS")
