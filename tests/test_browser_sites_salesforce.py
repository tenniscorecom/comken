"""salesforce ブラウザサイト雛形のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線だけを確認する
（tests/test_browser_sites_ntt.py と同じ方針）。
"""

from unittest.mock import MagicMock, patch

import pytest

from comken.exceptions import SalesforceReportExportError, SiteNotStartedError
from comken.toolbox.browser import BrowserOptions, DownloadDir
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites import SITES
from comken.toolbox.browser.sites.salesforce.site import (
    Salesforce,
    _build_export_url,
    _cookies_to_requests_session,
    _domain_of,
    _rename_to_report_id,
)

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
    session._site = Salesforce()
    return session


class TestPublicApi:
    """URLがダミーのままなので、SITES（公認一覧）には登録しない。"""

    def test_not_registered_in_sites(self):
        assert Salesforce.NAME
        assert Salesforce.BASE_URL
        assert Salesforce.OWNER == "comken"
        assert Salesforce not in SITES


# report_id_from_url() 自体のテストは tests/test_salesforce.py に集約してある
# （comken.toolbox.salesforce.report をそのまま使っているだけなので、ここでは複製しない）。


class TestBuildExportUrl:
    """_build_export_url() — 今のタブのドメインからエクスポートURLを組み立てる。"""

    def test_builds_csv_export_url_from_current_domain(self):
        url = _build_export_url(REPORT_URL_1, "00O5g00000ABCDE1AS", "csv")

        assert url == (
            "https://example.my.salesforce.com/00O5g00000ABCDE1AS"
            "?isdtp=p1&export=1&enc=UTF-8&xf=csv"
        )

    def test_uses_given_export_format(self):
        url = _build_export_url(REPORT_URL_1, "00O5g00000ABCDE1AS", "xls")

        assert url.endswith("xf=xls")


class TestRenameToReportId:
    """_rename_to_report_id() — ダウンロードした最新ファイルをreport_idベースの名前へ変える。"""

    def test_renames_latest_file(self, tmp_path):
        original = tmp_path / "月次レポート.csv"
        original.touch()

        renamed = _rename_to_report_id([original], tmp_path, "00O5g00000ABCDE1AS", "csv")

        assert renamed == tmp_path / "00O5g00000ABCDE1AS.csv"
        assert renamed.exists()
        assert not original.exists()

    def test_overwrites_existing_target(self, tmp_path):
        target = tmp_path / "00O5g00000ABCDE1AS.csv"
        target.write_text("old")
        original = tmp_path / "月次レポート.csv"
        original.write_text("new")

        renamed = _rename_to_report_id([original], tmp_path, "00O5g00000ABCDE1AS", "csv")

        assert renamed.read_text() == "new"


class TestLoginWithToken:
    """login_with_token() — frontdoor.jsp でブラウザのログイン状態を確立する。"""

    def test_opens_frontdoor_jsp_with_token(self, tmp_path):
        session = _make_session(tmp_path)
        sf = Salesforce(session)

        sf.login_with_token("MY_TOKEN", instance_url="https://org.my.salesforce.com")

        session._driver.get.assert_called_once_with(
            "https://org.my.salesforce.com/secur/frontdoor.jsp?sid=MY_TOKEN"
        )

    def test_falls_back_to_base_url_when_instance_url_omitted(self, tmp_path):
        session = _make_session(tmp_path)
        sf = Salesforce(session)

        sf.login_with_token("MY_TOKEN")

        session._driver.get.assert_called_once_with(
            f"{Salesforce.BASE_URL}/secur/frontdoor.jsp?sid=MY_TOKEN"
        )

    def test_raises_when_not_started(self):
        sf = Salesforce()

        with pytest.raises(SiteNotStartedError):
            sf.login_with_token("MY_TOKEN")


