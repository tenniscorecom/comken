"""comken/toolbox/browser/page/navigation.py — 画面の移動（open / save_screenshot）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Self

from comken.toolbox.browser.page.base import _PageBase

logger = logging.getLogger(__name__)


class NavigationMixin(_PageBase):
    """画面の移動（open / save_screenshot）。"""

    def open(self, url: str) -> Self:
        """URL を開き、自分自身を返す。"""
        logger.debug("URL を開きます: url=%s session=%s", url, self.session.name)
        self.session.open(url)
        logger.debug("URL を開きました: url=%s session=%s", url, self.session.name)
        return self

    def save_screenshot(
        self,
        filename: str | None = None,
        *,
        directory: Path | str | None = None,
        prefix: str = "screenshot",
    ) -> Path:
        """今の画面を PNG で保存し、そのパスを返す。

        Args:
            filename: 保存するファイル名。省略時は {prefix}_{セッション名}_{日時}.png。
            directory: 保存先ディレクトリ。相対パスなら logs/ 配下のサブフォルダとして扱う
                （例: "errors" → logs/errors/）。絶対パスを渡せば logs/ の外にも保存できる。
                省略時は logs/。
            prefix: filename を省略したときのファイル名の先頭。
        """
        logger.debug(
            "スクリーンショットを保存します: filename=%s directory=%s prefix=%s session=%s",
            filename,
            directory,
            prefix,
            self.session.name,
        )
        path = self.session.save_screenshot(filename, directory=directory, prefix=prefix)
        logger.debug("スクリーンショットを保存しました: path=%s", path)
        return path
