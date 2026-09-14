"""comken/toolbox/browser/sites/ams/pages/customer_list_page.py — お客様一覧画面（雛形）

URL や要素セレクタは example の値のまま。利用プロジェクト側で継承して書き換える。
"""

from __future__ import annotations

from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.ams.pages.app_page import AppPage
from comken.toolbox.browser.sites.ams.pages.device_screen_page import DeviceScreenPage


class CustomerListPage(AppPage):
    """お客様一覧画面（/customers）。お客様IDで検索し、装置画面へ進む。"""

    PATH = "/customers"
    CUSTOMER_ID_INPUT = Locator.id("customerId")
    SEARCH_BTN = Locator.css("button.search")
    # 検索結果が表示された目印（Ajax等で少し遅れて出る想定なので、これが
    # 出るまで待ってから DEVICE_LINK の有無を見る）
    RESULT_AREA = Locator.css(".search-result")
    # 検索結果内、そのお客様に紐づく装置へのリンク。無ければ装置が未登録
    DEVICE_LINK = Locator.css("a.device-link")

    def search(self, customer_id: str) -> None:
        """お客様IDで検索する。結果が画面内に表示されるまで待つ。"""
        self.input(self.CUSTOMER_ID_INPUT, customer_id)
        self.click(self.SEARCH_BTN)
        self.wait_visible(self.RESULT_AREA)

    def has_device(self) -> bool:
        """直前の search() の結果に、装置へのリンクがあるかを返す。

        search() の後、ここが False の間はブラウザは実際にはまだこの
        CustomerListPage のままなので、open_device_screen() は呼ばない
        （呼ぶと装置画面へ遷移したことになってしまい、実態と食い違う）。
        """
        return self.has_element(self.DEVICE_LINK)

    def open_device_screen(self) -> DeviceScreenPage:
        """装置リンクを開き、DeviceScreenPage を返す。

        呼ぶ前に has_device() で有無を確かめておくこと
        （装置が無いのに呼ぶと、通常の click() と同じ待機タイムアウトになる）。

            for customer_id in customer_ids:
                # 一覧画面はURL直飛びで開き直せるので、検索のたびに取り直す
                customer_list = ams.go_customer_list()
                customer_list.search(customer_id)
                if not customer_list.has_device():
                    logger.warning("装置が見つかりません: customer_id=%s", customer_id)
                    continue
                device_screen = customer_list.open_device_screen()
                device_screen.save_screenshot(f"device_{customer_id}.png")
        """
        self.click(self.DEVICE_LINK)
        return self.to(DeviceScreenPage)
