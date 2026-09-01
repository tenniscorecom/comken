"""SiteBase / SalesforceBase の OWNER 必須検査と起動時 INFO ログのテスト。

ライブラリ管理者が「同じ社内システムのクラスが複数プロジェクトで重複していないか」
把握できる仕組みを、`with SiteBase()` と `Browsers.launch()` の両方の経路、
および Salesforce の起動経路で確認する。

INFO ログは**起動が成功した後**にだけ出す。失敗したのに「使った」というログが
残ると記録が嘘になるので、失敗したらログが出ないことも確かめる。
"""

import contextlib
import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from comken.exceptions import (
    SiteAlreadyInLibraryError,
    SiteOwnerRequiredError,
)
from comken.toolbox.browser import Browsers, SiteBase
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.salesforce import ClientCredentialsOAuth
from comken.toolbox.salesforce.client import SalesforceBase

BROWSER_LOGGER = "comken.toolbox.browser.sitebase"
SALESFORCE_LOGGER = "comken.toolbox.salesforce.client"
DOMAIN_URL = "https://example.my.salesforce.com"
# 免除の確認に使う、comken 配下に見せかけるモジュール名
COMKEN_BROWSER_MODULE = "comken.toolbox.browser.sites.fake"
COMKEN_SALESFORCE_MODULE = "comken.toolbox.salesforce.sites.fake"


def _patch_browser_session(monkeypatch) -> None:
    """Edge を起動せずに SiteBase の起動経路を通せるようにする。"""
    monkeypatch.setattr(BrowserSession, "__enter__", lambda self: self)
    monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *args: None)


def _info_messages(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]


def _token_response():
    """認証のトークン応答の代わり。"""
    body = {"access_token": "TOKEN", "instance_url": DOMAIN_URL}
    response = MagicMock()
    response.status_code = 200
    response.headers = {"Content-Type": "application/json"}
    response.json.return_value = body
    response.text = json.dumps(body)
    return response


@contextlib.contextmanager
def _salesforce_http():
    """Salesforce の認証と HTTP セッションをモックする。"""
    session = MagicMock()
    session.headers = {}
    with (
        patch("comken.toolbox.salesforce.client.requests.Session", return_value=session),
        patch(
            "comken.toolbox.salesforce.oauth_credentials.requests.post",
            return_value=_token_response(),
        ),
    ):
        yield


