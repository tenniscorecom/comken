r"""comken/toolbox/salesforce/report_export.py — 画面のエクスポート機能でレポートをCSV取得する。

Reports and Dashboards REST API は2000行が上限（`docs/salesforce.md` の
「レポート — 2000行の壁」）。マトリックス／統合レポートなど SOQL に書き換えられない
形式で、1区間でも2000行を超える場合の最終手段として、画面のエクスポート機能を
HTTP で直接叩く。

frontdoor.jsp で OAuth アクセストークンをセッション Cookie に変換するだけなので、
実ブラウザ（Selenium）を起動する必要がない。requests + ThreadPoolExecutor で並列化する。

**セッションセキュリティレベル次第では、この経路が組織のポリシーで弾かれることがある**
（frontdoor.jsp 由来のセッションが「標準」扱いになり、エクスポートのような操作に
「高保証」を要求される場合）。弾かれた場合は
`comken.toolbox.browser.sites.salesforce.Salesforce`（実ブラウザ経由）を使う。
両者は「レポートURLを渡すと (report_id, 保存先パス) を順に返す」という同じ形の
インタフェースにしてあるので、どちらか一方が通らなくても呼び出し側の書き換えは
最小で済む。

    from comken.toolbox.salesforce.sites import Solution
    from comken.toolbox.salesforce.report_export import ReportExporter

    with Solution() as sf:
        exporter = ReportExporter(sf)
        for report_id, path in exporter.export_reports(report_urls, "出力先"):
            print(report_id, path)
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import requests

from comken.exceptions import SalesforceReportExportError
from comken.toolbox.salesforce.report import report_id_from_url

if TYPE_CHECKING:
    from comken.toolbox.salesforce.client import SalesforceBase

logger = logging.getLogger(__name__)

# export_reports() で同時に走らせるリクエストの既定数
_DEFAULT_MAX_WORKERS = 10

# 1リクエストあたりのタイムアウト秒数。集計系レポートは重いことがある
_DEFAULT_TIMEOUT_SECONDS = 120


class ReportExporter:
    """frontdoor.jsp + 画面エクスポートで、レポートをCSV/XLS取得する。

    ``SalesforceBase``（``Solution`` などの組織クラス）の access_token / instance_url を
    そのまま引き継いでログインする。ID/パスワードもMFAも不要。
    """

    def __init__(self, sf: SalesforceBase) -> None:
        """組織クラスの認証情報を引き継いで、エクスポート用のセッションを確立する。

        Args:
            sf: 認証済みの組織クラス（``with Solution() as sf:`` の中で渡す）。

        Raises:
            requests.exceptions.RequestException: frontdoor.jsp への接続に失敗した場合。
        """
        parts = urlsplit(sf.instance_url)
        self._domain = f"{parts.scheme}://{parts.netloc}"
        self._session = requests.Session()
        self._session.get(
            f"{self._domain}/secur/frontdoor.jsp",
            params={"sid": sf.access_token},
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )

    def export(self, report_url: str, *, export_format: str = "csv") -> bytes:
        """レポート1件をエクスポートし、ファイルの中身（bytes）を返す。

        Args:
            report_url: レポート画面のURL（またはレポートID）。
            export_format: "csv" または "xls"。

        Returns:
            エクスポートされたファイルの中身。

        Raises:
            SalesforceReportIDNotFoundError: URLからレポートIDを取り出せない場合。
            SalesforceReportExportError: レスポンスがCSV/XLSでなかった場合
                （ログイン画面・権限エラー・セッションセキュリティレベル不足など）。
        """
        report_id = report_id_from_url(report_url)
        response = self._session.get(
            f"{self._domain}/{report_id}",
            params={"isdtp": "p1", "export": "1", "enc": "UTF-8", "xf": export_format},
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )
        content_type = response.headers.get("Content-Type", "")
        disposition = response.headers.get("Content-Disposition", "")
        looks_like_export = (
            "attachment" in disposition.lower() or export_format in content_type.lower()
        )
        if response.status_code != requests.codes.ok or not looks_like_export:
            raise SalesforceReportExportError(report_id, response.status_code, content_type)
        return response.content

    def export_reports(
        self,
        report_urls: Sequence[str],
        directory: str | Path,
        *,
        export_format: str = "csv",
        max_workers: int = _DEFAULT_MAX_WORKERS,
    ) -> Iterator[tuple[str, Path]]:
        """レポートURLを渡すと、並列にダウンロードして (report_id, 保存先パス) を順に返す。

        ``comken.toolbox.browser.sites.salesforce.Salesforce.download_reports()`` と
        同じ形のインタフェース。読み込み待ちがブラウザのタブ数で決まる向こうと違い、
        こちらはHTTPリクエストを直接並列に投げるだけなので ``max_workers`` を
        増やしてもタブのようなメモリ負荷は増えない（サイト側の負荷には注意する）。

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
            SalesforceReportIDNotFoundError: URLからレポートIDを取り出せない場合。
            SalesforceReportExportError: いずれかのレポートでエクスポートが失敗した場合。
        """
        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.export, url, export_format=export_format): url
                for url in report_urls
            }
            for future in as_completed(futures):
                report_id = report_id_from_url(futures[future])
                path = target_dir / f"{report_id}.{export_format}"
                path.write_bytes(future.result())
                logger.info("レポートをダウンロードしました: report_id=%s path=%s", report_id, path)
                yield report_id, path
