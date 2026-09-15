"""comken/toolbox/browser/sites/ouju/pages/csv_report_page.py — CSV帳票のダウンロード画面（雛形）

URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
"""

from __future__ import annotations

from pathlib import Path

from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.ouju.pages.app_page import AppPage


class CsvReportPage(AppPage):
    """CSV帳票のダウンロード画面（雛形）。

    ダウンロードしたCSVの列削減（新ロールで255列を超えてAccessへ入らない問題への
    対処）はここでは行わない。toolbox は services に依存できないため
    （下の層だけを import できる設計ルール）、削減込みで使いたい場合は
    comken.services.csv_column_reducer.download_and_reduce_ouju_csv() を使う。
    """

    PATH = "/report"
    DOWNLOAD_BTN = Locator.css("button.download-csv")

    def download_csv(self) -> Path:
        """CSVをダウンロードし、保存先パスを返す。

        1回のクリックで1ファイルだけ落ちる前提。複数落ちる画面では
        ``self.session.download_dir.wait()`` を直接使って書き換える。
        """
        self.click(self.DOWNLOAD_BTN)
        [downloaded_path] = self.session.download_dir.wait()
        return downloaded_path
