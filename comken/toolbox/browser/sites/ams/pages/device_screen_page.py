"""comken/toolbox/browser/sites/ams/pages/device_screen_page.py — 装置の画面（雛形）

URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
"""

from comken.toolbox.browser.sites.ams.pages.app_page import AppPage


class DeviceScreenPage(AppPage):
    """お客様に紐づく装置の画面（雛形）。

    画面のスクリーンショットは Page 共通の ``save_screenshot()`` をそのまま使う
    （このサイト固有の後処理が無いため、わざわざラップするメソッドは置かない）。
    """

    PATH = "/devices"
