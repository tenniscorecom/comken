"""salesforce ブラウザサイト雛形のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線だけを確認する
（tests/test_browser_sites_ntt.py と同じ方針）。
"""

from unittest.mock import MagicMock

import pytest

from comken.exceptions import SalesforceReportIDNotFoundError, SiteNotStartedError
from comken.toolbox.browser import BrowserOptions, DownloadDir
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites import SITES
from comken.toolbox.browser.sites.salesforce.site import (
    Salesforce,
    _build_export_url,
    _rename_to_report_id,
    _report_id_from_url,
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


class TestReportIdFromUrl:
    """_report_id_from_url() — レポートURLからIDを取り出す。"""

    def test_extracts_id_from_lightning_url(self):
        assert _report_id_from_url(REPORT_URL_1) == "00O5g00000ABCDE1AS"

    def test_accepts_bare_report_id(self):
        assert _report_id_from_url("00O5g00000ABCDE1AS") == "00O5g00000ABCDE1AS"

    def test_raises_when_id_not_found(self):
        with pytest.raises(SalesforceReportIDNotFoundError):
            _report_id_from_url("https://example.my.salesforce.com/not-a-report")


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
