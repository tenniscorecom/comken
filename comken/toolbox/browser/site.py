r"""comken/toolbox/browser/site.py — サイトを表す SiteBase 基底クラス。

1サイトにつき1クラスを作って、固有の値をそこに集める。設計の骨格は
`comken.toolbox.salesforce.SalesforceBase` と同じ。読み書き両方を知っていれば、
片方は形だけで分かる。

1サイトだけ触るツールでは `with Kintai() as kintai:` で完結する。複数サイトを
扱うときは `with Browsers() as browsers: kintai = browsers.launch(Kintai)`。
どちらの出口でも SiteBase インスタンスが返り、`.session` で BrowserSession に繋がる。

    from comken.toolbox.browser import Browsers, SiteBase, BrowserOptions

    class KintaiOptions(BrowserOptions):
        DOWNLOAD_DIR = r"C:\work\downloads"

    class Kintai(SiteBase):
        NAME = "kintai"
        BASE_URL = "https://kintai.example.co.jp"
        OPTIONS = KintaiOptions

    # 1サイトだけ
    with Kintai() as kintai:
        print(kintai.login("user01", "password").unfilled_days())

    # 複数サイト
    with Browsers() as browsers:
        kintai = browsers.launch(Kintai)
        keiri = browsers.launch(Keiri)
        ...
"""

# 定義中（クラス内）の BrowserSession / Browsers を型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, TypeVar

from ...exceptions import SiteConfigError, SiteNotStartedError
from .download import DownloadDir
from .options import BrowserOptions

if TYPE_CHECKING:
    from .management import Browsers, BrowserSession
    from .page import Page

# page() が「渡したクラスをそのまま返す」ことを型で示す。
# これがないと補完が Page 止まりになり、画面ごとのメソッドが出ない
P = TypeVar("P", bound="Page")


class SiteBase:
    """1サイト分の入口。サイトごとにサブクラスを作って固有の値を置く。

    サブクラスで NAME / BASE_URL / OPTIONS を上書きする。`session` 以外の状態
    （current_url や cookie など）は持たない — 同じサイトを2アカウントで並列に
    開けるようにするため。

    使い方は2つ:
      - `with Kintai() as kintai:` … 1サイトだけ。Browsers を内側で抱えて起動する
      - `with Browsers() as browsers: kintai = browsers.launch(Kintai)` … 複数サイト

    Attributes:
        session: このサイトに紐づく BrowserSession。Page に渡して操作する。
    """

    # ログ・ダウンロード先・ログイン状態の分け方の鍵。Browsers.launch_session() に渡る
    NAME: ClassVar[str] = ""
    # 画面の BASE_URL にそのまま使える。SitePage.BASE_URL が無ければこれが使われる
    BASE_URL: ClassVar[str] = ""
    # 起動オプション。クラスで渡す（セッションごとに別インスタンスが作られる）
    OPTIONS: ClassVar[type[BrowserOptions] | None] = None

    def __init__(self, session: BrowserSession | None = None) -> None:
        self.session = session
        # 自分で起動した Browsers（with Kintai() 経由）。Browsers から持ってきた
        # ときは None のままにして、`close()` で持ち物を閉じてしまわないように区別する
        self._browsers: Browsers | None = None

    def __enter__(self) -> SiteBase:
        # 循環インポートを避けるため、使う直前に取り出す
        from .management import Browsers

        if not self.NAME:
            raise SiteConfigError(self.__class__, "NAME")
        self._browsers = Browsers()
        self._browsers.__enter__()
        session = self._browsers.launch_session(self.NAME, self.OPTIONS)
        self.session = session
        # SitePage.BASE_URL が未設定のときの参照先。launch_session() からは
        # 設定されないので、ここで結びつける
        session._site = self
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._browsers is not None:
            self._browsers.__exit__(exc_type, exc_val, exc_tb)
            self._browsers = None
        self.session = None

    @property
    def downloads(self) -> DownloadDir:
        """このサイトのダウンロード先。完了待ちに使う。

            files = kintai.downloads.wait()   # .crdownload が消えるまで待つ

        Raises:
            SiteNotStartedError: まだ起動していない場合。
        """
        if self.session is None:
            raise SiteNotStartedError(self.__class__)
        return self.session.download_dir

    def to(self, page_class: type[P]) -> P:
        """このサイトの画面へ移る。

        画面クラスは動かすのにブラウザ（`BrowserSession`）を要るが、
        **それを呼ぶ側に書かせない**ためのもの。

            with Kintai() as kintai:
                home = kintai.to(LoginPage).login(user_id, password)

        `Page.to()` と同じ名前にそろえてある。サイトから最初の画面へ移るのも、
        画面から次の画面へ移るのも、利用側から見れば同じ「移る」なので、
        覚える言葉を増やさない。

        `LoginPage(self.session)` と書いても同じだが、そう書くと
        「セッションとは何か」を知らないとサイトクラスを書けなくなる。

        Args:
            page_class: 作りたい画面クラス（`Page` のサブクラス）。

        Returns:
            そのサイトのブラウザに紐づいた画面クラスのインスタンス。
        """
        if self.session is None:
            raise SiteNotStartedError(self.__class__)
        return page_class(self.session)

    def close(self) -> None:
        """Browsers から渡されたセッションは触らず、自分で起動したブラウザだけ閉じる。

        `with Kintai() as kintai:` で起動したインスタンスを `close()` しても安全。
        ただし `Browsers.launch()` から持たせてもらったインスタンスでは何もしない
        （持ち主の Browsers が with を抜けるときに閉じるため、二重に閉じない）。
        """
        if self._browsers is not None:
            self._browsers.__exit__(None, None, None)
            self._browsers = None
        self.session = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.NAME!r})"
