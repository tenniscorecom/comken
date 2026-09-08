"""comken/toolbox/browser/sites/ams_site/pages/app_page.py — ams_site 共通の SitePage

URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。

``BASE_URL`` はここでは書かない。``SitePage.BASE_URL`` が未設定のときは、
起動したサイトクラス（``AMSSite``）の ``BASE_URL`` へ自動でフォールバックする
（解決順は ``comken/toolbox/browser/page/site.py`` を参照）。同じ値を
``site.py`` とここの2箇所に書くと、書き換え忘れで食い違う事故につながる。
"""

from comken.toolbox.browser import SitePage


class AppPage(SitePage):
    """ams_site 共通の基底クラス。

    全画面クラスはこのクラスを継承する。
    サイト固有の共通処理（ヘッダー操作・共通エラーメッセージ取得等）をここに書く。
    """
