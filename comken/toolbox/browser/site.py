r"""comken/toolbox/browser/site.py — サイトを表す Site 基底クラス。

1サイトにつき1クラスを作って、固有の値をそこに集める。設計の骨格は
`comken.toolbox.salesforce.SalesforceBase` と同じ。読み書き両方を知っていれば、
片方は形だけで分かる。

    from comken.toolbox.browser import Browsers, Site, BrowserOptions

    class KintaiOptions(BrowserOptions):
        DOWNLOAD_DIR = r"C:\work\downloads"

    class Kintai(Site):
        NAME = "kintai"
        BASE_URL = "https://kintai.example.co.jp"
        OPTIONS = KintaiOptions

    # 1サイトだけなら、これだけで起動から後片付けまで済む
    with Kintai() as kintai:
        kintai.session.open(kintai.BASE_URL)

    # 複数サイトを扱う・並列で動かすときは Browsers から
    with Browsers() as browsers:
        kintai = browsers.launch(Kintai)
        keiri = browsers.launch(Keiri)

Name を渡していた書き方を、Site クラスを渡す書き方に集約する。サイト固有の値を
1か所に集められるため、Name と Options を別々に渡したときに取り違える事故がない。
"""

# BrowseSessions から type 注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

from .options import BrowserOptions

if TYPE_CHECKING:
    from .management import BrowserSession


class Site:
    """1サイト分の入口。サイトごとにサブクラスを作って固有の値を置く。

    サブクラスで NAME / BASE_URL / OPTIONS を上書きする。`session` 以外の状態
    （current_url や cookie など）は持たない — 同じサイトを2アカウントで並列に
    開けるようにするため。

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
        """
        Args:
            session: 使うブラウザ。**省略するとこのサイト専用に1つ起動する**
                （`with Kintai() as kintai:` の形）。`Browsers.launch()` から
                作られるときは、そこで起動済みのものが渡る。
        """
        # Browsers を import すると management → site の循環になるので、
        # 使う瞬間に読み込む（社内ライブラリの呼び出しと同じ扱い）。
        self._owned = None
        if session is None:
            from .management import Browsers

            owned = Browsers()
            owned.__enter__()
            try:
                session = owned.launch(type(self)).session
            except BaseException:
                # 起動に失敗したら、開きかけのブラウザを残さない
                owned.__exit__(None, None, None)
                raise
            self._owned = owned
        self.session = session

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        """自分で起動したブラウザを閉じる。

        `Browsers.launch()` から作られた場合は**何もしない**。
        そのブラウザの持ち主は `Browsers` の方で、閉じるのもそちらの仕事。
        2回呼んでも安全。
        """
        owned, self._owned = self._owned, None
        if owned is not None:
            owned.__exit__(None, None, None)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.NAME!r})"
