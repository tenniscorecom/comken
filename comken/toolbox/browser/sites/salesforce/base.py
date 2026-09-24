r"""comken/toolbox/browser/sites/salesforce/base.py — SalesforceReportBrowser
（ブラウザ経由の雛形）。

Reports and Dashboards REST APIの2000行上限を超えるレポート（マトリックス／統合など
SOQLに書き換えられない形式）向けの最終手段。画面のエクスポート機能
（``?export=1&xf=csv``）を直接叩く。

ログインは ``go_login()`` + ``wait_for_manual_login()``（人が手動で入力）、または
``login_with_credentials()``（DPAPIに保存したID/パスワードを自動入力、MFA等は
引き続き人が対応）のどちらか。接続アプリの登録・OAuth初回認可を挟まないため、
一時的に使いたいだけの時に手早い。ログインさえ済めば、実際のN件のダウンロードは
requests + ThreadPoolExecutor で並列に行う。

組織ごとのクラスは同フォルダの ``solution.py`` / ``solution_sandbox.py`` にあり、
URL と認証情報名は API 側の組織クラス（``comken.toolbox.salesforce.sites``）の
``DOMAIN_URL`` / ``CREDENTIAL_PREFIX`` をそのまま使う（同じ URL を二重に書かない）。

> [!warning] URL は仮の値
> **このリポジトリは公開しているので、実際の組織の URL を書かない。**
> `BASE_URL` はダミーで、共有サーバーへ配置するときに実際の値へ書き換える
> （`comken/toolbox/salesforce/sites/` の `Solution` と同じ扱い）。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import requests

from comken.exceptions import BrowserNotStartedError, SalesforceReportExportError
from comken.toolbox.browser import SiteBase
from comken.toolbox.browser.sites.salesforce.pages.login_page import LoginPage
from comken.toolbox.salesforce.report import report_id_from_url

if TYPE_CHECKING:
    from comken.toolbox.browser.management import BrowserSession

logger = logging.getLogger(__name__)

# export_reports() で同時に投げるHTTPリクエストの既定数
_DEFAULT_MAX_WORKERS = 10

# 1リクエストあたりのタイムアウト秒数。集計系レポートは重いことがある
_DEFAULT_REQUEST_TIMEOUT_SECONDS = 300

# keep_alive_report_id を開く既定の間隔（秒）
_DEFAULT_KEEP_ALIVE_INTERVAL_SECONDS = 300


class SalesforceReportBrowser(SiteBase):
    """Salesforceのレポートをブラウザ経由でCSVダウンロードするための雛形。

    URL は example の値のまま。利用プロジェクト側で継承して書き換える
    （BASE_URL を実際の組織の My Domain URL へ）。

    ログイン方法は2通り:

    - ``go_login()`` + ``wait_for_manual_login()`` — 人がブラウザでID/パスワード/
      MFAを手動入力する
    - ``login_with_credentials(prefix)`` — DPAPIに保存したID/パスワードを自動
      入力する（MFA等の追加確認が出た場合は、続けて ``wait_for_manual_login()``
      を呼んで人が対応する）。``prefix`` は省略でき、その場合はクラスの
      ``CREDENTIAL_PREFIX`` を使う

    **ログインを使い回すには OPTIONS.PROFILE_ROOT を設定すること。**
    未設定だと起動のたびにまっさらなプロファイルになり、毎回ログインし直しになる
    （`docs/browser.md` の「ログイン状態を残す」を参照）:

        class MySalesforceOptions(BrowserOptions):
            PROFILE_ROOT = r"C:\\作業\\salesforce_profile"

        class MySalesforce(SalesforceReportBrowser):
            OPTIONS = MySalesforceOptions
            CREDENTIAL_PREFIX = "salesforce_temp"

        with MySalesforce() as sf:
            sf.login_with_credentials()     # prefix省略 → CREDENTIAL_PREFIXを使う
            sf.wait_for_manual_login()      # 初回だけ。2回目以降はプロファイルに残る
            for report_id, path in sf.export_reports(report_urls, "出力先"):
                ...
    """

    NAME = "salesforce"
    BASE_URL = "https://example.my.salesforce.com"
    OWNER = "comken"

    # 認証情報のキー名の頭。組織クラスで指定する
    # （``comken.toolbox.salesforce.client.SalesforceBase.CREDENTIAL_PREFIX`` と同じ役割）
    CREDENTIAL_PREFIX = ""

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。

        ID/パスワードを自分で入力するなら ``LoginPage.login()``、人が手動で
        入力するならこの後 ``wait_for_manual_login()`` を呼ぶ。
        """
        logger.info("Salesforceのログイン画面を開きます: url=%s", self.BASE_URL)
        return self.to(LoginPage).go()

    def login_with_credentials(self, prefix: str = "") -> None:
        """DPAPIに保存したID/パスワードでログインを試みる。

        MFA（認証コード・端末認証など）が要求される組織では、これだけでは
        ログインが完了しない。続けて ``wait_for_manual_login()`` を呼び、
        人がブラウザで残りの確認を終えるのを待つこと。

        Args:
            prefix: DPAPIに登録した認証情報のシステム名
                （``comken.toolbox.credentials.Credentials`` のサイト名）。
                ``username`` / ``password`` の2項目を登録しておく
                （例: ``python -m comken cred gui``）。**省略時はクラスの
                ``CREDENTIAL_PREFIX``** を使う（本番とテストを切り替えるときだけ渡す）。

        Raises:
            CredentialNotFoundError: prefix配下に username/password が未登録の場合。
            CredentialDecryptionError: 別のユーザー・PCで登録されていて復号できない場合。
        """
        from comken.toolbox.credentials import Credentials

        prefix = prefix or self.CREDENTIAL_PREFIX
        logger.info("DPAPIの認証情報でログインを試みます: prefix=%s", prefix)
        cred = Credentials(prefix)
        login_page = self.go_login()
        login_page.login(cred.username, cred.password)

    def wait_for_manual_login(self) -> None:
        """ブラウザでの手動ログインが終わるまで待つ（ターミナルでEnter待ち）。

        ``BrowserOptions.HEADLESS`` は既定で ``False`` のため、通常はブラウザの
        画面が見える状態で起動している。そこへ人がID/パスワード/MFAを入力し
        （``login_with_credentials()`` 済みならMFAだけ）、ログインが終わったら
        こちらのターミナルで Enter を押す。
        """
        logger.info("手動ログインの完了待ちに入ります（ターミナルでEnter待ち）")
        input("ブラウザでログイン（必要ならMFAも）を完了したら、ここで Enter を押してください...")
        logger.info("手動ログインの完了を受け付けました")

    def export_reports(
        self,
        reports: Mapping[str, str | Path],
        *,
        export_format: str = "csv",
        encoding: str = "Shift_JIS",
        max_workers: int = _DEFAULT_MAX_WORKERS,
        keep_alive_report_id: str | None = None,
        keep_alive_interval: float = _DEFAULT_KEEP_ALIVE_INTERVAL_SECONDS,
    ) -> Iterator[tuple[str, Path]]:
        """ログイン済みのブラウザのセッションCookieを requests へ引き継ぎ、
        並列にダウンロードして (report_id, 保存先パス) を返す。

        ファイル名・置き場所は呼び出し側が ``reports`` で完全に指定する
        （comken側では report_id ベースの名前を強制しない）。

        ブラウザはログインの確立だけに使い、N件のダウンロード自体は
        requests + ThreadPoolExecutor で並列に行う。

            with Salesforce() as sf:
                sf.login_with_credentials("salesforce_temp")
                sf.wait_for_manual_login()
                reports = {
                    report_url: f"出力先/{report_name}.csv"
                    for report_url, report_name in ...
                }
                for report_id, path in sf.export_reports(reports):
                    ...

        Args:
            reports: ``{レポート画面のURL（またはレポートID）: 保存先ファイルパス}``
                の対応表。保存先の親フォルダが無ければ作成する。
            export_format: "csv" または "xls"。保存先のファイル名の拡張子とは
                無関係（Salesforceに実際に何形式で吐かせるかだけを決める）。
            encoding: エクスポートする文字コード。既定は ``Shift_JIS``（CP932相当）。
                Excel・社内システムでの扱いやすさを優先している。UTF-8で欲しい
                場合は ``"UTF-8"`` を渡す。
            max_workers: 同時に投げるリクエストの数。既定10。
            keep_alive_report_id: ダウンロード中、この間隔でブラウザに開かせ続ける
                軽いレポートのID（例: 0件のレポート）。ドメインは今のセッションの
                ものをそのまま使うため、URLではなくIDだけ渡せばよい。省略時は
                何もしない。件数が多くダウンロードに時間がかかる場合、ブラウザ
                自体はログイン後なにも操作していないため、途中でSalesforce側の
                セッションが切れて ``SalesforceReportExportError`` になることが
                ある。その暫定対処として指定する（恒久対処ではない。根本的には
                Salesforce管理者にセッションタイムアウトの設定を確認してもらうのが筋）。
            keep_alive_interval: ``keep_alive_report_id`` を開く間隔（秒）。既定300秒（5分）。

        Yields:
            (report_id, 保存したファイルのパス) のタプル。
            **完了した順**に返るため、``reports`` の順序とは限らない。

        Raises:
            BrowserNotStartedError: 未起動の場合。
            SalesforceReportIDNotFoundError: URLからレポートIDを取り出せない場合。
            SalesforceReportExportError: いずれかのレポートでエクスポートが失敗した場合
                （ログイン未実行・セッション切れ等）。
        """
        session = self._require_session()
        domain = _domain_of(session.current_url)
        driver_cookies = session.raw.get_cookies()
        http_session = _cookies_to_requests_session(driver_cookies)
        logger.info(
            "export_reports() 開始: 件数=%d domain=%s max_workers=%d encoding=%s cookie数=%d",
            len(reports),
            domain,
            max_workers,
            encoding,
            len(driver_cookies),
        )

        keep_alive_url = (
            f"{domain}/{keep_alive_report_id}" if keep_alive_report_id is not None else None
        )
        keep_alive_thread, stop_keep_alive = _start_keep_alive(
            session, keep_alive_url, keep_alive_interval
        )
        done = 0
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _export_via_http, http_session, domain, url, export_format, encoding
                    ): Path(destination)
                    for url, destination in reports.items()
                }
                for future in as_completed(futures):
                    destination = futures[future]
                    report_id, content = future.result()
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
                    done += 1
                    logger.info(
                        "レポートをダウンロードしました(%d/%d): report_id=%s path=%s",
                        done,
                        len(reports),
                        report_id,
                        destination,
                    )
                    yield report_id, destination
        finally:
            stop_keep_alive.set()
            if keep_alive_thread is not None:
                keep_alive_thread.join()
            logger.info("export_reports() 終了: 完了=%d/%d", done, len(reports))

    def _require_session(self) -> BrowserSession:
        """起動済みの BrowserSession を返す。未起動なら理由を示して落とす。"""
        if self.session is None:
            raise BrowserNotStartedError(
                f"{self.__class__.__name__} はまだ起動していません。"
                f"`with {self.__class__.__name__}() as site:` の中で使ってください。"
            )
        return self.session


