"""comken/toolbox/browser/page/site.py — SitePage — サイト共通の画面クラス。"""

from __future__ import annotations

from typing import Self

from comken.toolbox.browser.page.model import Page


class SitePage(Page):
    """1つのサイト共通の画面クラス。サイトごとにこれを継承する。

    BASE_URL とログインなど、そのサイトのどの画面でも使う処理をここに書く。
    画面ごとのクラスは、さらにこれを継承する:

        Page          … ブラウザ操作（click / input / select ...）
          └ SitePage  … サイト共通（BASE_URL / ログイン / 共通ヘッダー）
              └ LoginPage / HomePage / ...   … 各画面

    BASE_URL は次の順で解決する:
      1. 自身（または親クラス）に `BASE_URL` が定義されていればそれ
      2. 無ければ、`browsers.launch(SiteBase)` で起動した `SiteBase` の `BASE_URL`
    """

    BASE_URL: str = ""

    def go(self, path: str = "") -> Self:
        """BASE_URL からの相対パスへ移動し、自分自身を返す。

        Args:
            path: BASE_URL からの相対パス（例: "/login"）。省略時は BASE_URL を開く。
        """
        self.session.open(self._base_url + path)
        return self

    @property
    def _base_url(self) -> str:
        """画面クラス側の BASE_URL を、なければ SiteBase.BASE_URL から解決する。

        クラス変数の解決は Python の MRO に任せる（`type(self).BASE_URL` ではなく
        `self.__class__.BASE_URL` を使う）。SitePage 側で必ず定義する設計もあるが、
        それでは SiteBase クラスの BASE_URL を取りに行く経路が消えるため、ここでは
        「未設定なら上位 SiteBase を見る」形にしている。
        """
        if self.__class__.BASE_URL:
            return self.__class__.BASE_URL
        site = getattr(self.session, "_site", None)
        if site is not None:
            return site.BASE_URL
        return ""
