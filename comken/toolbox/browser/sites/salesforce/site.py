r"""comken/toolbox/browser/sites/salesforce/site.py — Salesforceレポートのブラウザダウンロード。

レポートIDの抽出は comken.toolbox.salesforce.report.report_id_from_url() をそのまま使う
（toolbox.browser → toolbox.salesforce は tests/test_layers.py の ALLOWED_SAME_LAYER で
許可済み）。

ダウンロード方法は2通り:

- ``download_reports()`` — タブ（load_many）だけで完結する。組織のセッション
  ポリシーに関わらず確実に通る
- ``export_reports()`` — ``login_with_token()`` で確立したブラウザのセッション
  Cookieを requests へ引き継ぎ、実際のN件のダウンロードは requests +
  ThreadPoolExecutor で並列に行う。**速いのでこちらを先に試す。**
  requests だけで frontdoor.jsp ログインを試みるとログイン画面へ
  リダイレクトされて通らない組織があることを確認済み（セッションセキュリティ
  レベル等）のため、認証だけは実ブラウザで確立している

> [!warning] URL は仮の値
> **このリポジトリは公開しているので、実際の組織の URL を書かない。**
> `BASE_URL` はダミーで、共有サーバーへ配置するときに実際の値へ書き換える
> （`comken/toolbox/salesforce/sites/` の `Solution` と同じ扱い）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import requests

from comken.exceptions import SalesforceReportExportError, SiteNotStartedError
from comken.toolbox.browser import BrowserOptions, SiteBase
from comken.toolbox.browser.locator import Locator
from comken.toolbox.salesforce.report import report_id_from_url

if TYPE_CHECKING:
    from comken.toolbox.browser.management import BrowserSession

logger = logging.getLogger(__name__)

# load_many() で同時に開いておくタブの既定数
_DEFAULT_MAX_OPEN_TABS = 10

# レポート1件あたりのダウンロード完了待ちの既定秒数。集計系レポートは重いことがある
_DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 300

# export_reports() で同時に投げるHTTPリクエストの既定数
_DEFAULT_MAX_WORKERS = 10


class SalesforceBrowserOptions(BrowserOptions):
    """salesforce 用のブラウザオプション。

    デフォルト（BrowserOptions）から変更したいものだけ上書きする。
    レポートの読み込みが重いことがあるため、待機秒数を既定より長めにする。
    """

    WAIT_SECONDS = 180


class Salesforce(SiteBase):
    """Salesforceのレポートをブラウザ経由でCSVダウンロードするための雛形。

    URL や認証は example の値のまま。利用プロジェクト側で継承して書き換える
    （BASE_URL を実際の組織の My Domain URL へ）。

    ID/パスワードでのログイン画面は使わない。comken.toolbox.salesforce で取得した
    OAuthアクセストークンを ``login_with_token()`` に渡すだけで、
    frontdoor.jsp 経由でブラウザのログイン状態を確立する（MFAの二度手間が無い）。
    """

    NAME = "salesforce"
    BASE_URL = "https://example.my.salesforce.com"
    OPTIONS = SalesforceBrowserOptions
    OWNER = "comken"

    def login_with_token(self, access_token: str, instance_url: str | None = None) -> None:
        """OAuthアクセストークンでブラウザのログイン状態を確立する（frontdoor.jsp）。

        Args:
            access_token: comken.toolbox.salesforce 側で取得したOAuthアクセストークン
                （Salesforceのセッションidを兼ねる）。
            instance_url: 組織のインスタンスURL。省略時は BASE_URL を使う。
        """
        domain = (instance_url or self.BASE_URL).rstrip("/")
        self._require_session().open(f"{domain}/secur/frontdoor.jsp?sid={access_token}")

    def download_reports(
        self,
        report_urls: Sequence[str],
        *,
        ready: Locator | None = None,
        max_open: int = _DEFAULT_MAX_OPEN_TABS,
        page_timeout: int | None = None,
        download_timeout: int = _DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
        export_format: str = "csv",
    ) -> Iterator[tuple[str, Path]]:
        """レポートURLを渡すと、順に (report_id, ダウンロードしたファイルのパス) を返す。

        レポートの読み込みが重いことを前提に、``load_many()`` で複数タブを同時に
        開いておき、読み込みが終わったものから順にエクスポートしてダウンロードする。

        **読み込み待ちは並列、ダウンロードのトリガーは1件ずつ。** Salesforceの
        エクスポートはファイル名がレポート名で決まりIDでは決まらないため、複数の
        ダウンロードを同時に走らせると「どのファイルがどのレポートか」を取り違える。
        読み込みの終わったタブから順にこのメソッドが1件ずつ処理するので、
        ダウンロードが同時に複数走ることはない。

            with Salesforce() as sf:
                sf.login_with_token(access_token, instance_url)
                for report_id, path in sf.download_reports(report_urls, ready=MY_READY_LOCATOR):
                    move_to_project_folder(report_id, path)

        Args:
            report_urls: レポート画面のURL（またはレポートID）のリスト。
            ready: レポートの読み込み完了とみなす目印の要素。**省略せず渡すことを
                強く推奨する。** LightningはページのHTMLを描いてから中身を
                後入れするため、省略時（HTMLの読み込み完了で判断）だと表が
                まだ空でも「読み込み完了」とみなしてしまう。組織・Salesforceの
                バージョンでDOMが変わるため、comken側では固定値を持たない。
            max_open: 同時に開いておくタブの数。既定10。
            page_timeout: レポート1件あたりの読み込み待ちの上限秒数。省略時はセッションの設定
                （SalesforceBrowserOptions.WAIT_SECONDS）。
            download_timeout: ダウンロード完了待ちの上限秒数。既定300秒。
            export_format: "csv" または "xls"。

        Yields:
            (report_id, ダウンロードしたファイルのパス) のタプル。ファイルは
            download_dir 直下に "{report_id}.{export_format}" として保存される
            （Salesforceがレポート名で付けた元のファイル名から、この場でリネームする）。

        Raises:
            SalesforceReportIDNotFoundError: URLからレポートIDを取り出せない場合。
            DownloadTimeoutError: download_timeout 秒以内にダウンロードが完了しなかった場合。
        """
        session = self._require_session()
        for url in session.load_many(
            list(report_urls), ready=ready, max_open=max_open, timeout=page_timeout
        ):
            report_id = report_id_from_url(url)
            export_url = _build_export_url(session.current_url, report_id, export_format)
            session.open(export_url)
            downloaded = self.downloads.wait(timeout=download_timeout)
            renamed = _rename_to_report_id(
                downloaded, self.downloads.path, report_id, export_format
            )
            # wait() は作成時点のファイルしか除外しないため、リネーム後のパスを
            # 「既知」として伝えておかないと、次の1件の wait() がこれを
            # 誤って新しいダウンロードとして検出する
            self.downloads.mark_known(*downloaded, renamed)
            logger.info("レポートをダウンロードしました: report_id=%s path=%s", report_id, renamed)
            yield report_id, renamed

    def export_reports(
        self,
        report_urls: Sequence[str],
        directory: str | Path,
        *,
        export_format: str = "csv",
        max_workers: int = _DEFAULT_MAX_WORKERS,
    ) -> Iterator[tuple[str, Path]]:
        """``login_with_token()`` 済みのセッションCookieを requests へ引き継ぎ、
        並列にダウンロードして (report_id, 保存先パス) を返す。

        ``download_reports()`` はタブの読み込み・切り替えが挟まるため、実際の
        ダウンロードは1件ずつしか進まない。このメソッドはブラウザを認証の確立
        （``login_with_token()``）だけに使い、N件のダウンロード自体は
        requests + ThreadPoolExecutor で並列に行うため、はるかに速い。

        **requests だけで frontdoor.jsp ログインを試みるとログイン画面へ
        リダイレクトされ、通らない組織があることを確認済み**（セッション
        セキュリティレベル等）。実ブラウザで確立したセッションCookieを使うことで、
        この制約を避けている。

            with Salesforce() as sf:
                sf.login_with_token(access_token, instance_url)
                for report_id, path in sf.export_reports(report_urls, "出力先"):
                    ...

        Args:
            report_urls: レポート画面のURL（またはレポートID）のリスト。
            directory: 保存先ディレクトリ。無ければ作成する。
            export_format: "csv" または "xls"。
            max_workers: 同時に投げるリクエストの数。既定10。

        Yields:
            (report_id, ダウンロードしたファイルのパス) のタプル。ファイルは
            ``directory`` 直下に ``{report_id}.{export_format}`` として保存される。
            **完了した順**に返るため、``report_urls`` の順序とは限らない。

        Raises:
            SiteNotStartedError: 未起動、または ``login_with_token()`` を呼ぶ前の場合。
            SalesforceReportIDNotFoundError: URLからレポートIDを取り出せない場合。
            SalesforceReportExportError: いずれかのレポートでエクスポートが失敗した場合
                （``login_with_token()`` 未実行・セッション切れ等）。
        """
        session = self._require_session()
        domain = _domain_of(session.current_url)
        http_session = _cookies_to_requests_session(session.raw.get_cookies())

        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_export_via_http, http_session, domain, url, export_format): url
                for url in report_urls
            }
            for future in as_completed(futures):
                report_id, content = future.result()
                path = target_dir / f"{report_id}.{export_format}"
                path.write_bytes(content)
                logger.info("レポートをダウンロードしました: report_id=%s path=%s", report_id, path)
                yield report_id, path

    def _require_session(self) -> BrowserSession:
        """起動済みの BrowserSession を返す。未起動なら理由を示して落とす。"""
        if self.session is None:
            raise SiteNotStartedError(self.__class__)
        return self.session


def _domain_of(url: str) -> str:
    """URL から scheme + netloc だけを取り出す（例: https://example.my.salesforce.com）。"""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _build_export_url(current_url: str, report_id: str, export_format: str) -> str:
    """今のタブのドメインを使って、レポートのエクスポートURLを組み立てる。

    ``?export=1&enc=UTF-8&xf=csv`` を付けたURLへ遷移すると、画面を描かずに
    ブラウザが直接CSVをダウンロードする（クラシックUI時代からある仕組みで、
    Lightningのドメインからでもそのまま使える）。
    """
    return f"{_domain_of(current_url)}/{report_id}?isdtp=p1&export=1&enc=UTF-8&xf={export_format}"


