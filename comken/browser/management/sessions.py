"""1サイト分のブラウザーを表す ``BrowserSession``。

このファイルはWebDriverの生存期間と、1セッションを同時に操作させない排他制御を担当する。
複数ブラウザーの管理は ``browsers.py``、タブの開閉は ``tabs.py`` が担当する。

1つのサイトにつき1つのブラウザを起動する。タブで複数サイトを扱わないのは、
ダウンロード先・起動オプション・ログイン状態がすべてブラウザ単位で決まるため。
タブで分けると「サイトAのCSVがサイトBのフォルダに落ちる」といった取り違えが起きる。

このクラスを直接作らず、Browsersから起動する:

    from comken.browser import Browsers

    with Browsers() as browsers:
        kintai = browsers.launch("kintai")
        kintai.open("https://kintai.example.co.jp")

サイトが1つでも複数でも書き方は同じで、増やすときは launch を1行足すだけにしてある。
"""

import logging
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from selenium import webdriver

from comken.exceptions import (
    ConcurrentSessionUseError,
    SessionClosedError,
    SessionNotStartedError,
)
from comken.utils import now

from ..download import DownloadDir
from ..locator import Locator
from ..options import BrowserOptions
from .startup import start_driver
from .tabs import _TabManager

logger = logging.getLogger(__name__)

# 新しいタブが開くのを待つ既定の秒数
_POPUP_TAB_TIMEOUT_SECONDS = 10

# load_many で同時に開いておくタブの既定数。増やすほど待ち時間が重なって速くなるが、
# メモリとサイト側の負荷も増えるため、控えめな値から始める
_DEFAULT_MAX_OPEN_TABS = 5


