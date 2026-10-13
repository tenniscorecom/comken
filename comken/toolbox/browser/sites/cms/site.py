"""comken/toolbox/browser/sites/cms/site.py — CMS 用の SiteBase クラス。

このサイトのものは sites/cms/ の中で完結する（site.py・pages/）。
サイトを増やすときは sites/<サイト名>/ をもう1つ作る。

1サイトにつき ``CMS`` と ``CMSBrowserOptions`` を **同じ ``site.py`` に置く**
（``〇〇Site`` と ``〇〇SiteOptions`` は必ずセットで、フォルダが同じなら
ファイルを分ける理由が無い）。ブラウザ設定は config.ini ではなくこのファイル
（サイト側の Python）に書き、設定できる項目は ``print(CMSBrowserOptions())``
で一覧できる。

1サイト＝1フォルダで、起動オプション・ダウンロード先・ログイン状態はサイトごとに独立する
（片方の設定がもう片方へ影響しない）。

行ける画面は `go_〇〇()` で書き、コードがそのまま遷移図になるようにする
（書き方の正本は docs/機能/browser.md）。

> [!note] 雛形の値
> BASE_URL は RFC 2606 の例示ドメイン（example.com、実在しない）を使った
> ダミー値。セレクタも example の値のまま。利用プロジェクト側で実際の値へ
> 書き換える前提。
"""

# 遷移先の import を型注釈だけ TYPE_CHECKING、実行時はメソッド内に分けているのは、
# 画面クラス同士の循環importを避けるため（循環の有無に関わらず一律この形にする）
from __future__ import annotations

from typing import TYPE_CHECKING

from comken.toolbox.browser import BrowserOptions, SiteBase

if TYPE_CHECKING:
    from comken.toolbox.browser.sites.cms.pages.login_page import LoginPage
    from comken.toolbox.browser.sites.cms.pages.top_page import TopPage


class CMSBrowserOptions(BrowserOptions):
    """cms 用のブラウザオプション。

    デフォルト（BrowserOptions）から変更したいものだけ上書きする。
    全オプションのデフォルト値は comken/toolbox/browser/options.py を参照。
    """

    # 利用プロジェクト側で実情に合わせて書き換える想定。雛形では既定のままにしておく


class CMS(SiteBase):
    """cms 雛形用の SiteBase。

    URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
    """

    NAME = "cms"
    BASE_URL = "https://cms.example.com"
    OPTIONS = CMSBrowserOptions
    OWNER = "comken"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。"""
        from comken.toolbox.browser.sites.cms.pages.login_page import LoginPage

        return self.to(LoginPage).go("/login")

    def go_top(self) -> TopPage:
        """ログイン後の最初の画面（トップ画面）を開く。

        セッションがログイン済み前提。ログイン前なら ``go_login()`` から
        ``LoginPage.login()`` を経由して ``TopPage`` へ辿る形が基本。
        """
        from comken.toolbox.browser.sites.cms.pages.top_page import TopPage

        return self.to(TopPage).go("/top")
