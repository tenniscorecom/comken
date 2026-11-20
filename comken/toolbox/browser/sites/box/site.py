"""comken/toolbox/browser/sites/box/site.py — Box 用の SiteBase クラス。

このサイトのものは sites/box/ の中で完結する（site.py・pages/）。
サイトを増やすときは sites/<サイト名>/ をもう1つ作る。

1サイトにつき ``Box`` と ``BoxBrowserOptions`` を **同じ ``site.py`` に置く**
（``〇〇Site`` と ``〇〇SiteOptions`` は必ずセットで、フォルダが同じならファイルも
分ける理由が無い）。

API（OAuth アプリ登録）は使わない。ログインはログイン画面の「サインインで続行」
ボタンを押すだけ（ID/パスワードの入力はしない）。2段階認証などが必要なときは
人がブラウザで承認する（``login()`` はその承認が終わるまで待つ）。

行ける画面は `go_〇〇()` で書き、コードがそのまま遷移図になるようにする
（書き方の正本は docs/機能/browser.md）。

> [!note] 独自サブドメインの Box
> 会社の Box が独自サブドメイン（https://<社名>.app.box.com など）を使っている
> 場合は、利用側で継承して ``BASE_URL`` を書き換える。セレクターはサブドメインに
> 依存しないが、ログイン画面の URL（account.box.com への遷移）が変わることがある。
"""

# 遷移先の import を型注釈だけ TYPE_CHECKING、実行時はメソッド内に分けているのは、
# 画面クラス同士の循環importを避けるため（循環の有無に関わらず一律この形にする）
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from comken.exceptions import BrowserError, LoginFailedError
from comken.toolbox.browser import BrowserOptions, SiteBase

if TYPE_CHECKING:
    from comken.toolbox.browser.management import BrowserSession
    from comken.toolbox.browser.sites.box.pages.file_page import FilePage
    from comken.toolbox.browser.sites.box.pages.folder_page import FolderPage
    from comken.toolbox.browser.sites.box.pages.login_page import LoginPage

logger = logging.getLogger(__name__)

# 人の操作（2段階認証の承認など）を待つ最大の秒数
_DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS = 600

# 人の操作を待つ間にブラウザの状態を確認する間隔（秒）。
# 短すぎるとポーリングの負荷、長すぎると完了検知が遅れる
_DEFAULT_MANUAL_LOGIN_INTERVAL_SECONDS = 3


class BoxBrowserOptions(BrowserOptions):
    """Box 用のブラウザオプション。

    デフォルト（BrowserOptions）から変更したいものだけ上書きする。
    全オプションのデフォルト値は comken/toolbox/browser/options.py を参照。
    """


