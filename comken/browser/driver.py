import datetime
import logging
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.remote.webelement import WebElement

from .download import DownloadDir
from .options import BrowserOptions

logger = logging.getLogger(__name__)


class EdgeDriver:
    """Edge WebDriver のラッパー。with 文で確実に終了できる。

    よく使うブラウザ操作は d.open(...) / d.find_element(...) のように直接呼べる
    （d.driver.get(...) と書かなくてよい。エディタ補完も効く）。
    ここにない WebDriver の機能は d.driver.xxx で使う。

    デフォルトでは内部に一時ダウンロードフォルダを自動作成し、
    with を抜けると自動削除する。ファイルを残したい場合は
    BrowserOptions.DOWNLOAD_DIR またはコンストラクタの download_dir にパスを指定する。

    Args:
        browser_options: BrowserOptions のインスタンス。省略時はデフォルト設定で起動。
                         DRIVER_PATH / WAIT_SECONDS / DOWNLOAD_DIR もここで設定する。
        download_dir: ダウンロード先（BrowserOptions.DOWNLOAD_DIR より優先）。
                      - パス（str / Path）→ 固定フォルダとして使う（削除しない）
                      - DownloadDir → そのまま使う
                      - 省略 → BrowserOptions.DOWNLOAD_DIR を使う（None なら一時フォルダ）

    使い方（デフォルト：一時フォルダ、with 終了で自動削除）:
        from comken.files import move_file

        with EdgeDriver() as d:
            d.open("https://example.com")
            # ... ダウンロード操作 ...
            files = d.download_dir.wait()        # 完了まで待機
            move_file(files[0], r"C:\\作業\\output")  # with 内で移動する
        # ← ここで一時フォルダは自動削除される

    使い方（ファイルを残す場合）:
        # BrowserOptions で指定
        opts = BrowserOptions()
        opts.DOWNLOAD_DIR = r"C:\\作業\\downloads"
        with EdgeDriver(opts) as d:
            files = d.download_dir.wait()
        # ← C:\\作業\\downloads のファイルはそのまま残る

        # または EdgeDriver に直接指定
        with EdgeDriver(download_dir=r"C:\\作業\\downloads") as d:
            files = d.download_dir.wait()
    """

    def __init__(
        self,
        browser_options: BrowserOptions | None = None,
        download_dir: "str | os.PathLike | DownloadDir | None" = None,
    ) -> None:
        opts = browser_options or BrowserOptions()

        options = Options()
        for arg in opts.build():
            options.add_argument(arg)

        self.download_dir = _resolve_download_dir(download_dir, opts.DOWNLOAD_DIR)
        # BasePage の明示的待機（WebDriverWait）のデフォルト秒数として引き継がせる
        self.wait_seconds = opts.WAIT_SECONDS
        options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": str(self.download_dir.path),
                "download.prompt_for_download": False,
            },
        )

        # ドライバー起動に失敗すると with に入る前に例外で抜けるため、
        # ここで片付けないと作成済みの一時フォルダが残り続ける
        try:
            service = Service(executable_path=opts.DRIVER_PATH)
            self._driver = webdriver.Edge(service=service, options=options)
            # 暗黙的待機は 0 にする。待機は BasePage の WebDriverWait（明示的待機）に一本化する。
            # 暗黙×明示を混在させると待ち時間が予測不能になり、要素の不在確認
            # （has / count）が毎回 WAIT_SECONDS 分ブロックしてしまうため
            self._driver.implicitly_wait(0)
        except Exception:
            # ブラウザが起動済みなら閉じてから、作成済みの一時フォルダを片付ける
            driver = getattr(self, "_driver", None)
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    logger.warning("起動失敗後のブラウザ終了に失敗しました", exc_info=True)
            self.download_dir.__exit__(None, None, None)
            raise

    def __enter__(self) -> "EdgeDriver":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # エラーで抜ける場合は、原因調査用にその時点の画面を残す
        if exc_type is not None:
            self._save_error_screenshot()
        # quit() が失敗しても一時フォルダの後始末は必ず行う（残留防止）
        try:
            self.quit()
        finally:
            self.download_dir.__exit__(exc_type, exc_value, traceback)  # 一時フォルダなら自動削除

    def _save_error_screenshot(self) -> None:
        """エラー発生時のスクリーンショットを logs/ に保存する。

        保存に失敗しても本来の例外を邪魔しない（警告ログだけ出して続行）。
        """
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = Path("logs") / f"error_{timestamp}.png"
            path.parent.mkdir(exist_ok=True)
            self._driver.save_screenshot(str(path))
            logger.error("エラー発生時のスクリーンショットを保存しました: %s", path.resolve())
        except Exception:
            logger.warning("エラー時スクリーンショットの保存に失敗しました", exc_info=True)

    @property
    def driver(self) -> webdriver.Edge:
        """内部の WebDriver。BasePage 等に生の WebDriver を渡したい場合に使う。"""
        return self._driver

    def quit(self) -> None:
        self._driver.quit()

    # ---------------------------------------------------- WebDriver の委譲
    # よく使うものはエディタ補完が効くよう明示的にラップする。
    # ここにない WebDriver の機能は d.driver.xxx で使う（型付きなので補完が効く）。

    def open(self, url: str) -> None:
        """URL を開く（WebDriver の get に相当。役割が分かる名前にしている）。"""
        self._driver.get(url)

    def find_element(self, by: str, value: str) -> WebElement:
        """要素を1つ取得する（見つからなければ NoSuchElementException）。

        使い方:
            from selenium.webdriver.common.by import By
            d.find_element(By.ID, "login-btn").click()
        """
        return self._driver.find_element(by, value)

    def find_elements(self, by: str, value: str) -> list[WebElement]:
        """要素をすべて取得する（見つからなければ空リスト）。"""
        return self._driver.find_elements(by, value)

    def execute_script(self, script: str, *args):
        """JavaScript を実行する。"""
        return self._driver.execute_script(script, *args)

    def refresh(self) -> None:
        """ページを再読み込みする。"""
        self._driver.refresh()

    def back(self) -> None:
        """ブラウザの「戻る」。"""
        self._driver.back()

    def save_screenshot(self, path: "str | os.PathLike") -> bool:
        """スクリーンショットを PNG で保存する。"""
        return self._driver.save_screenshot(str(path))

    def maximize_window(self) -> None:
        """ウィンドウを最大化する。"""
        self._driver.maximize_window()

    @property
    def current_url(self) -> str:
        """現在の URL。"""
        return self._driver.current_url

    @property
    def title(self) -> str:
        """現在のページタイトル。"""
        return self._driver.title

    @property
    def page_source(self) -> str:
        """現在のページの HTML ソース。"""
        return self._driver.page_source

    @property
    def switch_to(self):
        """フレーム・ウィンドウ・アラートの切り替え（d.switch_to.frame(...) 等）。"""
        return self._driver.switch_to

    def __getattr__(self, name: str):
        # 明示的にラップしていない WebDriver のメソッド・属性はそのまま委譲する
        # （__getattr__ は通常の属性探索で見つからなかったときだけ呼ばれる）
        if name.startswith("_"):
            # _driver 未設定時の無限再帰と、copy/pickle 等の内部属性探索を防ぐ
            raise AttributeError(name)
        return getattr(self._driver, name)


def _resolve_download_dir(
    download_dir: "str | os.PathLike | DownloadDir | None",
    options_download_dir: "str | None",
) -> DownloadDir:
    """download_dir 引数を DownloadDir に揃える。

    - DownloadDir ならそのまま使う
    - パス（str / Path）なら固定フォルダの DownloadDir に包む
    - 未指定かつ BrowserOptions.DOWNLOAD_DIR が設定済み → 固定フォルダ
    - 未指定かつ BrowserOptions.DOWNLOAD_DIR が None → 一時フォルダを自動作成

    どの指定方法でも d.download_dir.wait() が使える。
    """
    if isinstance(download_dir, DownloadDir):
        return download_dir
    if download_dir:
        return DownloadDir(path=download_dir)
    if options_download_dir:
        return DownloadDir(path=options_download_dir)
    return DownloadDir()  # 一時フォルダ（EdgeDriver の with 終了時に自動削除）
