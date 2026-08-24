"""comken/toolbox/browser/sites/ouju_site/pages/app_page.py — ouju_site 共通の SitePage

URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
"""

from comken.toolbox.browser import SitePage


class AppPage(SitePage):
    """ouju_site 共通の基底クラス。

    全画面クラスはこのクラスを継承する。
    サイト固有の共通処理（ヘッダー操作・共通エラーメッセージ取得等）をここに書く。
    """

    BASE_URL = "https://example.com"
