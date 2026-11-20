"""comken/toolbox/browser/sites/box/pages/file_page.py — Box のファイル詳細画面。

``/file/{id}`` の画面。ダウンロードボタンからファイルをダウンロードし、
保存先のパスを返す。
"""

from __future__ import annotations

import logging
from pathlib import Path

from comken.exceptions import BrowserError
from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.box.pages.app_page import AppPage

logger = logging.getLogger(__name__)


def _download_not_finished_error() -> BrowserError:
    """``BrowserError`` の「ダウンロードが完了したファイルが無い」文言。"""
    return BrowserError(
        "ダウンロードが完了したファイルが見つかりません。\n"
        "次を確認してください:\n"
        "  1. ダウンロードが実際に始まっているか（画面のエラー表示）\n"
        "  2. ブラウザの保存先がこのセッションのダウンロードフォルダか\n"
        "\n対処: もう一度実行してください。"
    )


class FilePage(AppPage):
    """Box のファイル詳細画面（/file/{id}）。"""

    PATH = "/file"

    # ── セレクター ──
    # ダウンロードボタン。画面（一覧／詳細）によって属性が違うため、
    # 候補を順番に試す。data-testid / data-resin-target は表示文字列に
    # 依存しないので、日本語UIでもそのまま使える。
    # 根拠: https://github.com/BlueMath-Warriors/clouddownloader の
    # src/clouddownloader/providers/box.py の _SELECTORS
    # （``button[aria-label="Download"]`` / ``button[data-testid="download-button"]``
    # / ``button[data-resin-target="bulkdownload"]``
    # / ``button[data-resin-target="download"]`` をこの順に試している）。
    DOWNLOAD_BTNS = (
        Locator.css("button[data-testid='download-button']"),
        Locator.css("button[data-resin-target='download']"),
        Locator.css("button[data-resin-target='bulkdownload']"),
        Locator.css("button[aria-label='Download']"),
    )

    def download(self) -> Path:
        """ファイルをダウンロードし、保存されたファイルのパスを返す。

        ダウンロードの完了待ちはセッションの ``download_dir.wait()`` で行う
        （``.crdownload`` が消えるまで待つ）。

        Returns:
            ダウンロード先（セッションのダウンロードフォルダ）に保存されたパス。

        Raises:
            BrowserError: ダウンロードが終わる前に時間切れになった場合。
            ElementNotFoundError: ダウンロードボタンが見つからない場合。
        """
        self._click_download_button()
        files = self.session.download_dir.wait()
        if not files:
            raise _download_not_finished_error()
        logger.info("ダウンロードが完了しました: 件数=%d", len(files))
        return files[0]

    def _click_download_button(self) -> None:
        """ダウンロードボタンを押す。

        ボタンの属性は画面によって違うため、候補を順番に試す。
        """
        for locator in self.DOWNLOAD_BTNS:
            if self.has_element(locator):
                self.click(locator)
                return
        # どれも見つからない。描画が遅れているだけなら、
        # 1番目の候補で要素待ちをしてから押す（見つからなければ
        # ElementNotFoundError になる）
        self.click(self.DOWNLOAD_BTNS[0])
