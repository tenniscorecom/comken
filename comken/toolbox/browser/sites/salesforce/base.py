r"""comken/toolbox/browser/sites/salesforce/base.py — SalesforceReportBrowser
（ブラウザ経由の雛形）。

Reports and Dashboards REST APIの2000行上限を超えるレポート（マトリックス／統合など
SOQLに書き換えられない形式）向けの最終手段。画面のエクスポート機能
（``?export=1&xf=csv``）を直接叩く。

CSV 出力には、データ末尾に空行を挟んで著作権・機密情報表示などのフッターが付く。
``export_reports()`` は保存前にこのフッター（最初の空行以降）を取り除く。

ログインは ``ensure_login()`` を**推奨**（DPAPIに保存したID/パスワードを自動入力し、
MFA等の追加確認は人が承認する。ログイン済みのセッションが残っているときは何も
せず return する）、または ``go_login()`` + ``wait_for_manual_login()``
（人が手動で入力）、``login_with_credentials()``（ID/パスワードの自動入力だけ
行い、MFA等は別途 ``wait_for_manual_login()`` を呼ぶ必要がある）の3通り。
接続アプリの登録・OAuth初回認可を挟まないため、一時的に使いたいだけの時に手早い。
ログインさえ済めば、実際のN件のダウンロードは requests + ThreadPoolExecutor で
並列に行う。

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
import time
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import requests

from comken.core.text import normalize_encoding
from comken.exceptions import BrowserError, LoginFailedError, SalesforceError
from comken.toolbox.browser import SiteBase
from comken.toolbox.browser.sites.salesforce.pages.login_page import LoginPage
from comken.toolbox.salesforce.report import report_id_from_url

if TYPE_CHECKING:
    from comken.toolbox.browser.management import BrowserSession

logger = logging.getLogger(__name__)


def _report_export_error(report_id: str, status_code: int, content_type: str) -> SalesforceError:
    """``SalesforceError`` の「画面のエクスポート機能でレポートを取得できなかった」文言。

    HTTPステータス自体は200で返るが、本文がCSV/XLSではなくHTMLのログイン画面や
    エラーページになっている場合に出る。
    """
    return SalesforceError(
        f"レポートのエクスポートに失敗しました: {report_id}"
        f"（HTTP {status_code}、Content-Type={content_type!r}）\n"
        "CSV/XLSではなくHTML（ログイン画面やエラーページ）が返っています。\n"
        "go_login() + wait_for_manual_login() でログインを済ませているか、"
        "セッションが切れていないかを確認してください。"
        "\n対処: 1. go_login() + wait_for_manual_login() でログインを済ませてから"
        "export_reports() を呼んでいるか確認してください。"
        "2. 時間が経ってセッションが切れていないか（長時間のバッチの後半で"
        "発生する場合はこれが疑わしい）。"
        "3. レポートそのものへのアクセス権・組織の Edition を確認してください。"
    )


# export_reports() で同時に投げるHTTPリクエストの既定数
_DEFAULT_MAX_WORKERS = 10

# 1リクエストあたりのタイムアウト秒数。集計系レポートは重いことがある
_DEFAULT_REQUEST_TIMEOUT_SECONDS = 300

# keep_alive_report_id を開く既定の間隔（秒）
_DEFAULT_KEEP_ALIVE_INTERVAL_SECONDS = 300

# wait_for_manual_login(): 最大の待ち時間（秒）。MFA まで含めて人が終えるのに
# 十分な時間を取る（既定10分）。タイムアウト後は LoginFailedError を送出する
_DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS = 600

# wait_for_manual_login(): ブラウザ状態を確認する間隔（秒）。
# 短すぎるとポーリングの負荷、長すぎると完了検知が遅れる。3秒は両者の妥協点
_DEFAULT_MANUAL_LOGIN_INTERVAL_SECONDS = 3

# time.monotonic / time.sleep はテストで差し替えられるよう、モジュールの属性として
# 参照する（テストでは _monotonic / _sleep を monkeypatch で差し替える）
_monotonic = time.monotonic
_sleep = time.sleep


class SalesforceReportBrowser(SiteBase):
    """Salesforceのレポートをブラウザ経由でCSVダウンロードするための雛形。

    URL は example の値のまま。利用プロジェクト側で継承して書き換える
    （BASE_URL を実際の組織の My Domain URL へ）。

    ログイン方法は3通り:

    - ``ensure_login()`` （**推奨**）— 既にログイン済みなら何もせず return。
      未ログインなら DPAPIに保存したID/パスワードを自動入力し、MFA等の追加確認は
      人が承認する。``prefix`` は省略でき、その場合はクラスの ``CREDENTIAL_PREFIX``
      を使う
    - ``go_login()`` + ``wait_for_manual_login()`` — 人がブラウザでID/パスワード/
      MFAを手動入力する
    - ``login_with_credentials(prefix)`` — DPAPIに保存したID/パスワードを自動
      入力する（MFA等の追加確認が出た場合は、続けて ``wait_for_manual_login()``
      を呼んで人が対応する）。``prefix`` は省略でき、その場合はクラスの
      ``CREDENTIAL_PREFIX`` を使う

    **ログインを使い回すには OPTIONS.PROFILE_ROOT を設定すること。**
    未設定だと起動のたびにまっさらなプロファイルになり、毎回ログインし直しになる
    （`docs/機能/browser.md` の「ログイン状態を残す」を参照）:

        class MySalesforceOptions(BrowserOptions):
            PROFILE_ROOT = r"C:\\作業\\salesforce_profile"

        class MySalesforce(SalesforceReportBrowser):
            OPTIONS = MySalesforceOptions
            CREDENTIAL_PREFIX = "salesforce_temp"

        with MySalesforce() as sf:
            sf.ensure_login()              # 推奨。1行でログインまで完結
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
        ブラウザで残りの確認を終えると自動で検知して return する。

        ログイン済みの判定や未登録時の扱いまで含めたいなら ``ensure_login()``
        を使うこと。

        Args:
            prefix: DPAPIに登録した認証情報のシステム名
                （``comken.toolbox.credentials.Credentials`` のサイト名）。
                ``username`` / ``password`` の2項目を登録しておく
                （例: ``python -m comken cred gui``）。**省略時はクラスの
                ``CREDENTIAL_PREFIX``** を使う（本番とテストを切り替えるときだけ渡す）。

        Raises:
            CredentialNotFoundError: prefix配下に username/password が未登録の場合。
            CredentialError: 別のユーザー・PCで登録されていて復号できない場合。
        """
        from comken.toolbox.credentials import Credentials

        prefix = prefix or self.CREDENTIAL_PREFIX
        logger.info("DPAPIの認証情報でログインを試みます: prefix=%s", prefix)
        cred = Credentials(prefix)
        login_page = self.go_login()
        login_page.login(cred.username, cred.password)

    def ensure_login(
        self,
        prefix: str = "",
        timeout: float = _DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS,
        interval: float = _DEFAULT_MANUAL_LOGIN_INTERVAL_SECONDS,
    ) -> None:
        """ログイン画面を開き、ID/パスワードを自動入力したうえで MFA の承認を待つ。

        推奨のログイン方法。次の順で動く:

        1. ``go_login()`` でログイン画面を開く
        2. 既にログイン済み（``_is_logged_in(driver)`` が真）なら、認証情報を
           読まずに何もせず return する
        3. 未ログインなら ``Credentials(prefix or self.CREDENTIAL_PREFIX)`` から
           ``username`` / ``password`` を取り出し、``LoginPage.login()`` で
           入力して送信する
        4. ``wait_for_manual_login(timeout, interval)`` を呼ぶ

        DPAPI の認証情報が未登録（``CredentialNotFoundError``）や、別の
        ユーザー・PC で登録されていて復号できない（``CredentialError``）
        場合は**止めずに** WARNING をログへ出し、ID/パスワードの自動入力は
        スキップして ``wait_for_manual_login()`` へ進む。人が Edge で
        ID/パスワードから手入力する「今までの手動ログインと同じ動き」に
        なるため。WARNING には ``python -m comken cred gui`` で
        ``<prefix>`` に ``username`` / ``password`` を登録すれば自動入力に
        切り替わる旨を書く。**パスワードはログに出さない。**

        Args:
            prefix: DPAPIに登録した認証情報のシステム名。**省略時はクラスの
                ``CREDENTIAL_PREFIX``** を使う。
            timeout: ``wait_for_manual_login()`` に渡す最大待ち秒数。既定10分。
            interval: ``wait_for_manual_login()`` に渡す確認間隔（秒）。既定3秒。
        """
        from comken.exceptions import CredentialError
        from comken.toolbox.credentials import Credentials

        login_page = self.go_login()
        session = self._require_session()
        driver = session.raw

        if _is_logged_in(driver):
            logger.debug(
                "Salesforce は既にログイン済みのため ID/パスワードは入力しません: url=%s",
                driver.current_url,
            )
            return

        prefix = prefix or self.CREDENTIAL_PREFIX
        try:
            cred = Credentials(prefix)
            username, password = cred.username, cred.password
        except CredentialError as error:
            logger.warning(
                "Salesforce のID/パスワードをDPAPIから取得できなかったため、"
                "ID/パスワードは自動入力しません。"
                "表示中の Edge でID/パスワードから手入力してください（手動ログインと同じ動き）。"
                "自動入力に切り替えるには `python -m comken cred gui` を実行し、"
                "サイト名「%s」に username と password を登録してください: %s",
                prefix,
                error,
            )
            self.wait_for_manual_login(timeout=timeout, interval=interval)
            return

        logger.info(
            "Salesforce のIDとパスワードを自動入力しました。"
            "続けて MFA を承認してください（スマホ）。"
            "Edge 側の操作が終わると自動で検知して処理を続行します: prefix=%s",
            prefix,
        )
        login_page.login(username, password)
        self.wait_for_manual_login(timeout=timeout, interval=interval)

    def wait_for_manual_login(
        self,
        timeout: float = _DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS,
        interval: float = _DEFAULT_MANUAL_LOGIN_INTERVAL_SECONDS,
    ) -> None:
        """ブラウザでの手動ログインが終わるまで、ブラウザを定期的にポーリングして待つ。

        ``go_login()`` の直後（``BASE_URL`` のログイン画面を開いた直後）に呼ぶ。
        すでにログイン済み（ログイン画面の入力欄 ``id="username"`` が無く、URL が
        Lightning のホーム ``/lightning/...`` または Classic のホーム
        ``/home/home.jsp``）なら、**待たずにすぐ return する**。

        まだログインしていなければ ``interval`` 秒おきにブラウザ状態を確認し、
        ログイン済みになった時点で ``logger.info`` を出して return する。人が
        ターミナルで Enter を押す必要はない（無人の定期実行からも安全に呼べる）。

        ``timeout`` 秒を過ぎてもログインが確認できなかった場合は
        ``LoginFailedError`` を送出する。

        ``OPTIONS.HEADLESS`` が ``True`` のときは人がログインできないので、
        ログインが切れた瞬間に待たずに ``BrowserError`` を送出する
        （ただし呼び出し時点でログイン済みなら、HEADLESS でもそのまま return する）。

        .. note::
           ログイン済み判定は Salesforce の一般的な動き（ログイン後に
           ``/lightning/`` のホームへ遷移する）に基づく**推測**で、実際の組織で
           完全に正しいことは未確認。MFA・パスワード変更の途中画面
           （``/_ui/identity/verification/...`` など）は「まだ」と判定される
           （仕様の想定通り）。組織固有の動きがある場合は ``_is_logged_in()`` を
           拡張すること。

        Args:
            timeout: 待機の最大秒数。既定10分
                （``_DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS``）。
            interval: ブラウザ状態の確認間隔（秒）。既定3秒
                （``_DEFAULT_MANUAL_LOGIN_INTERVAL_SECONDS``）。

        Raises:
            LoginFailedError: ``timeout`` 秒待ってもログイン済みにならなかった場合。
            BrowserError: HEADLESS で起動中、かつログインが切れていた場合
                （人がブラウザを操作できないため、待たずにエラー）。
            WebDriverException: ブラウザが閉じられた・一時的に操作不能になった
                場合（そのまま例外を上げる）。
        """
        session = self._require_session()
        driver = session.raw

        if _is_logged_in(driver):
            logger.debug("Salesforce はログイン済みです: url=%s", driver.current_url)
            return

        # HEADLESS だとブラウザ画面が見えず人がログインできないので、待たずにエラー
        headless = bool(self.OPTIONS.HEADLESS) if self.OPTIONS else False
        if headless:
            raise BrowserError(
                "Salesforce のログインが切れていますが、HEADLESS で起動中のため"
                "人手でログインできません。\n"
                "対処: OPTIONS.HEADLESS を False にして（既定値）起動してから"
                "再度実行してください。"
            )

        timeout_minutes = max(1, int(timeout // 60))
        logger.warning(
            "Salesforce のログインが切れています。"
            "表示中の Edge でログイン、または MFA の承認をしてください。"
            "最大 %d 分待ちます: url=%s",
            timeout_minutes,
            driver.current_url,
        )

        started = _monotonic()
        deadline = started + timeout
        while True:
            _sleep(interval)
            if _is_logged_in(driver):
                elapsed = int(_monotonic() - started)
                logger.info("手動ログインを確認しました（%d 秒）", elapsed)
                return
            if _monotonic() >= deadline:
                raise LoginFailedError(
                    f"{timeout_minutes} 分待ちましたがログインが確認できませんでした: "
                    f"url={driver.current_url}\n"
                    "対処: Edge でログインしてから、もう一度実行してください。"
                )

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
                セッションが切れて ``SalesforceError`` になることが
                ある。その暫定対処として指定する（恒久対処ではない。根本的には
                Salesforce管理者にセッションタイムアウトの設定を確認してもらうのが筋）。
            keep_alive_interval: ``keep_alive_report_id`` を開く間隔（秒）。既定300秒（5分）。

        Yields:
            (report_id, 保存したファイルのパス) のタプル。
            **完了した順**に返るため、``reports`` の順序とは限らない。

        CSV の場合、Salesforce の画面エクスポートはデータ末尾に空行を挟んだ
        フッター（著作権・機密情報表示など）を付けるため、**保存前に最初の
        空行以降を取り除いてから保存する**。``export_format`` が ``"csv"`` 以外の
        ときは中身を変えない。

        Raises:
            BrowserError: 未起動の場合。
            SalesforceError: URLからレポートIDを取り出せない場合、または
                いずれかのレポートでエクスポートが失敗した場合（ログイン未実行・セッション切れ等）。
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
                    if export_format == "csv":
                        content = _strip_report_footer(content, encoding)
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
            raise BrowserError(
                f"{self.__class__.__name__} はまだ起動していません。"
                f"`with {self.__class__.__name__}() as site:` の中で使ってください。"
                "\n対処: `with SiteBase() as site:` の中で使ってください"
                "（ブラウザは起動していないので実害はない）。"
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


def _is_logged_in(driver: Any) -> bool:
    """現在のブラウザ状態が「Salesforce にログイン済み」かを判定する。

    判定基準:
        - ログイン画面の入力欄 ``LoginPage.USERNAME``（``id="username"``）が**無い**
          （ログイン画面そのものでは無い）
        - **かつ** 現在 URL のパスが ``/lightning/`` で始まる、または
          ``/home/home.jsp`` を含む（Lightning / Classic のホーム）

    どちらか一方でも欠ければ「まだ」と判定する。MFA・パスワード変更の途中画面
    （``/_ui/identity/verification/...`` など）はパスが上の条件に当てはまらない
    ため「まだ」と判定される（想定通り）。

    .. note::
       Salesforce の一般的な動き（ログイン済みで ``BASE_URL`` を開くと Lightning の
       ホーム ``/lightning/`` へ移る）に基づく**推測**で、実際の組織で完全に正しい
       ことは未確認。組織固有の動き（独自ドメインへのリダイレクト、別のログイン
       後パスなど）がある場合は、ここを拡張すること。
    """
    # find_elements は要素が無いと空リストを返す（NoSuchElementException は出ない）。
    # 入力欄が見えていれば、まだログイン画面（あるいはその残骸）
    if driver.find_elements(*LoginPage.USERNAME):
        return False
    current_url = driver.current_url
    path = urlsplit(current_url).path
    return path.startswith("/lightning/") or "/home/home.jsp" in current_url


def _cookies_to_requests_session(driver_cookies: list[dict[str, Any]]) -> requests.Session:
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
        raise _report_export_error(report_id, response.status_code, content_type)
    logger.debug(
        "レポートのエクスポートに成功しました: report_id=%s bytes=%d",
        report_id,
        len(response.content),
    )
    return report_id, response.content


def _strip_report_footer(content: bytes, encoding: str) -> bytes:
    """Salesforce の画面CSV書き出しの末尾フッター（最初の空行以降）を取り除く。

    Salesforce の ``?export=1&xf=csv`` の出力は、データ末尾に空行を挟んで
    著作権表示・機密情報表示・作成者と日時・会社名などの1列だけの行を付ける。
    comken の ``CSV`` でそのまま読むとフッター行の列数が見出しと合わずに
    ``CSVError`` で止まるため、保存前にここで取り除く。

    Excel 形式（``export_format="xls"`` など）は中身を変更しないので、この関数は
    CSV のときだけ ``export_reports()`` から呼ばれる。

    ルール:

    - データ末尾の「**引用符の外にある最初の空行**」から後ろを全部削る
      （``""`` は引用符の中の ``"`` 1文字として扱う）
    - 空行 = 空白以外の文字が無い行。``\\r\\n`` / ``\\n`` どちらでも扱う
    - ヘッダを含めて1行以上のデータ行を見ていない場合は空行を
      フッター扱いしない（ヘッダ無しCSVをそのまま通す）
    - 残す部分は1バイトも変えない。``normalize_encoding`` で codec 名に
      そろえてから decode し、同じ codec で encode する
    - decode に失敗した場合は **何も削らずそのまま返す**（warning を出して取得は止めない）

    Args:
        content: HTTP 応答の生バイト列。
        encoding: ``export_reports()`` の ``encoding`` 引数の値（既定 ``"Shift_JIS"``）。

    Returns:
        フッターを取り除いたバイト列。フッターが無い、または decode に失敗した
        場合は ``content`` をそのまま返す（呼び出し側の ``write_bytes`` が保存する）。
    """
    try:
        codec = normalize_encoding(encoding)
    except ValueError:
        logger.warning(
            "Salesforce レポートCSVのフッターを取り除くために encoding を正規化できません: %r。"
            " 元のまま保存します。",
            encoding,
        )
        return content

    try:
        text = content.decode(codec)
    except (UnicodeDecodeError, LookupError) as error:
        logger.warning(
            "Salesforce レポートCSVのデコードに失敗したためフッターを取り除きません "
            "(encoding=%r)。元のまま保存します: %s",
            codec,
            error,
        )
        return content

    cut_at = _find_footer_start(text)
    if cut_at is None:
        return content

    first_line = text.split("\n", 1)[0] if "\n" in text else text
    removed_text = text[cut_at:]
    removed_lines = removed_text.count("\n")
    stripped_bytes = text[:cut_at].encode(codec)
    logger.debug(
        "Salesforce レポートCSVのフッターを取り除きました: 先頭行=%r 削除行数=%d",
        first_line,
        removed_lines,
    )
    return stripped_bytes


def _find_footer_start(text: str) -> int | None:
    """CSV の本文中、引用符の外側で空白のみの最初の行の開始位置（文字インデックス）を返す。

    「データ行を1行以上見た後にある最初の空行」を探す。空行は無視できる
    引用符の外にある空白のみの行とする。``""`` は引用符の中の ``"`` 1文字として
    扱い、引用符の中にある改行や空行は区切りと見なさない。

    ヘッダを含めて1行以上のデータ行を見ていない場合は ``None`` を返す
    （ヘッダ無しCSVを空のまま通す）。

    Args:
        text: CSV のデコード済み文字列。

    Returns:
        フッター開始位置の文字インデックス。見つからなければ ``None``。
    """
    in_quotes = False
    line_start = 0
    seen_non_blank_line = False
    n = len(text)
    pos = 0
    while pos < n:
        c = text[pos]
        if c == '"':
            # 引用符の中の "" はリテラルの " 一文字として扱う
            if in_quotes and pos + 1 < n and text[pos + 1] == '"':
                pos += 2
                continue
            in_quotes = not in_quotes
            pos += 1
            continue
        if c == "\n" and not in_quotes:
            line = text[line_start:pos]
            # \r\n の \r を取り除き、両端の空白を判定用に外す
            line_content = line.rstrip("\r").strip()
            if line_content:
                seen_non_blank_line = True
            elif seen_non_blank_line:
                # 空行で、データ行を既に1行以上見ている。
                # 後ろにもう1行以上あるなら、フッター開始とみなす。
                rest = text[pos + 1 :]
                if rest.strip():
                    return line_start
            line_start = pos + 1
        pos += 1
    return None
