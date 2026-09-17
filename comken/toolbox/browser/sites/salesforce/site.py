r"""comken/toolbox/browser/sites/salesforce/site.py — Salesforceレポートのブラウザ経由ダウンロード。

Reports and Dashboards REST APIの2000行上限を超えるレポート（マトリックス／統合など
SOQLに書き換えられない形式）向けの最終手段。画面のエクスポート機能
（``?export=1&xf=csv``）を直接叩く。

ログインは人が手動で行う（``go_login()`` + ``wait_for_manual_login()``）。
接続アプリの登録・OAuth初回認可を挟まないため、一時的に使いたいだけのときに手早い。
ログインさえ済めば、実際のN件のダウンロードは requests + ThreadPoolExecutor で並列に行う。

レポートIDの抽出は comken.toolbox.salesforce.report.report_id_from_url() をそのまま使う
（toolbox.browser → toolbox.salesforce は tests/test_layers.py の ALLOWED_SAME_LAYER で
許可済み）。

> [!warning] URL は仮の値
> **このリポジトリは公開しているので、実際の組織の URL を書かない。**
> `BASE_URL` はダミーで、共有サーバーへ配置するときに実際の値へ書き換える
> （`comken/toolbox/salesforce/sites/` の `Solution` と同じ扱い）。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import requests

from comken.exceptions import SalesforceReportExportError, SiteNotStartedError
from comken.toolbox.browser import SiteBase
from comken.toolbox.salesforce.report import report_id_from_url

if TYPE_CHECKING:
    from comken.toolbox.browser.management import BrowserSession

logger = logging.getLogger(__name__)

# export_reports() で同時に投げるHTTPリクエストの既定数
_DEFAULT_MAX_WORKERS = 10

# 1リクエストあたりのタイムアウト秒数。集計系レポートは重いことがある
_DEFAULT_REQUEST_TIMEOUT_SECONDS = 300

# keep_alive_url を開く既定の間隔（秒）
_DEFAULT_KEEP_ALIVE_INTERVAL_SECONDS = 300


class Salesforce(SiteBase):
    """Salesforceのレポートをブラウザ経由でCSVダウンロードするための雛形。

    URL は example の値のまま。利用プロジェクト側で継承して書き換える
    （BASE_URL を実際の組織の My Domain URL へ）。

    ログインは ``go_login()`` + ``wait_for_manual_login()`` で人が手動で行う
    （接続アプリの登録・OAuth初回認可を挟まないため、一時的に使いたいだけの
    ときに手早い。MFAもそのままブラウザで入力できる）。

    **ログインを使い回すには OPTIONS.PROFILE_ROOT を設定すること。**
    未設定だと起動のたびにまっさらなプロファイルになり、毎回ログインし直しになる
    （`docs/browser.md` の「ログイン状態を残す」を参照）:

        class MySalesforceOptions(BrowserOptions):
            PROFILE_ROOT = r"C:\\作業\\salesforce_profile"

        class MySalesforce(Salesforce):
            OPTIONS = MySalesforceOptions

        with MySalesforce() as sf:
            sf.go_login()
            sf.wait_for_manual_login()      # 初回だけ。2回目以降はプロファイルに残る
            for report_id, path in sf.export_reports(report_urls, "出力先"):
                ...
    """

    NAME = "salesforce"
    BASE_URL = "https://example.my.salesforce.com"
    OWNER = "comken"

    def go_login(self) -> None:
        """ログイン画面を開く。ID/パスワード/MFAは人がブラウザで手動入力する想定。

        ログイン後は ``wait_for_manual_login()`` を呼ぶこと。
        """
        self._require_session().open(self.BASE_URL)

    def wait_for_manual_login(self) -> None:
        """ブラウザでの手動ログインが終わるまで待つ（ターミナルでEnter待ち）。

        ``BrowserOptions.HEADLESS`` は既定で ``False`` のため、通常はブラウザの
        画面が見える状態で起動している。そこへ人がID/パスワード/MFAを入力し、
        ログインが終わったらこちらのターミナルで Enter を押す。
        """
        input("ブラウザでログイン（必要ならMFAも）を完了したら、ここで Enter を押してください...")

    def export_reports(
        self,
        report_urls: Sequence[str],
        directory: str | Path,
        *,
        export_format: str = "csv",
        encoding: str = "Shift_JIS",
        max_workers: int = _DEFAULT_MAX_WORKERS,
        keep_alive_url: str | None = None,
        keep_alive_interval: float = _DEFAULT_KEEP_ALIVE_INTERVAL_SECONDS,
    ) -> Iterator[tuple[str, Path]]:
        """ログイン済みのブラウザのセッションCookieを requests へ引き継ぎ、
        並列にダウンロードして (report_id, 保存先パス) を返す。

        ブラウザはログインの確立だけに使い、N件のダウンロード自体は
        requests + ThreadPoolExecutor で並列に行う。

            with Salesforce() as sf:
                sf.go_login()
                sf.wait_for_manual_login()
                for report_id, path in sf.export_reports(report_urls, "出力先"):
                    ...

        Args:
            report_urls: レポート画面のURL（またはレポートID）のリスト。
            directory: 保存先ディレクトリ。無ければ作成する。
            export_format: "csv" または "xls"。
            encoding: エクスポートする文字コード。既定は ``Shift_JIS``（CP932相当）。
                Excel・社内システムでの扱いやすさを優先している。UTF-8で欲しい
                場合は ``"UTF-8"`` を渡す。
            max_workers: 同時に投げるリクエストの数。既定10。
            keep_alive_url: ダウンロード中、この間隔でブラウザに開かせ続ける
                軽いページのURL（例: 0件のレポート）。省略時は何もしない。
                件数が多くダウンロードに時間がかかる場合、ブラウザ自体は
                ログイン後なにも操作していないため、途中でSalesforce側の
                セッションが切れて ``SalesforceReportExportError`` になることが
                ある。その暫定対処として指定する（恒久対処ではない。根本的には
                Salesforce管理者にセッションタイムアウトの設定を確認してもらうのが筋）。
            keep_alive_interval: ``keep_alive_url`` を開く間隔（秒）。既定300秒（5分）。

        Yields:
            (report_id, ダウンロードしたファイルのパス) のタプル。ファイルは
            ``directory`` 直下に ``{report_id}.{export_format}`` として保存される。
            **完了した順**に返るため、``report_urls`` の順序とは限らない。

        Raises:
            SiteNotStartedError: 未起動の場合。
            SalesforceReportIDNotFoundError: URLからレポートIDを取り出せない場合。
            SalesforceReportExportError: いずれかのレポートでエクスポートが失敗した場合
                （ログイン未実行・セッション切れ等）。
        """
        session = self._require_session()
        domain = _domain_of(session.current_url)
        http_session = _cookies_to_requests_session(session.raw.get_cookies())

        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)

        keep_alive_thread, stop_keep_alive = _start_keep_alive(
            session, keep_alive_url, keep_alive_interval
        )
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _export_via_http, http_session, domain, url, export_format, encoding
                    ): url
                    for url in report_urls
                }
                for future in as_completed(futures):
                    report_id, content = future.result()
                    path = target_dir / f"{report_id}.{export_format}"
                    path.write_bytes(content)
                    logger.info(
                        "レポートをダウンロードしました: report_id=%s path=%s", report_id, path
                    )
                    yield report_id, path
        finally:
            stop_keep_alive.set()
            if keep_alive_thread is not None:
                keep_alive_thread.join()

    def _require_session(self) -> BrowserSession:
        """起動済みの BrowserSession を返す。未起動なら理由を示して落とす。"""
        if self.session is None:
            raise SiteNotStartedError(self.__class__)
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
    response = http_session.get(
        f"{domain}/{report_id}",
        params={"isdtp": "p1", "export": "1", "enc": encoding, "xf": export_format},
        timeout=_DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )
    content_type = response.headers.get("Content-Type", "")
    disposition = response.headers.get("Content-Disposition", "")
    looks_like_export = "attachment" in disposition.lower() or export_format in content_type.lower()
    if response.status_code != requests.codes.ok or not looks_like_export:
        raise SalesforceReportExportError(report_id, response.status_code, content_type)
    return report_id, response.content