class TestSiteBaseOwner:
    """SiteBase の OWNER 必須検査のテスト。"""

    def test_with_site_base_rejects_missing_owner(self, monkeypatch):
        """`with Kintai()` 経路で OWNER 未設定だと SiteOwnerRequiredError になる。"""
        _patch_browser_session(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"

        with pytest.raises(SiteOwnerRequiredError), Kintai():
            pass

    def test_launch_rejects_missing_owner(self, monkeypatch):
        """`Browsers.launch(Kintai)` 経路でも OWNER 未設定だと SiteOwnerRequiredError。"""
        _patch_browser_session(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"

        with Browsers() as browsers, pytest.raises(SiteOwnerRequiredError):
            browsers.launch(Kintai)

    def test_error_message_guides_to_the_rule(self, monkeypatch):
        """エラー文が「書き方」と「判断基準の在り処」と「管理者へ連絡」を案内する。"""
        _patch_browser_session(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"

        with pytest.raises(SiteOwnerRequiredError) as raised, Browsers() as browsers:
            browsers.launch(Kintai)

        message = str(raised.value)
        assert "OWNER =" in message
        # 基底クラス名は呼び出し側が渡す（__base__ に頼ると多重継承でずれる）
        assert "class Kintai(SiteBase):" in message
        assert "ライブラリ開発規約.md" in message
        assert "ライブラリ管理者へ連絡" in message

    def test_comken_module_is_exempt(self, monkeypatch):
        """`comken.` 配下のクラスは OWNER が空でも起動できる（免除が効く）。"""
        _patch_browser_session(monkeypatch)

        class ComkenInternalSite(SiteBase):
            NAME = "comken_internal"
            # OWNER = "" のまま（免除の確認）

        ComkenInternalSite.__module__ = COMKEN_BROWSER_MODULE

        with Browsers() as browsers:
            assert isinstance(browsers.launch(ComkenInternalSite), ComkenInternalSite)


class TestSiteBaseStartedLog:
    """起動が成功した後に出る INFO ログのテスト。"""

    def test_logs_once_on_launch(self, caplog, monkeypatch):
        """`Browsers.launch()` 経路で `site=` `owner=` `defined=` が1行出る。"""
        _patch_browser_session(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "勤怠 / 小栗"

        with caplog.at_level(logging.INFO, logger=BROWSER_LOGGER), Browsers() as browsers:
            browsers.launch(Kintai)

        messages = _info_messages(caplog)
        assert len(messages) == 1
        assert "site=kintai" in messages[0]
        assert "owner=勤怠 / 小栗" in messages[0]
        assert f"defined={Kintai.__module__}" in messages[0]

    def test_logs_once_with_site(self, caplog, monkeypatch):
        """`with Kintai()` 経路でも同じログが1行だけ出る（二重に出さない）。"""
        _patch_browser_session(monkeypatch)

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "勤怠 / 小栗"

        with caplog.at_level(logging.INFO, logger=BROWSER_LOGGER), Kintai():
            pass

        messages = _info_messages(caplog)
        assert len(messages) == 1
        assert "site=kintai" in messages[0]

    def test_no_log_when_launch_fails(self, caplog, monkeypatch):
        """ブラウザの起動に失敗したらログは出ない（「使った」という嘘を残さない）。"""

        def _fail(*args, **kwargs):
            raise RuntimeError("ブラウザを起動できなかった")

        monkeypatch.setattr(Browsers, "launch_session", _fail)

        class Kintai(SiteBase):
            NAME = "kintai"
            OWNER = "勤怠 / 小栗"

        with (
            caplog.at_level(logging.INFO, logger=BROWSER_LOGGER),
            Browsers() as browsers,
            pytest.raises(RuntimeError),
        ):
            browsers.launch(Kintai)

        assert _info_messages(caplog) == []

    def test_comken_module_is_not_logged(self, caplog, monkeypatch):
        """comken 配下のクラスはログにも出さない（管理者が把握済みのため）。"""
        _patch_browser_session(monkeypatch)

        class ComkenInternalSite(SiteBase):
            NAME = "comken_internal"
            OWNER = "comken"

        ComkenInternalSite.__module__ = COMKEN_BROWSER_MODULE

        with caplog.at_level(logging.INFO, logger=BROWSER_LOGGER), Browsers() as browsers:
            browsers.launch(ComkenInternalSite)

        assert _info_messages(caplog) == []


class TestSiteBaseLibraryConflict:
    """ライブラリ公認サイトとの NAME 衝突検出のテスト。"""

    def test_project_site_with_library_name_raises(self, monkeypatch):
        """SITES に登録済みの NAME をプロジェクト側で定義すると SiteAlreadyInLibraryError。"""

        class LibrarySite(SiteBase):
            NAME = "library_shared_site"
            OWNER = "comken"

        # comken 配下に置く → OWNER 検査は免除される（ライブラリ側の前提）
        LibrarySite.__module__ = COMKEN_BROWSER_MODULE
        # SITES に登録して、ライブラリ側を装う
        import comken.toolbox.browser.sites as sites_module

        monkeypatch.setattr(sites_module, "SITES", (LibrarySite,))

        class ProjectSite(SiteBase):
            NAME = "library_shared_site"
            OWNER = "project / テスト"

        with Browsers() as browsers, pytest.raises(SiteAlreadyInLibraryError):
            browsers.launch(ProjectSite)

    def test_project_site_with_different_name_passes(self, monkeypatch):
        """ライブラリ側と NAME が違うプロジェクト側はそのまま起動できる。"""
        import comken.toolbox.browser.sites as sites_module

        class LibrarySite(SiteBase):
            NAME = "library_site"

        LibrarySite.__module__ = COMKEN_BROWSER_MODULE
        monkeypatch.setattr(sites_module, "SITES", (LibrarySite,))

        _patch_browser_session(monkeypatch)

        class ProjectSite(SiteBase):
            NAME = "project_site"
            OWNER = "project / テスト"

        with Browsers() as browsers:
            site = browsers.launch(ProjectSite)
            assert isinstance(site, ProjectSite)


class TestSalesforceBaseOwner:
    """SalesforceBase の OWNER 必須検査のテスト。"""

    def test_rejects_missing_owner(self):
        """SalesforceBase サブクラスで OWNER 未設定だと SiteOwnerRequiredError。"""

        class Org(SalesforceBase):
            DOMAIN_URL = DOMAIN_URL
            CREDENTIAL_PREFIX = "test_org"

        with pytest.raises(SiteOwnerRequiredError) as raised:
            Org()

        assert "class Org(SalesforceBase):" in str(raised.value)

    def test_rejects_before_touching_the_network(self):
        """OWNER の検査は認証より先。ネットワークへ出る前に止まる。"""

        class Org(SalesforceBase):
            DOMAIN_URL = DOMAIN_URL
            CREDENTIAL_PREFIX = "test_org"

        with (
            patch("comken.toolbox.salesforce.oauth_credentials.requests.post") as post,
            pytest.raises(SiteOwnerRequiredError),
        ):
            Org(auth=ClientCredentialsOAuth("CID", "CSECRET", DOMAIN_URL))

        post.assert_not_called()

    def test_comken_module_is_exempt(self):
        """`comken.` 配下の SalesforceBase サブクラスは OWNER 検査されない。"""

        class ComkenInternalOrg(SalesforceBase):
            DOMAIN_URL = DOMAIN_URL
            CREDENTIAL_PREFIX = "test_comken_org"
            # OWNER = "" のまま（免除の確認）

        ComkenInternalOrg.__module__ = COMKEN_SALESFORCE_MODULE

        with _salesforce_http():
            ComkenInternalOrg(auth=ClientCredentialsOAuth("CID", "CSECRET", DOMAIN_URL))


class TestSalesforceStartedLog:
    """Salesforce 側の起動 INFO ログのテスト。"""

    def test_logs_once_after_authentication(self, caplog):
        """認証が済んだ後に `site=` `owner=` `defined=` が1行出る。"""

        class Org(SalesforceBase):
            DOMAIN_URL = DOMAIN_URL
            CREDENTIAL_PREFIX = "test_org"
            OWNER = "経理 / 田中"

        with caplog.at_level(logging.INFO, logger=SALESFORCE_LOGGER), _salesforce_http():
            Org(auth=ClientCredentialsOAuth("CID", "CSECRET", DOMAIN_URL))

        messages = _info_messages(caplog)
        assert len(messages) == 1
        assert "site=Org" in messages[0]
        assert "owner=経理 / 田中" in messages[0]
        assert f"defined={Org.__module__}" in messages[0]

    def test_no_log_when_authentication_fails(self, caplog, monkeypatch):
        """認証に失敗したらログは出ない（「使った」という嘘を残さない）。"""

        class Org(SalesforceBase):
            DOMAIN_URL = DOMAIN_URL
            CREDENTIAL_PREFIX = "test_org"
            OWNER = "経理 / 田中"

        def _fail(self):
            raise RuntimeError("認証できなかった")

        monkeypatch.setattr(SalesforceBase, "_authenticate", _fail)

        with (
            caplog.at_level(logging.INFO, logger=SALESFORCE_LOGGER),
            _salesforce_http(),
            pytest.raises(RuntimeError),
        ):
            Org(auth=ClientCredentialsOAuth("CID", "CSECRET", DOMAIN_URL))

        assert _info_messages(caplog) == []
