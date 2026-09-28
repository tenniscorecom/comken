"""comken.toolbox.browser.sites.salesforce.base のテスト。

実際の Edge は起動せず、WebDriver をモックに差し替えて配線だけを確認する
（tests/test_browser_sites_ntt.py と同じ方針）。
"""

import logging
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from comken.exceptions import BrowserError, SalesforceError
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.sites.salesforce.base import (
    SalesforceReportBrowser,
    _cookies_to_requests_session,
    _domain_of,
    _find_footer_start,
    _start_keep_alive,
    _strip_report_footer,
)
from comken.toolbox.browser.sites.salesforce.pages.login_page import LoginPage

REPORT_URL_1 = "https://example.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE1AS/view"
REPORT_URL_2 = "https://example.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE2AS/view"


def _patch_browser(monkeypatch) -> None:
    """Edge を起動せずに、``with SalesforceReportBrowser() as sf:`` の経路を通す。

    `BrowserSession.__enter__` の戻り値を self にして _driver に MagicMock を入れる。
    `SiteBase.__enter__` が BrowserSession を作って `session.__enter__()` を
    呼ぶ流れに差し込む。
    """

    def enter(self):
        self._driver = MagicMock()
        return self

    monkeypatch.setattr(BrowserSession, "__enter__", enter)
    monkeypatch.setattr(BrowserSession, "__exit__", lambda self, *a: None)


class TestPublicApi:
    """URLがダミーのままの雛形。組織別クラスは comken.toolbox.browser.sites.salesforce にある。"""

    def test_class_attributes(self):
        assert SalesforceReportBrowser.NAME
        assert SalesforceReportBrowser.BASE_URL
        assert SalesforceReportBrowser.OWNER == "comken"


# report_id_from_url() 自体のテストは tests/test_salesforce.py に集約してある
# （comken.toolbox.salesforce.report をそのまま使っているだけなので、ここでは複製しない）。


class TestGoLogin:
    """go_login() — 人が手動でログインする画面を開く。"""

    def test_opens_base_url(self, monkeypatch):
        _patch_browser(monkeypatch)

        with SalesforceReportBrowser() as sf:
            driver = sf.session._driver
            sf.go_login()

        driver.get.assert_called_once_with(SalesforceReportBrowser.BASE_URL)

    def test_raises_when_not_started(self):
        sf = SalesforceReportBrowser()

        with pytest.raises(BrowserError):
            sf.go_login()


class TestWaitForManualLogin:
    """wait_for_manual_login() — 人がブラウザでログインを終えるのをEnter待ちする。"""

    def test_waits_for_enter_key(self, monkeypatch):
        calls = []
        monkeypatch.setattr("builtins.input", lambda prompt="": calls.append(prompt))

        SalesforceReportBrowser().wait_for_manual_login()

        assert len(calls) == 1


class TestLoginPageLogin:
    """LoginPage.login() — ID/パスワードを入力してログインボタンを押す。"""

    def test_fills_username_and_password_and_clicks_login(self, monkeypatch):
        _patch_browser(monkeypatch)

        with SalesforceReportBrowser() as sf:
            page = sf.to(LoginPage)
            page._wait = MagicMock()
            element = MagicMock()
            page._wait.until.return_value = element

            page.login("user@example.com", "secret")

            element.send_keys.assert_any_call("user@example.com")
            element.send_keys.assert_any_call("secret")
            element.click.assert_called_once()


