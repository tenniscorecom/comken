r"""comken/toolbox/browser/sitebase.py — サイトを表す SiteBase 基底クラス。

1サイトにつき1クラスを作って、固有の値をそこに集める。設計の骨格は
`comken.toolbox.salesforce.SalesforceBase` と同じ。読み書き両方を知っていれば、
片方は形だけで分かる。

1サイトだけ触るツールでは `with Kintai() as kintai:` で完結する。複数サイトを
扱うときは `with Browsers() as browsers: kintai = browsers.launch(Kintai)`。
どちらの出口でも SiteBase インスタンスが返り、`.session` で BrowserSession に繋がる。

    from comken.toolbox.browser import Browsers, SiteBase

    class Kintai(SiteBase):
        NAME = "kintai"
        BASE_URL = "https://kintai.example.co.jp"
        OWNER = "勤怠 / 小栗"

        # 起動オプションは既定のままでよければ OPTIONS を書かなくてよい。
        # 変えたいときだけ BrowserOptions のサブクラスをこのファイルに作って
        # OPTIONS = 〇〇 を置く（書ける項目は print(BrowserOptions()) で一覧できる）
        # OPTIONS = KintaiOptions

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

import logging
from typing import TYPE_CHECKING, ClassVar, Self, TypeVar

from comken.exceptions import (
    SiteAlreadyInLibraryError,
    SiteConfigError,
    SiteNotStartedError,
    SiteOwnerRequiredError,
)
from comken.toolbox.browser.download import DownloadDir
from comken.toolbox.browser.options import BrowserOptions

if TYPE_CHECKING:
    from comken.toolbox.browser.management import Browsers, BrowserSession
    from comken.toolbox.browser.page import Page

# page() が「渡したクラスをそのまま返す」ことを型で示す。
# これがないと補完が Page 止まりになり、画面ごとのメソッドが出ない
P = TypeVar("P", bound="Page")

# comken 配下のクラスは OWNER 検査の対象外（管理者が既に昇格を判断した印）。
# 検査する側の classmethod とこの定数を同じ場所に置いて、意味のずれを防ぐ
_COMKEN_MODULE_PREFIX = "comken."

logger = logging.getLogger(__name__)


class SiteBase:
    """1サイト分の入口。サイトごとにサブクラスを作って固有の値を置く。

    サブクラスで NAME / BASE_URL / OPTIONS / OWNER を上書きする。`session` 以外の状態
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
    # 「どのプロジェクト／誰が継承して作ったか」を示す識別子。同じ社内システムの
    # クラスが複数プロジェクトで重複していないかを、ライブラリ管理者が
    # 把握するために使う。comken 配下に置くクラスは OWNER = "comken" にする。
    OWNER: ClassVar[str] = ""

    def __init__(self, session: BrowserSession | None = None) -> None:
        self.session = session
        # 自分で起動した Browsers（with Kintai() 経由）。Browsers から持ってきた
        # ときは None のままにして、`close()` で持ち物を閉じてしまわないように区別する
        self._browsers: Browsers | None = None

    def __enter__(self) -> Self:
        # 循環インポートを避けるため、使う直前に取り出す
        from comken.toolbox.browser.management import Browsers

        if not self.NAME:
            raise SiteConfigError(self.__class__, "NAME")
        type(self)._check_start()
        self._browsers = Browsers()
        self._browsers.__enter__()
        session = self._browsers.launch_session(self.NAME, self.OPTIONS)
        self.session = session
        # SitePage.BASE_URL が未設定のときの参照先。launch_session() からは
        # 設定されないので、ここで結びつける
        session._site = self
        # 起動成功後に1回だけ INFO ログを出す。`Browsers.launch()` 経路と
        # この経路のどちらでも同じログが1行だけ出る（Browsers.launch() は
        # launch_session() を直接呼ぶため、ここは通らない）
        type(self)._log_started()
        return self

    @classmethod
    def _check_start(cls) -> None:
        """起動時に1回だけ行う検証（OWNER 必須とライブラリ公認サイトとの NAME 衝突）。

        `with SiteBase()` 経路と `Browsers.launch()` 経路の両方から共有するために
        1か所にまとめる。comken 配下のクラスは検査対象外（管理者が既に判断した印）。
        起動 INFO ログは出さない。ログは起動が成功した後 `_log_started()` で
        1回だけ出す（ここで出すと起動失敗のときに「使った」という嘘のログが残る）。
        """
        if cls.__module__.startswith(_COMKEN_MODULE_PREFIX):
            return
        if not cls.OWNER:
            raise SiteOwnerRequiredError(cls, "SiteBase")
        _check_not_in_library(cls)

    @classmethod
    def _log_started(cls) -> None:
        """起動が成功した後に1回だけ出す INFO ログ。

        検証 (`_check_start()`) とは分けて、起動の入口ではなく出口に置く。
        ブラウザの起動や NAME 衝突が失敗したらログは出ない（5xx をリトライしたと
        計測しながら実際にはやり直していなかった反省をここで踏まないため）。
        comken 配下のクラスは免除の判定を `_check_start()` と共有し、ログも
        出さない（管理者が把握済みのものを毎回流しても情報が増えないため）。
        """
        if cls.__module__.startswith(_COMKEN_MODULE_PREFIX):
            return
        logger.info("site=%s owner=%s defined=%s", cls.NAME, cls.OWNER, cls.__module__)

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

            def go_login(self) -> LoginPage:
                return self.to(LoginPage).go("/login")

        **行き先の型を切り替えるだけで、ブラウザは動かさない。** 実際に動かすのは
        `Page.go("/path")` かリンクのクリックで、それを `go_〇〇()` の中に隠す。
        こうしておくと、その画面から行ける先が `go_〇〇()` の一覧になる。

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


def _check_not_in_library(cls: type[SiteBase]) -> None:
    """起動しようとしているクラスと同じ NAME がライブラリ公認サイトにあれば止める。

    ライブラリに同じ NAME のクラスがあるなら、プロジェクト側で再定義するのではなく
    ライブラリから import して使う形に直してほしい。`SiteAlreadyInLibraryError` で
    「取り出して使う import パス」まで案内する。
    """
    # 循環 import 回避のため、ここで import する（`site.py` が `sites` を import する形になる）
    from comken.toolbox.browser.sites import SITES

    for library_cls in SITES:
        if library_cls.NAME == cls.NAME:
            raise SiteAlreadyInLibraryError(cls, library_cls)