class TestDownloadReports:
    """download_reports() — 読み込みが終わったレポートから順にダウンロードしてリネームする。"""

    def test_downloads_and_renames_each_report_without_mixing_files(self, tmp_path):
        """2件目のダウンロード判定に、1件目のリネーム後ファイルが紛れ込まないことを確認する。

        DownloadDir.wait() を複数回呼ぶと、mark_known() を呼ばない限り前回リネームした
        ファイルを再検出してしまう回帰（tests/test_utils.py で個別に確認済み）を、
        Salesforce.download_reports() 側で正しく防げているかを確かめる。
        """
        session = _make_session(tmp_path)
        session.load_many = MagicMock(return_value=iter([REPORT_URL_1, REPORT_URL_2]))
        session._driver.current_url = REPORT_URL_1
        sf = Salesforce(session)

        # 1件目はここで既にダウンロード済みという想定(session.open は素通しのモック)
        (session.download_dir.path / "レポートA.csv").touch()

        results = sf.download_reports([REPORT_URL_1, REPORT_URL_2], ready=None, download_timeout=1)

        first_id, first_path = next(results)
        assert first_id == "00O5g00000ABCDE1AS"
        assert first_path == session.download_dir.path / "00O5g00000ABCDE1AS.csv"

        # 2件目のタブに切り替わった想定で current_url を変え、ファイルもここで初めて作る
        session._driver.current_url = REPORT_URL_2
        (session.download_dir.path / "レポートB.csv").touch()

        second_id, second_path = next(results)
        assert second_id == "00O5g00000ABCDE2AS"
        assert second_path == session.download_dir.path / "00O5g00000ABCDE2AS.csv"

        with pytest.raises(StopIteration):
            next(results)

        session.load_many.assert_called_once_with(
            [REPORT_URL_1, REPORT_URL_2], ready=None, max_open=10, timeout=None
        )


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

    def test_downloads_all_reports_and_yields_report_id_and_path(self, tmp_path):
        session = _make_session(tmp_path)
        session._driver.current_url = REPORT_URL_1
        session._driver.get_cookies.return_value = [
            {"name": "sid", "value": "TOKEN", "domain": ".salesforce.com"}
        ]
        sf = Salesforce(session)

        http_session = MagicMock()
        http_session.get.side_effect = [
            _csv_response(b"report1"),
            _csv_response(b"report2"),
        ]
        with patch(
            "comken.toolbox.browser.sites.salesforce.site.requests.Session",
            return_value=http_session,
        ):
            results = dict(sf.export_reports([REPORT_URL_1, REPORT_URL_2], tmp_path))

        assert set(results) == {"00O5g00000ABCDE1AS", "00O5g00000ABCDE2AS"}
        for report_id, path in results.items():
            assert path == tmp_path / f"{report_id}.csv"
            assert path.exists()

    def test_creates_target_directory(self, tmp_path):
        session = _make_session(tmp_path)
        session._driver.current_url = REPORT_URL_1
        session._driver.get_cookies.return_value = []
        sf = Salesforce(session)

        http_session = MagicMock()
        http_session.get.return_value = _csv_response()
        target = tmp_path / "nested" / "dir"
        with patch(
            "comken.toolbox.browser.sites.salesforce.site.requests.Session",
            return_value=http_session,
        ):
            list(sf.export_reports([REPORT_URL_1], target))

        assert target.is_dir()

    def test_raises_when_response_is_html(self, tmp_path):
        session = _make_session(tmp_path)
        session._driver.current_url = REPORT_URL_1
        session._driver.get_cookies.return_value = []
        sf = Salesforce(session)

        http_session = MagicMock()
        http_session.get.return_value = _html_response()
        with (
            patch(
                "comken.toolbox.browser.sites.salesforce.site.requests.Session",
                return_value=http_session,
            ),
            pytest.raises(SalesforceReportExportError),
        ):
            list(sf.export_reports([REPORT_URL_1], tmp_path))

    def test_raises_when_not_started(self):
        sf = Salesforce()

        with pytest.raises(SiteNotStartedError):
            list(sf.export_reports([REPORT_URL_1], "出力先"))
