"""comken/toolbox/browser/page/alerts.py — 警告ダイアログの操作（alert_accept 系）。"""

from __future__ import annotations

from typing import cast

from selenium.webdriver.common.alert import Alert
from selenium.webdriver.support import expected_conditions as EC

from comken.toolbox.browser.page.base import _PageBase


class AlertsMixin(_PageBase):
    """警告ダイアログの操作（alert_accept / alert_dismiss / read_alert_text）。"""

    def alert_accept(self) -> None:
        """ブラウザの確認ダイアログで OK を押す。出るまで待つ。"""
        with self.session._operating("alert_accept"):
            # EC.alert_is_present() の戻り Alert を pyright が bool と推論するため、Alert に直す
            cast(Alert, self._until(EC.alert_is_present(), "alert", "現れ")).accept()

    def alert_dismiss(self) -> None:
        """ブラウザの確認ダイアログでキャンセルを押す。出るまで待つ。"""
        with self.session._operating("alert_dismiss"):
            cast(Alert, self._until(EC.alert_is_present(), "alert", "現れ")).dismiss()

    def read_alert_text(self) -> str:
        """ブラウザの確認ダイアログの文言を返す。出るまで待つ。"""
        with self.session._operating("read_alert_text"):
            return cast(Alert, self._until(EC.alert_is_present(), "alert", "現れ")).text