def _cookies_to_requests_session(driver_cookies: list[dict]) -> requests.Session:
    """Seleniumの driver.get_cookies() を requests.Session の Cookie へ移す。

    login_with_token() で実ブラウザが確立したセッションを、requests 側でも
    そのまま使えるようにする。
    """
    http_session = requests.Session()
    for cookie in driver_cookies:
        http_session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain", ""))
    return http_session


def _export_via_http(
    http_session: requests.Session, domain: str, report_url: str, export_format: str
) -> tuple[str, bytes]:
    """1件のレポートをHTTPで直接エクスポートする（export_reports() の並列実行単位）。"""
    report_id = report_id_from_url(report_url)
    response = http_session.get(
        f"{domain}/{report_id}",
        params={"isdtp": "p1", "export": "1", "enc": "UTF-8", "xf": export_format},
        timeout=_DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
    )
    content_type = response.headers.get("Content-Type", "")
    disposition = response.headers.get("Content-Disposition", "")
    looks_like_export = "attachment" in disposition.lower() or export_format in content_type.lower()
    if response.status_code != requests.codes.ok or not looks_like_export:
        raise SalesforceReportExportError(report_id, response.status_code, content_type)
    return report_id, response.content


def _rename_to_report_id(
    downloaded: list[Path], directory: Path, report_id: str, export_format: str
) -> Path:
    """download_dir.wait() が返した最新のファイルを report_id ベースの名前へ変える。

    Salesforceが付けるファイル名はレポート名でありIDではないため、呼び出し側が
    「どのレポートのファイルか」を確実に分かるようにリネームする。
    """
    latest = downloaded[-1]
    target = directory / f"{report_id}.{export_format}"
    if target.exists():
        target.unlink()
    latest.rename(target)
    return target