class BrowserSession:
    """1サイト分の Edge ブラウザ。with 文の中でだけ使える。

    with を必須にしているのは、処理の途中で例外が出たときに
    ブラウザのプロセスと一時フォルダを確実に片付けるため。
    with を使わずに操作すると SessionNotStartedError になる。

    ダウンロード先・ログイン状態・起動オプションはこのセッションが専有する。
    他のセッションと混ざらないので、サイトごとに違う設定を安心して使える。

    Attributes:
        name: セッション名。ログとエラーメッセージに出るので、
              「kintai」「keiri」のようにサイトが分かる名前にする。
        download_dir: このセッション専用のダウンロードフォルダ。
                      完了待ちは download_dir.wait() を使う。
        wait_seconds: 要素待機のタイムアウト秒数。Page がこれを引き継ぐ。
    """

    def __init__(
        self,
        name: str,
        options: BrowserOptions,
        download_dir: DownloadDir,
        profile_dir: Path | None = None,
    ) -> None:
        """直接呼ばず、Browsers.launch() から作る。

        Args:
            name: セッション名。
            options: 起動オプション。セッションごとに別インスタンスを渡すこと。
            download_dir: このセッション専用のダウンロードフォルダ。
            profile_dir: ログイン状態を残すフォルダ。None なら毎回まっさらな状態で起動する。
        """
        self.name = name
        self.download_dir = download_dir
        self.wait_seconds = options.WAIT_SECONDS

        self._options = options
        self._profile_dir = profile_dir
        self._driver: webdriver.Edge | None = None
        self._is_closed = False

        # 同じセッションを2スレッドから同時に操作していないかを見張る。
        # RLock なので、同じスレッドの中で操作がネストしても止まらない
        self._lock = threading.RLock()
        self._holder_name = ""

    # ------------------------------------------------------------ with 管理

    def __enter__(self) -> "BrowserSession":
        # ここで例外を投げると、この with の __exit__ は呼ばれない。
        # 後始末は _start_driver() の中で完結させること
        self._driver = start_driver(self._options, self._profile_dir, self.download_dir)
        logger.info("ブラウザを起動しました: %s", self.name)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # エラーで抜けるときは、原因調査のために最後の画面を残す
        if exc_type is not None:
            self._save_error_screenshot()

        self._is_closed = True
        driver = self._driver
        self._driver = None
        try:
            if driver is not None:
                driver.quit()
                logger.info("ブラウザを終了しました: %s", self.name)
        finally:
            # quit() が失敗しても一時フォルダは必ず片付ける（残留防止）
            self.download_dir.__exit__(exc_type, exc_value, traceback)

    # ------------------------------------------------------------ ページ操作

    def open(self, url: str) -> None:
        """URL を開く。"""
        with self.operating("open"):
            self._require_driver().get(url)

    def refresh(self) -> None:
        """今のページを再読み込みする。"""
        with self.operating("refresh"):
            self._require_driver().refresh()

    def back(self) -> None:
        """ブラウザの「戻る」。"""
        with self.operating("back"):
            self._require_driver().back()

    @property
    def current_url(self) -> str:
        """今開いている URL。"""
        with self.operating("current_url"):
            return self._require_driver().current_url

    @property
    def title(self) -> str:
        """今開いているページのタイトル。"""
        with self.operating("title"):
            return self._require_driver().title

    @property
    def page_source(self) -> str:
        """今開いているページの HTML。"""
        with self.operating("page_source"):
            return self._require_driver().page_source

    def save_screenshot(self, prefix: str = "screenshot") -> Path:
        """今の画面を logs/ に PNG で保存し、そのパスを返す。

        Args:
            prefix: ファイル名の先頭。保存先は logs/{prefix}_{セッション名}_{日時}.png。

        Returns:
            保存したファイルのパス。
        """
        with self.operating("save_screenshot"):
            timestamp = now().strftime("%Y%m%d_%H%M%S")
            path = Path("logs") / f"{prefix}_{self.name}_{timestamp}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            self._require_driver().save_screenshot(str(path))
            return path

    @contextmanager
    def popup_tab(self, timeout: int | None = None) -> Iterator["BrowserSession"]:
        """別タブで開いた画面を操作し、抜けるときに閉じて元のタブへ戻る。

        リンクの target="_blank" や帳票 PDF のように、こちらの意図と関係なく
        タブが増える場面のためのもの。タブを開く操作を済ませてから with に入る:

            page.click(PDF_LINK)              # ここで別タブが開く
            with session.popup_tab():         # 開いたタブへ移る
                session.save_screenshot("pdf")
            # ← 別タブを閉じて、元のタブへ戻る（中で例外が出ても戻る）

        Args:
            timeout: 新しいタブが開くのを待つ秒数。省略時は 10 秒。

        Yields:
            自分自身。中では今までどおり session と Page をそのまま使える。

        Raises:
            PopupTabNotOpenedError: 時間内に新しいタブが開かなかった場合。
        """
        seconds = timeout if timeout is not None else _POPUP_TAB_TIMEOUT_SECONDS
        with self.operating("popup_tab"):
            tabs = _TabManager(self._require_driver(), self.name)
            with tabs.popup(seconds):
                yield self

    def load_many(
        self,
        urls: "Sequence[str]",
        ready: "Locator | None" = None,
        max_open: int = _DEFAULT_MAX_OPEN_TABS,
        timeout: int | None = None,
    ) -> Iterator[str]:
        """同じサイトの複数ページをまとめて開き、**読み込めたものから順に**返す。

        レポート一覧のように、同じサイトの大量の URL を見て回るときに使う。
        1件ずつ開いて待つと「読み込み時間 × 件数」かかるが、先に何枚か開いておくと
        待ち時間がブラウザ側で重なるため、全体が大幅に短くなる
        （1件2分・90件なら、逐次で3時間、10枚開けば20分台）。

        ログインは1回で済む。同じブラウザの中でタブを開くだけなので、
        Cookie も二要素認証の記憶も共有される。

            for url in sf.load_many(report_urls, ready=ReportPage.TABLE, max_open=10):
                rows = ReportPage(sf).rows()     # そのページのタブに切り替わっている
                save(url, rows)
            # ← 抜けると、開いたタブは全部閉じて元のタブへ戻る

        Args:
            urls: 開く URL。渡した順に開くが、**返る順番は読み込みが終わった順**になる。
            ready: 読み込み完了とみなす目印の要素。省略すると HTML の読み込み完了で判断する。
                   画面を描いてから中身を入れるサイト（Salesforce など）では、
                   表やヘッダーなど「出たら中身がある」要素を指定すること。
            max_open: 同時に開いておくタブの数。増やすほど速くなるが、
                      メモリとサイト側の負荷も増える。
            timeout: 1ページあたりの待ち時間の上限（秒）。省略時はセッションの設定。
                     超えたページは諦めて次へ進み、警告ログに残す。

        Yields:
            読み込みが終わった URL。yield されている間、そのページのタブに切り替わっており、
            Page のメソッドがそのまま使える。

        Raises:
            SessionNotStartedError: with に入る前に呼んだ場合。
            ConcurrentSessionUseError: 他のスレッドが同じセッションを操作している場合。
        """
        seconds = timeout if timeout is not None else self.wait_seconds
        with self.operating("load_many"):
            tabs = _TabManager(self._require_driver(), self.name)
            yield from tabs.load_many(urls, ready, max_open, seconds)

    # ------------------------------------------------------------ 内部連携用

    @property
    def raw(self) -> webdriver.Edge:
        """selenium の WebDriver そのもの。

        このクラスと Page に用意されていない機能を使うときの逃げ道。
        ここから switch_to でタブを移動すると、セッションが今どのタブにいるかを
        見失うことがあるので、タブ操作は popup_tab() を使うこと。

        ここから直接操作すると、同時操作の見張り（operating）を通らない。
        parallel の中で使う場合、他のスレッドと衝突しないことは呼び出し側の責任になる。
        """
        return self._require_driver()

    @contextmanager
    def operating(self, operation: str) -> Iterator[None]:
        """このセッションを操作している間の目印。Page から使う。

        with に入っているか、すでに閉じていないか、他のスレッドが同時に
        触っていないかをまとめて確認する。

        Args:
            operation: 何をしようとしているか（エラーメッセージに出る）。

        Raises:
            SessionNotStartedError: with に入る前に操作した場合。
            SessionClosedError: with を抜けた後に操作した場合。
            ConcurrentSessionUseError: 他のスレッドが同時に操作している場合。
        """
        if self._is_closed:
            raise SessionClosedError(self.name, operation)
        if self._driver is None:
            raise SessionNotStartedError(operation)

        # blocking=False にして「待つ」のではなく「弾く」。待ってしまうと
        # 設計ミスが性能劣化として現れるだけで、原因に気づけないため
        if not self._lock.acquire(blocking=False):
            raise ConcurrentSessionUseError(self.name, operation, self._holder_name)
        self._holder_name = threading.current_thread().name
        try:
            yield
        finally:
            self._lock.release()

    # ------------------------------------------------------------ 内部処理

    def _require_driver(self) -> webdriver.Edge:
        """起動済みの WebDriver を返す。使える状態でなければ理由を示して落とす。"""
        if self._is_closed:
            raise SessionClosedError(self.name, "driver")
        if self._driver is None:
            raise SessionNotStartedError("driver")
        return self._driver

    def _save_error_screenshot(self) -> None:
        """エラーで終わるときの画面を残す。

        保存に失敗しても、本来の例外を隠さないよう警告だけ出して続行する。
        """
        if self._driver is None:
            return
        try:
            timestamp = now().strftime("%Y%m%d_%H%M%S")
            path = Path("logs") / f"error_{self.name}_{timestamp}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            self._driver.save_screenshot(str(path))
            logger.error("エラー時の画面を保存しました: %s", path.resolve())
        except Exception:
            logger.warning("エラー時の画面を保存できませんでした", exc_info=True)

    def __repr__(self) -> str:
        if self._is_closed:
            state = "終了済み"
        elif self._driver is None:
            state = "未起動"
        else:
            state = "起動中"
        return f"BrowserSession(name={self.name!r}, {state})"