def _start_keep_alive(
    session: BrowserSession, url: str | None, interval: float
) -> tuple[threading.Thread | None, threading.Event]:
    """指定したURLを一定間隔で開き続けるスレッドを始める（export_reports()のセッション維持用）。

    長時間の並列ダウンロード中、ブラウザ自体は何も操作しないため
    Salesforce側のセッションが途中で切れることがある暫定対処。
    url が None なら何もしない（スレッドは作らない）。

    呼び出し側は必ず ``finally`` で戻り値の Event を ``set()`` してから
    スレッドを ``join()`` して止めること。
    """
    stop = threading.Event()
    if url is None:
        return None, stop

    logger.info("セッション維持スレッドを開始します: url=%s interval=%s秒", url, interval)

    def _loop() -> None:
        while not stop.wait(interval):
            try:
                session.open(url)
                logger.debug("セッション維持のため開き直しました: %s", url)
            except Exception:
                logger.warning(
                    "セッション維持のためのアクセスに失敗しました: %s", url, exc_info=True
                )

    thread = threading.Thread(target=_loop, name="salesforce-keep-alive", daemon=True)
    thread.start()
    return thread, stop


def _domain_of(url: str) -> str:
    """URL から scheme + netloc だけを取り出す（例: https://example.my.salesforce.com）。"""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _cookies_to_requests_session(driver_cookies: list[dict]) -> requests.Session:
    """Seleniumの driver.get_cookies() を requests.Session の Cookie へ移す。

    ブラウザで確立したログインセッションを、requests 側でもそのまま使えるようにする。
    """
    http_session = requests.Session()
    for cookie in driver_cookies:
        http_session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain", ""))
    logger.debug("ブラウザのcookieをrequestsへ引き継ぎました: %d件", len(driver_cookies))
    return http_session


def _export_via_http(
    http_session: requests.Session,
    domain: str,
    report_url: str,
    export_format: str,
    encoding: str,
) -> tuple[str, bytes]:
    """1件のレポートをHTTPで直接エクスポートする（export_reports() の並列実行単位）。"""
    report_id = report_id_from_url(report_url)
    logger.debug("レポートのエクスポートを開始します: report_id=%s", report_id)
    response = http_session.get(
        f"{domain}/{report_id}",
        params={"isdtp": "p1", "export": "1", "enc": encoding, "xf": export_format},
        timeout=_DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )
    content_type = response.headers.get("Content-Type", "")
    disposition = response.headers.get("Content-Disposition", "")
    looks_like_export = "attachment" in disposition.lower() or export_format in content_type.lower()
    if response.status_code != requests.codes.ok or not looks_like_export:
        logger.warning(
            "レポートのエクスポートに失敗しました: report_id=%s status=%d content_type=%r",
            report_id,
            response.status_code,
            content_type,
        )
        raise SalesforceReportExportError(report_id, response.status_code, content_type)
    logger.debug(
        "レポートのエクスポートに成功しました: report_id=%s bytes=%d",
        report_id,
        len(response.content),
    )
    return report_id, response.content