class Box(SiteBase):
    """Box (https://app.box.com) を操作するためのサイトクラス。

    ログインは ``login()`` だけ。ID/パスワードの入力はせず、ログイン画面の
    「サインインで続行」ボタンを押したあと、2段階認証の承認を人が終えるのを待つ。

        with Box() as box:
            box.login()
            folder = box.go_folder("123456789")

    **ログインを使い回すには OPTIONS.PROFILE_ROOT を設定すること。**
    未設定だと起動のたびにまっさらなプロファイルになり、毎回ログインし直しになる
    （``docs/機能/browser.md`` の「ログイン状態を残す」を参照）:

        class MyBoxOptions(BrowserOptions):
            PROFILE_ROOT = r"C:\\\\作業\\\\box_profile"

        class MyBox(Box):
            OPTIONS = MyBoxOptions
    """

    NAME = "box"
    BASE_URL = "https://app.box.com"
    OPTIONS = BoxBrowserOptions
    OWNER = "comken"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。

        ``login()`` がこの画面を使って「サインインで続行」を押す。
        自分で操作するなら、この後で ``wait_for_manual_login()`` を呼ぶ。
        """
        from comken.toolbox.browser.sites.box.pages.login_page import LoginPage

        logger.info("Boxのログイン画面を開きます: url=%s", self.BASE_URL)
        return self.to(LoginPage).go("/login")

    def go_folder(self, folder_id: str = "0") -> FolderPage:
        """フォルダ画面を開く。

        Args:
            folder_id: フォルダの ID。``"0"`` は「すべてのファイル」。
        """
        from comken.toolbox.browser.sites.box.pages.folder_page import FolderPage

        return self.to(FolderPage).go(f"/folder/{folder_id}")

    def go_file(self, file_id: str) -> FilePage:
        """ファイルの詳細画面を開く。

        Args:
            file_id: ファイルの ID。
        """
        from comken.toolbox.browser.sites.box.pages.file_page import FilePage

        return self.to(FilePage).go(f"/file/{file_id}")

    def login(
        self,
        timeout: float = _DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS,
        interval: float = _DEFAULT_MANUAL_LOGIN_INTERVAL_SECONDS,
    ) -> None:
        """「サインインで続行」を押してログインし、2段階認証などを人が済ませるのを待つ。

        ログイン画面を開く → 既にログイン済みなら何もしない → そうでなければ
        「サインインで続行」を押す → そのまま ``wait_for_manual_login()`` を呼んで、
        2段階認証（アカウント選択・認証コード・端末承認など）の承認を人が終えるのを
        待つ。承認が完了してログイン済みになった時点で return する。

        Args:
            timeout: 2段階認証の承認を待つ最大の秒数。既定10分。
            interval: ブラウザ状態の確認間隔（秒）。既定3秒。

        Raises:
            LoginFailedError: ログイン画面のエラー表示が出た場合、
                ``timeout`` 秒待ってもログイン済みにならなかった場合。
            BrowserError: HEADLESS で起動中、かつ2段階認証の承認が必要な場合
                （人がブラウザを操作できないため、待たずにエラー）。
        """
        login_page = self.go_login()
        if self._is_logged_in():
            # ログイン状態を保存したプロファイルで、すでにログイン済みのとき
            logger.info("Boxはすでにログイン済みです")
        else:
            login_page.continue_sign_in()
            logger.info(
                "「サインインで続行」を押しました。"
                "2段階認証が要求される場合は表示中のEdgeで承認してください"
            )
        self.wait_for_manual_login(timeout=timeout, interval=interval)

    def wait_for_manual_login(
        self,
        timeout: float = _DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS,
        interval: float = _DEFAULT_MANUAL_LOGIN_INTERVAL_SECONDS,
    ) -> None:
        """ブラウザでの手動ログインが終わるまで、ブラウザを定期的にポーリングして待つ。

        ``go_login()`` の直後（ログイン画面を開いた直後）に呼ぶ。
        すでにログイン済みなら、**待たずにすぐ return する**。

        まだログインしていなければ ``interval`` 秒おきにブラウザ状態を確認し、
        ログイン済みになった時点で ``logger.info`` を出して return する。人が
        ターミナルで Enter を押す必要はない（無人の定期実行からも安全に呼べる）。

        ログイン画面のエラー表示が出たら ``LoginFailedError`` を送出する
        （認証情報が間違っている 等）。

        ``timeout`` 秒を過ぎてもログインが確認できなかった場合は
        ``LoginFailedError`` を送出する。

        ``OPTIONS.HEADLESS`` が ``True`` のときは人が2段階認証を承認できない
        ので、ログインが済んでいないままなら待たずに ``BrowserError`` を送出する。

        Args:
            timeout: 待機の最大秒数。既定10分。
            interval: ブラウザ状態の確認間隔（秒）。既定3秒。

        Raises:
            LoginFailedError: ログイン画面のエラー表示が出た場合、
                ``timeout`` 秒待ってもログイン済みにならなかった場合。
            BrowserError: HEADLESS で起動中、かつ2段階認証の承認が必要な場合。
        """
        from comken.toolbox.browser.sites.box.pages.login_page import LoginPage

        session = self._require_session()
        driver = session.raw

        if self._is_logged_in():
            logger.debug("Boxはログイン済みです: url=%s", driver.current_url)
            return

        # HEADLESS だとブラウザ画面が見えず人が2段階認証を承認できない
        headless = bool(self.OPTIONS.HEADLESS) if self.OPTIONS else False
        if headless:
            raise BrowserError(
                "Box のログインが済んでいませんが、HEADLESS で起動中のため"
                "人手で2段階認証を承認できません。\n"
                "対処: OPTIONS.HEADLESS を False にして（既定値）起動してから"
                "再度実行してください。"
            )

        timeout_minutes = max(1, int(timeout // 60))
        logger.warning(
            "Box のログインが済んでいません。"
            "表示中の Edge で2段階認証も含めて承認してください。"
            "最大 %d 分待ちます: url=%s",
            timeout_minutes,
            driver.current_url,
        )

        login_page = self.to(LoginPage)
        started = time.monotonic()
        deadline = started + timeout
        while True:
            time.sleep(interval)
            if self._is_logged_in():
                logger.info("手動ログインを確認しました（%d 秒）", int(time.monotonic() - started))
                return
            error = login_page.error_message()
            if error:
                raise LoginFailedError(error)
            if time.monotonic() >= deadline:
                raise LoginFailedError(
                    f"{timeout_minutes} 分待ちましたがログインを確認できませんでした: "
                    f"url={driver.current_url}\n"
                    "対処: Edge でログインしてから、もう一度実行してください。"
                )

    def _is_logged_in(self) -> bool:
        """ブラウザの状態が「Box にログイン済み」かを判定する。

        判定基準:
            - ログイン画面の「サインインで続行」ボタンが**見えていない**
            - **かつ** 現在 URL がログイン画面（account.box.com / login / sso）で無い
            - **かつ** ログイン後の画面にある目印（アカウントアイコン）が出ている

        根拠: URL による判定は
        https://github.com/b-tree-labs/axiom-os の
        src/axiom/extensions/builtins/publishing/providers/storage/box_browser.py
        の ``_needs_login()`` と同じロジック
        （``"account.box.com" in url or "login" in url.lower() or "sso" in url.lower()``）。
        目印の要素は AppPage.APP_SHELL を参照。
        Microsoft のアカウント選択画面（login.microsoftonline.com /
        login.live.com）も "login" を含むので、未ログインとして扱われる。
        """
        from comken.toolbox.browser.sites.box.pages.app_page import AppPage

        session = self._require_session()
        driver = session.raw

        # ログイン画面のボタンが見えていれば、まだログインしていない
        if self._continue_button_shown():
            return False

        lowered_url = driver.current_url.lower()
        if "account.box.com" in lowered_url or "login" in lowered_url or "sso" in lowered_url:
            return False

        # ログイン後の画面（アカウントアイコン）が出ていればログイン済み
        return bool(driver.find_elements(*AppPage.APP_SHELL))

    def _continue_button_shown(self) -> bool:
        """「サインインで続行」ボタンが画面に見えているかを返す（待たない）。

        ログイン画面のボタンが見えている間は、まだログインしていない
        （``_is_logged_in()`` の判定に使う）。
        """
        from comken.toolbox.browser.sites.box.pages.login_page import LoginPage

        session = self._require_session()
        # find_elements は要素が無ければ空リストを返す（例外は出ない）
        elements = session.raw.find_elements(*LoginPage.CONTINUE_BTN)
        return any(element.is_displayed() for element in elements)

    def _require_session(self) -> BrowserSession:
        """起動済みの BrowserSession を返す。未起動なら理由を示して落とす。"""
        if self.session is None:
            raise BrowserError(
                f"{self.__class__.__name__} はまだ起動していません。"
                f"`with {self.__class__.__name__}() as site:` の中で使ってください。"
                "\n対処: `with SiteBase() as site:` の中で使ってください"
                "（ブラウザは起動していないので実害はない）。"
            )
        return self.session
