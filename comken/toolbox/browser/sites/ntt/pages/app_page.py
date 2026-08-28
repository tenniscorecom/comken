"""comken/toolbox/browser/sites/ntt/pages/app_page.py — NTT西/NTT東 共通の SitePage

NTT西・NTT東はドメイン（BASE_URL）だけが違う姉妹サイトのため、``BASE_URL`` を
ここで固定せず、起動したサイトクラス（``NTTNishi`` / ``NTTHigashi``）の
``BASE_URL`` へ委ねる（``Page.BASE_URL`` の解決順は
``comken/toolbox/browser/page.py`` を参照）。1サイトだけの画面共通クラス
（例: ``sites/sample/pages/app_page.py``）と違い、ここで ``BASE_URL`` を
書くと片方のサイトでしか動かなくなる点に注意。
"""

from comken.toolbox.browser import Locator, SitePage


class AppPage(SitePage):
    """NTT西・NTT東で共通の基底クラス。全画面クラスはこのクラスを継承する。

    サイト固有の共通処理（ヘッダー操作・共通エラーメッセージ取得等）をここに書く。
    """

    ERROR_MESSAGE = Locator.css(".error")

    def error_message(self) -> str:
        """画面上部のエラー表示を返す。"""
        return self.read_text(self.ERROR_MESSAGE)
