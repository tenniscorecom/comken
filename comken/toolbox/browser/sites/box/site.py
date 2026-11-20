"""comken/toolbox/browser/sites/box/site.py — Box 用の SiteBase クラス。

このサイトのものは sites/box/ の中で完結する（site.py・pages/）。
サイトを増やすときは sites/<サイト名>/ をもう1つ作る。

1サイトにつき ``Box`` と ``BoxBrowserOptions`` を **同じ ``site.py`` に置く**
（``〇〇Site`` と ``〇〇SiteOptions`` は必ずセットで、フォルダが同じならファイルも
分ける理由が無い）。

API（OAuth アプリ登録）は使わない。ログインはメールアドレスとパスワードで行い、
2段階認証などが必要なときは人がブラウザで承認する（``login_with_credentials()``
は DPAPI の認証情報を入力したあと、その承認を待つ）。

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

    ログインは 2 通り:

    - ``go_login()`` + ``LoginPage.login()`` — 自分でID/パスワードを入力する
    - ``login_with_credentials()`` — DPAPI に保存したID/パスワードを自動入力し、
      そのまま 2段階認証の承認を人が終えるのを待つ

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

    # DPAPI に登録する認証情報のシステム名。
    # ``username`` と ``password`` の2項目を登録しておく（``python -m comken cred gui``）
    CREDENTIAL_PREFIX = "box"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。

        ID/パスワードを自分で入力するなら ``LoginPage.login()``、人が手動で
        入力するならこの後 ``wait_for_manual_login()`` を呼ぶ。
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

    def login_with_credentials(
        self,
        prefix: str = "",
        timeout: float = _DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS,
        interval: float = _DEFAULT_MANUAL_LOGIN_INTERVAL_SECONDS,
    ) -> None:
        """DPAPI に保存したID/パスワードでログインし、2段階認証などを人が済ませるのを待つ。

        ``Credentials`` の ``username`` / ``password`` でログイン画面に入力・送信
        したあと、そのまま ``wait_for_manual_login()`` を呼んで、2段階認証（認証
        コード・端末承認など）の承認を人が終えるのを待つ。承認が完了して
        ログイン済みになった時点で return する。

        Args:
            prefix: DPAPI に登録した認証情報のシステム名
                （``comken.toolbox.credentials.Credentials`` のサイト名）。
                ``username`` / ``password`` の2項目を登録しておく
                （例: ``python -m comken cred gui``）。**省略時はクラスの
                ``CREDENTIAL_PREFIX``** を使う。
            timeout: 2段階認証の承認を待つ最大の秒数。既定10分。
            interval: ブラウザ状態の確認間隔（秒）。既定3秒。

        Raises:
            CredentialNotFoundError: prefix 配下に username/password が未登録の場合。
            CredentialError: 別のユーザー・PC で登録されていて復号できない場合。
            LoginFailedError: ログイン画面のエラー表示が出た場合、
                ``timeout`` 秒待ってもログイン済みにならなかった場合。
            BrowserError: HEADLESS で起動中、かつ2段階認証の承認が必要な場合
                （人がブラウザを操作できないため、待たずにエラー）。
        """
        from comken.toolbox.credentials import Credentials

        prefix = prefix or self.CREDENTIAL_PREFIX
        logger.info("DPAPIの認証情報でログインを試みます: prefix=%s", prefix)
        cred = Credentials(prefix)

        login_page = self.go_login()
        if self._is_logged_in():
            # ログイン状態を保存したプロファイルで、すでにログイン済みのとき
            logger.info("Boxはすでにログイン済みです")
        else:
            login_page.login(cred.username, cred.password)
            logger.info(
                "IDとパスワードを入力しました。2段階認証がある場合は表示中のEdgeで承認してください"
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
            - ログイン画面の入力欄（``#login-email``）が**無い**
            - **かつ** 現在 URL がログイン画面（account.box.com / login / sso）で無い
            - **かつ** ログイン後の画面にある目印（アカウントアイコン）が出ている

        根拠: URL による判定は
        https://github.com/b-tree-labs/axiom-os の
        src/axiom/extensions/builtins/publishing/providers/storage/box_browser.py
        の ``_needs_login()`` と同じロジック
        （``"account.box.com" in url or "login" in url.lower() or "sso" in url.lower()``）。
        目印の要素は AppPage.APP_SHELL を参照。
        """
        from comken.toolbox.browser.sites.box.pages.app_page import AppPage
        from comken.toolbox.browser.sites.box.pages.login_page import LoginPage

        session = self._require_session()
        driver = session.raw

        # find_elements は要素が無ければ空リストを返す（例外は出ない）。
        # 入力欄が見えていれば、まだログイン画面（あるいはその残骸）
        if driver.find_elements(*LoginPage.EMAIL_INPUT):
            return False

        lowered_url = driver.current_url.lower()
        if "account.box.com" in lowered_url or "login" in lowered_url or "sso" in lowered_url:
            return False

        # ログイン後の画面（アカウントアイコン）が出ていればログイン済み
        return bool(driver.find_elements(*AppPage.APP_SHELL))

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