class TestLoginWithCredentials:
    """login_with_credentials() — DPAPIのID/パスワードでログインフォームへ入力する。"""

    def test_uses_credentials_to_login(self, monkeypatch):
        _patch_browser(monkeypatch)
        cred = MagicMock(username="user@example.com", password="secret")
        login_page = MagicMock()
        with (
            SalesforceReportBrowser() as sf,
            patch("comken.toolbox.credentials.Credentials", return_value=cred) as cred_class,
            patch.object(SalesforceReportBrowser, "go_login", return_value=login_page) as go_login,
        ):
            sf.login_with_credentials("salesforce_temp")

        cred_class.assert_called_once_with("salesforce_temp")
        go_login.assert_called_once()
        login_page.login.assert_called_once_with("user@example.com", "secret")

    def test_falls_back_to_class_credential_prefix_when_omitted(self, monkeypatch):
        """prefix省略時は、クラスの CREDENTIAL_PREFIX を使う。"""

        class _MyOrg(SalesforceReportBrowser):
            CREDENTIAL_PREFIX = "salesforce_solution"

        _patch_browser(monkeypatch)
        cred = MagicMock(username="user@example.com", password="secret")
        with (
            _MyOrg() as sf,
            patch("comken.toolbox.credentials.Credentials", return_value=cred) as cred_class,
            patch.object(SalesforceReportBrowser, "go_login", return_value=MagicMock()),
        ):
            sf.login_with_credentials()

        cred_class.assert_called_once_with("salesforce_solution")

    def test_explicit_prefix_overrides_class_credential_prefix(self, monkeypatch):
        """明示的に渡した prefix は、クラスの CREDENTIAL_PREFIX より優先される。"""

        class _MyOrg(SalesforceReportBrowser):
            CREDENTIAL_PREFIX = "salesforce_solution"

        _patch_browser(monkeypatch)
        cred = MagicMock(username="user@example.com", password="secret")
        with (
            _MyOrg() as sf,
            patch("comken.toolbox.credentials.Credentials", return_value=cred) as cred_class,
            patch.object(SalesforceReportBrowser, "go_login", return_value=MagicMock()),
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

    def test_downloads_reports_to_the_given_destinations(self, monkeypatch, tmp_path):
        _patch_browser(monkeypatch)
        http_session = MagicMock()
        http_session.get.side_effect = [
            _csv_response(b"report1"),
            _csv_response(b"report2"),
        ]
        destination_1 = tmp_path / "月次レポート.csv"
        destination_2 = tmp_path / "サブフォルダ" / "四半期レポート.csv"
        with (
            SalesforceReportBrowser() as sf,
            patch(
                "comken.toolbox.browser.sites.salesforce.base.requests.Session",
                return_value=http_session,
            ),
        ):
            sf.session._driver.current_url = REPORT_URL_1
            sf.session._driver.get_cookies.return_value = [
                {"name": "sid", "value": "TOKEN", "domain": ".salesforce.com"}
            ]
            results = dict(
                sf.export_reports({REPORT_URL_1: destination_1, REPORT_URL_2: destination_2})
            )

        assert set(results) == {"00O5g00000ABCDE1AS", "00O5g00000ABCDE2AS"}
        assert results["00O5g00000ABCDE1AS"] == destination_1
        assert results["00O5g00000ABCDE2AS"] == destination_2
        assert destination_1.exists()
        assert destination_2.exists()

    def test_creates_parent_directory_of_destination(self, monkeypatch, tmp_path):
        _patch_browser(monkeypatch)
        http_session = MagicMock()
        http_session.get.return_value = _csv_response()
        destination = tmp_path / "nested" / "dir" / "report.csv"
        with (
            SalesforceReportBrowser() as sf,
            patch(
                "comken.toolbox.browser.sites.salesforce.base.requests.Session",
                return_value=http_session,
            ),
        ):
            sf.session._driver.current_url = REPORT_URL_1
            sf.session._driver.get_cookies.return_value = []
            list(sf.export_reports({REPORT_URL_1: destination}))

        assert destination.exists()

    def test_raises_when_response_is_html(self, monkeypatch, tmp_path):
        _patch_browser(monkeypatch)
        http_session = MagicMock()
        http_session.get.return_value = _html_response()
        with (
            SalesforceReportBrowser() as sf,
            patch(
                "comken.toolbox.browser.sites.salesforce.base.requests.Session",
                return_value=http_session,
            ),
            pytest.raises(SalesforceError),
        ):
            sf.session._driver.current_url = REPORT_URL_1
            sf.session._driver.get_cookies.return_value = []
            list(sf.export_reports({REPORT_URL_1: tmp_path / "report.csv"}))

    def test_raises_when_not_started(self):
        sf = SalesforceReportBrowser()

        with pytest.raises(BrowserError):
            list(sf.export_reports({REPORT_URL_1: "出力先/report.csv"}))


class TestStartKeepAlive:
    """_start_keep_alive() — export_reports() 中、ブラウザにURLを開かせ続ける暫定対処。"""

    def test_returns_none_thread_when_url_is_none(self, monkeypatch):
        _patch_browser(monkeypatch)

        with SalesforceReportBrowser() as sf:
            assert sf.session is not None
            session = sf.session
            thread, stop = _start_keep_alive(session, None, 300)

        assert thread is None
        assert not stop.is_set()

    def test_opens_url_repeatedly_until_stopped(self, monkeypatch):
        _patch_browser(monkeypatch)

        with SalesforceReportBrowser() as sf:
            assert sf.session is not None
            session = sf.session
            thread, stop = _start_keep_alive(session, REPORT_URL_1, 0.02)
            try:
                time.sleep(0.1)
            finally:
                stop.set()
                thread.join(timeout=1)

        assert not thread.is_alive()
        assert session._driver.get.call_count >= 2

    def test_survives_open_failure_and_keeps_running(self, monkeypatch):
        _patch_browser(monkeypatch)

        with SalesforceReportBrowser() as sf:
            assert sf.session is not None
            session = sf.session
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

    def test_keep_alive_thread_stops_after_completion(self, monkeypatch, tmp_path):
        _patch_browser(monkeypatch)
        http_session = MagicMock()
        http_session.get.return_value = _csv_response()
        with (
            SalesforceReportBrowser() as sf,
            patch(
                "comken.toolbox.browser.sites.salesforce.base.requests.Session",
                return_value=http_session,
            ),
        ):
            sf.session._driver.current_url = REPORT_URL_1
            sf.session._driver.get_cookies.return_value = []
            list(
                sf.export_reports(
                    {REPORT_URL_1: tmp_path / "report.csv"},
                    keep_alive_report_id="00O5g00000ABCDE9AS",
                    keep_alive_interval=0.02,
                )
            )

        active_threads = [t for t in threading.enumerate() if t.name == "salesforce-keep-alive"]
        assert active_threads == []

    def test_keep_alive_url_is_built_from_current_domain(self, monkeypatch, tmp_path):
        _patch_browser(monkeypatch)

        def _slow_get(*args, **kwargs):
            time.sleep(0.1)
            return _csv_response()

        http_session = MagicMock()
        http_session.get.side_effect = _slow_get
        with (
            SalesforceReportBrowser() as sf,
            patch(
                "comken.toolbox.browser.sites.salesforce.base.requests.Session",
                return_value=http_session,
            ),
        ):
            driver = sf.session._driver
            sf.session._driver.current_url = REPORT_URL_1
            sf.session._driver.get_cookies.return_value = []
            list(
                sf.export_reports(
                    {REPORT_URL_1: tmp_path / "report.csv"},
                    keep_alive_report_id="00O5g00000ABCDE9AS",
                    keep_alive_interval=0.02,
                )
            )

        driver.get.assert_any_call("https://example.my.salesforce.com/00O5g00000ABCDE9AS")


# CSV フッター除去で使うデータ（テスト本体で .encode("cp932") する）
_HEADER = "col1,col2"
_DATA_LINE = "1,2"
_FOOTER_LINES = [
    "Copyright (c) 2024 Example Inc. All rights reserved.",
    "機密情報 - 配布禁止",
    "作成者: 山田 太郎 / 2024-01-01 12:00",
    "株式会社サンプル",
]


def _build_csv_with_footer(
    body: str = "\n".join([_HEADER, _DATA_LINE, _DATA_LINE]),
    footer: list[str] | None = None,
    line_sep: str = "\n",
) -> bytes:
    """Salesforce 風の本体 + 空行 + フッターを cp932 で組み立てる。"""
    if footer is None:
        footer = list(_FOOTER_LINES)
    return (body + line_sep + line_sep + line_sep.join(footer) + line_sep).encode("cp932")


def _bytes_to_path(data: bytes, suffix: str = ".csv"):
    """テスト用: バイト列を一時ファイルに書き出して Path を返す。"""
    import os
    import tempfile
    from pathlib import Path

    fd, name = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return Path(name)


class TestFindFooterStart:
    """_find_footer_start() — 引用符の外にある最初の空行（フッター開始）を見つける。"""

    def test_finds_blank_line_before_footer(self):
        text = "col1,col2\n1,2\n\nフッター"

        # 「2」の直後、空白行の開始位置
        assert _find_footer_start(text) == len("col1,col2\n1,2\n")

    def test_returns_none_when_no_blank_line(self):
        assert _find_footer_start("col1,col2\n1,2\n") is None

    def test_treats_blank_line_before_data_as_not_footer(self):
        # 先頭が空白行だけだとデータ行が無いのでフッター扱いにしない
        assert _find_footer_start("\n\n1,2\n") is None

    def test_does_not_split_quoted_field_with_embedded_blank_line(self):
        # 値の中の \r\n\r\n は空行扱いしない（"1行目\r\n\r\n3行目" が一塊の値）
        text = 'col1,col2\n"1行目\r\n\r\n3行目",x\n\n'

        assert _find_footer_start(text) is None

    def test_handles_unix_only_newlines(self):
        assert _find_footer_start("a\nb\n\n\n") is None
        assert _find_footer_start("a\nb\n\nc\n") == len("a\nb\n")

    def test_handles_cr_lf_newlines(self):
        text = "col1,col2\r\n1,2\r\n\r\n"
        assert _find_footer_start(text) is None
        text = "col1,col2\r\n1,2\r\n\r\nfooter\r\n"
        assert _find_footer_start(text) == len("col1,col2\r\n1,2\r\n")

    def test_does_not_split_double_quote_inside_quoted_field(self):
        # "a""b" 中の "" はリテラルの " 1 文字として扱い、引用符は閉じない
        text = '"a""b",1\n2,3\n\nfooter\n'
        assert _find_footer_start(text) == len('"a""b",1\n2,3\n')


class TestStripReportFooter:
    """_strip_report_footer() — Salesforce の画面CSVが末尾に付けるフッターを取り除く。"""

    def test_strips_japanese_footer_and_preserves_data_bytes(self):
        body = _HEADER + "\n" + _DATA_LINE + "\n" + _DATA_LINE
        content = _build_csv_with_footer(body=body)

        stripped = _strip_report_footer(content, encoding="Shift_JIS")

        # 取り除いた結果は元のデータ部分（+ 区切りの改行1個まで）とバイト単位で同じ
        assert stripped == (body + "\n").encode("cp932")
        # comken の CSV で読めてエラーにならない
        from comken.toolbox.csv import CSV

        path = _bytes_to_path(stripped)
        with CSV(path, encoding="cp932", read_only=True) as csv:
            table = csv.read()

        assert len(table) == 2
        assert table.columns == ["col1", "col2"]

    def test_keeps_embedded_blank_line_in_quoted_value(self):
        body = _HEADER + "\n" + '"1行目\r\n\r\n3行目",x'
        content = (body + "\n\n" + "\n".join(_FOOTER_LINES) + "\n").encode("cp932")

        stripped = _strip_report_footer(content, encoding="Shift_JIS")

        # 値の中の空行は残し、フッター（空行以降）は消える
        assert stripped == (body + "\n").encode("cp932")

    def test_returns_content_unchanged_when_there_is_no_footer(self):
        body_bytes = (_HEADER + "\n" + _DATA_LINE + "\n" + _DATA_LINE + "\n").encode("cp932")

        assert _strip_report_footer(body_bytes, encoding="Shift_JIS") == body_bytes

    def test_works_with_unix_only_newlines(self):
        body = _HEADER + "\n" + _DATA_LINE + "\n" + _DATA_LINE
        content = (body + "\n\n" + "\n".join(_FOOTER_LINES) + "\n").encode("cp932")

        stripped = _strip_report_footer(content, encoding="Shift_JIS")

        assert stripped == (body + "\n").encode("cp932")

    def test_works_with_utf8(self):
        body = _HEADER + "\n" + _DATA_LINE + "\n" + _DATA_LINE
        content = (body + "\n\n" + "\n".join(_FOOTER_LINES) + "\n").encode("utf-8")

        stripped = _strip_report_footer(content, encoding="UTF-8")

        assert stripped == (body + "\n").encode("utf-8")

    def test_preserves_cp932_only_characters_through_roundtrip(self):
        # ① と 髙 は cp932 にはあるが標準の shift_jis には無い文字
        body = "col1,col2\n①,髙橋\n"
        footer = "Copyright (c) 2024 例示 / 機密情報 - 配布禁止 / 株式会社サンプル"
        content = (body + "\n" + footer + "\n").encode("cp932")

        stripped = _strip_report_footer(content, encoding="Shift_JIS")

        # decode→encode の往復で残す部分のバイト列が変わらない
        assert stripped == body.encode("cp932")

    def test_logs_warning_and_returns_content_unchanged_when_decode_fails(self, caplog):
        # cp932 として不正なバイト列を含む
        body = _HEADER + "\n" + _DATA_LINE + "\n" + _DATA_LINE
        footer_bytes = "バットモジデス".encode()
        content = body.encode("cp932") + b"\n\n" + footer_bytes + b"\n"

        module_logger = "comken.toolbox.browser.sites.salesforce.base"
        with caplog.at_level(logging.WARNING, logger=module_logger):
            stripped = _strip_report_footer(content, encoding="Shift_JIS")

        # decode に失敗したのでフッターは削らずそのまま返す
        assert stripped == content
        assert any("デコードに失敗" in record.getMessage() for record in caplog.records)

    def test_break_quote_aware_search(self):
        """引用符判定を壊したら値の中の空行で切られてテストが落ちること。

        実装が quote を無視して空行を探しているなら、quoted field の
        埋め込み空行 ``\\n\\n`` の位置をフッター開始と誤認して本文の途中で
        切ってしまい、結果がバイト単位で一致しなくなる。

        ここではデータ行とフッター行の間に**空行を挟まない**入力を与え、
        quoted field 内の ``\\n\\n`` が「引用符の外側の唯一の空行」に
        見えるかどうかで挙動を確かめる。
        """
        body = _HEADER + "\n" + '"1行目\n\n3行目",x'
        footer = "\n".join(_FOOTER_LINES)
        # データ末尾とフッターの間に空行を挟まない。値の中の \n\n が
        # 「唯一の空行候補」となり、引用符を見ない壊れた実装ならここで切られる。
        content = (body + "\n" + footer + "\n").encode("cp932")

        stripped = _strip_report_footer(content, encoding="Shift_JIS")

        # 引用符の外に空行が無いので何も削らない（= バイト単位で同じ）
        assert stripped == content

    def test_break_must_actually_strip_footer(self):
        """フッターを削らない素朴な実装なら comken の CSV が列数不一致で落ちる。

        ここで扱う入力をそのまま comken の ``CSV`` に読ませると ``CSVError``
        になる（= フッターが残っていることを確認）。同時に ``_strip_report_footer``
        を通すと読み込める（= フッターが落ちていることを確認）。
        """
        from comken.exceptions import CSVError
        from comken.toolbox.csv import CSV

        body = _HEADER + "\n" + _DATA_LINE + "\n" + _DATA_LINE
        csv_with_footer = _build_csv_with_footer(body=body)

        # フッター付き CSV は comken の CSV で CSVError（列数不一致）
        path_with = _bytes_to_path(csv_with_footer)
        with (
            pytest.raises(CSVError),
            CSV(path_with, encoding="cp932", read_only=True) as csv,
        ):
            csv.read()

        # フッター除去後は comken の CSV で 2 行として読める
        stripped = _strip_report_footer(csv_with_footer, encoding="Shift_JIS")
        path_without = _bytes_to_path(stripped)
        with CSV(path_without, encoding="cp932", read_only=True) as csv:
            table = csv.read()

        assert len(table) == 2
        assert table.columns == ["col1", "col2"]


class TestExportReportsStripsFooter:
    """export_reports() — CSV のとき保存前にフッターを取り除く（xls は変えない）。"""

    def test_csv_destination_has_no_footer(self, monkeypatch, tmp_path):
        _patch_browser(monkeypatch)
        body = _HEADER + "\n" + _DATA_LINE + "\n" + _DATA_LINE
        csv_bytes = _build_csv_with_footer(body=body)
        http_session = MagicMock()
        http_session.get.return_value = _csv_response(csv_bytes)
        destination = tmp_path / "report.csv"

        with (
            SalesforceReportBrowser() as sf,
            patch(
                "comken.toolbox.browser.sites.salesforce.base.requests.Session",
                return_value=http_session,
            ),
        ):
            sf.session._driver.current_url = REPORT_URL_1
            sf.session._driver.get_cookies.return_value = []
            list(sf.export_reports({REPORT_URL_1: destination}))

        # ファイルに保存された中身はデータ部分 + 区切りの改行（フッターは無い）
        assert destination.read_bytes() == (body + "\n").encode("cp932")

    def test_xls_destination_is_unchanged(self, monkeypatch, tmp_path):
        _patch_browser(monkeypatch)
        xls_bytes = b"not-a-real-xls-but-export_reports_should_not_touch_it"
        response = MagicMock()
        response.status_code = 200
        response.headers = {
            "Content-Type": "application/vnd.ms-excel",
            "Content-Disposition": "attachment; filename=report.xls",
        }
        response.content = xls_bytes
        http_session = MagicMock()
        http_session.get.return_value = response
        destination = tmp_path / "report.xls"

        with (
            SalesforceReportBrowser() as sf,
            patch(
                "comken.toolbox.browser.sites.salesforce.base.requests.Session",
                return_value=http_session,
            ),
        ):
            sf.session._driver.current_url = REPORT_URL_1
            sf.session._driver.get_cookies.return_value = []
            list(sf.export_reports({REPORT_URL_1: destination}, export_format="xls"))

        # Excel 形式は中身を変更しないのでフッター除去も走らない
        assert destination.read_bytes() == xls_bytes
