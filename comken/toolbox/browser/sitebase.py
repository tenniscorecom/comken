r"""comken/toolbox/browser/sitebase.py — サイトを表す SiteBase 基底クラス。

1サイトにつき1クラスを作って、固有の値をそこに集める。設計の骨格は
`comken.toolbox.salesforce.SalesforceBase` と同じ。読み書き両方を知っていれば、
片方は形だけで分かる。

ダウンロードフォルダとログイン状態はブラウザ単位で決まるので、1サイトなら
``with Kintai() as kintai:``、複数サイトなら with を並べるだけで足りる:

    from comken.toolbox.browser import SiteBase

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

    # 複数サイトは with を並べるだけ
    with Kintai() as kintai, Keiri() as keiri:
        unfilled = kintai.go_login().login(USER, PW).unfilled_days()
        pending = keiri.go_login().login(USER, PW).pending_rows()

    # 同じサイトを2アカウントで同時ログインするときは name= でセッション名を分ける
    with Kintai(name="kintai_a") as a, Kintai(name="kintai_b") as b:
        a_admin = a.go_login().login(ADMIN_USER, ADMIN_PW)
        b_staff = b.go_login().login(STAFF_USER, STAFF_PW)
"""

# 定義中（クラス内）の BrowserSession を型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, ClassVar, Self, TypeVar

from comken.exceptions import BrowserError, SiteOwnerRequiredError
from comken.toolbox.browser.download import DownloadDir
from comken.toolbox.browser.options import BrowserOptions

if TYPE_CHECKING:
    from comken.toolbox.browser.management import BrowserSession
    from comken.toolbox.browser.page import Page

# page() が「渡したクラスをそのまま返す」ことを型で示す。
# これがないと補完が Page 止まりになり、画面ごとのメソッドが出ない
P = TypeVar("P", bound="Page")

# comken 配下のクラスは OWNER 検査の対象外（管理者が既に昇格を判断した印）。
# 検査する側の classmethod とこの定数を同じ場所に置いて、意味のずれを防ぐ
_COMKEN_MODULE_PREFIX = "comken."

# 起動中のセッション名を覚える集合。SiteBase.__enter__ で登録し、
# __exit__ / close() で必ず解除する（失敗しても名前は残さない）
_ACTIVE_SESSION_NAMES: set[str] = set()

logger = logging.getLogger(__name__)


def _session_name_conflict_error(name: str) -> BrowserError:
    """``BrowserError`` の「同じセッション名で2つ起動した」文言。

    発生箇所: SiteBase.__enter__()
    """
    return BrowserError(
        f"セッション名が重複しています: {name}\n"
        "同じプロセス内で同じ名前のセッションを2つ同時に開くことはできません。\n"
        "同じサイトに2つのアカウントでログインする場合は、"
        "name= で別名を付けてください。\n"
        '  例: with Kintai(name="kintai_a") as a, Kintai(name="kintai_b") as b:\n'
        '\n対処: name="kintai_a" / name="kintai_b" のように名前を分けるか、'
        "どちらかを with の外に出して時間差で使ってください。"
    )


def _site_config_error(site_cls: type, missing: str) -> BrowserError:
    """``BrowserError`` の「SiteBase サブクラスの設定が不足している」文言。

    発生箇所: SiteBase.__enter__()
    """
    return BrowserError(
        f"{site_cls.__name__} に {missing} が設定されていません。\n"
        "SiteBase サブクラスでは、次のクラス定数を決めてください:\n"
        f"  class {site_cls.__name__}(SiteBase):\n"
        f"      {missing} = ...\n"
        "  NAME      セッション名（ログ・ダウンロード先で使われる）\n"
        "  BASE_URL  このサイトの入口 URL（SitePage から参照される）\n"
        "  OPTIONS   起動オプション（BrowserOptions のサブクラス）"
        "\n対処: サブクラスに NAME を定義してください"
        "（BASE_URL / OPTIONS も同じ）。"
    )


def _site_not_started_error(instance: SiteBase) -> BrowserError:
    """``BrowserError`` の「SiteBase を起動前に操作した」文言。"""
    return BrowserError(
        f"{instance.__class__.__name__} はまだ起動していません。"
        f"`with {instance.__class__.__name__}() as site:` の中で使ってください。"
        "\n対処: `with SiteBase() as site:` の中で使ってください"
        "（ブラウザは起動していないので実害はない）。"
    )


def _site_already_in_library_error(site_cls: type, library_cls: type) -> BrowserError:
    """``BrowserError`` の「ライブラリ公認のサイトと同じ NAME を再定義した」文言。

    発生箇所: SiteBase.__enter__()
    """
    return BrowserError(
        f'{site_cls.__name__}（NAME="{site_cls.NAME}"）はライブラリにすでに登録されています: '
        f"{library_cls.__module__}.{library_cls.__name__}\n"
        "ライブラリ公認のクラスを取り出して使う形に書き換えてください:\n"
        f"  from {library_cls.__module__} import {library_cls.__name__}\n"
        f"  with {library_cls.__name__}() as site:\n"
        "プロジェクト側に独自実装を残したい場合は、クラス名と NAME を別のものへ変えてください。"
        "\n対処: ライブラリから `from comken.toolbox.browser.sites import <クラス名>` で"
        "取り出して使ってください。プロジェクト側の定義は消してください。"
        "ライブラリへ昇格する基準は `docs/CONVENTIONS.md` の"
        "「サイト／組織クラスを昇格させる基準」を参照。"
    )


def _resolve_options(
    options: type[BrowserOptions] | BrowserOptions | None,
) -> BrowserOptions:
    """options 引数を BrowserOptions のインスタンスに揃える。

    クラスで渡された場合はここでインスタンス化する。セッションごとに別インスタンスにして、
    片方のセッションの設定変更がもう片方へ伝わらないようにするため。
    """
    if options is None:
        return BrowserOptions()
    if isinstance(options, type):
        return options()
    return options


def _resolve_download_dir(
    name: str,
    options: BrowserOptions,
    download_dir: str | Path | None,
) -> DownloadDir:
    """このセッション専用のダウンロードフォルダを決める。

    options.DOWNLOAD_DIR をそのまま全セッションで共有すると、
    どのサイトから落ちたファイルか分からなくなるため、名前ごとのサブフォルダに分ける。
    引数で明示された場合だけは、指定どおりのフォルダをそのまま使う。
    """
    if download_dir is not None:
        return DownloadDir(path=download_dir)
    if options.DOWNLOAD_DIR:
        return DownloadDir(path=Path(options.DOWNLOAD_DIR) / name)
    return DownloadDir(prefix=f"comken_{name}_")


def _resolve_profile_dir(name: str, options: BrowserOptions) -> Path | None:
    """ログイン状態を残すフォルダを決める。PROFILE_ROOT 未設定なら None。

    同じフォルダを2つの Edge が同時に開くと起動に失敗するため、
    必ず名前ごとのサブフォルダに分ける。

    **必ず絶対パスにする。** ``--user-data-dir`` に相対パスを渡すと、
    msedge.exe 側の作業ディレクトリが Python の実行時カレントディレクトリと
    一致しない場合にプロファイルの初期化に失敗し、Selenium 側には
    「Edge のバージョンが合わない」という紛らわしいメッセージで
    BrowserError になる（実際はバージョンではなくパスの問題）。
    """
    if not options.PROFILE_ROOT:
        return None

    profile_dir = (Path(options.PROFILE_ROOT) / name).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    logger.info("ログイン状態を引き継ぎます: %s", profile_dir)
    return profile_dir


class SiteBase:
    """1サイト分の入口。サイトごとにサブクラスを作って固有の値を置く。

    サブクラスで NAME / BASE_URL / OPTIONS / OWNER を上書きする。`session` 以外の状態
    （current_url や cookie など）は持たない — 同じサイトを2アカウントで並列に
    開けるようにするため。

    使い方は ``with Kintai() as kintai:`` だけ。複数サイトは with を並べればよい。

    Args:
        name: セッション名の上書き。省略時は ``NAME`` が使われる。
              ダウンロードフォルダ・ログイン状態はセッション名ごとに分かれるので、
              同じサイトを2アカウントで開くときは ``name="kintai_a"`` のように分ける。
        download_dir: ダウンロード先の固定パス。``None`` のときは
                      ``OPTIONS.DOWNLOAD_DIR/<セッション名>``、
                      これも未設定なら一時フォルダになる（一時フォルダは with を
                      抜けると自動削除）。

    Attributes:
        session: このサイトに紐づく BrowserSession。Page に渡して操作する。
    """

    # ログ・ダウンロード先・ログイン状態の分け方の鍵
    NAME: ClassVar[str] = ""
    # 画面の BASE_URL にそのまま使える。SitePage.BASE_URL が無ければこれが使われる
    BASE_URL: ClassVar[str] = ""
    # 起動オプション。クラスで渡す（セッションごとに別インスタンスが作られる）
    OPTIONS: ClassVar[type[BrowserOptions] | None] = None
    # 「どのプロジェクト／誰が継承して作ったか」を示す識別子。同じ社内システムの
    # クラスが複数プロジェクトで重複していないかを、ライブラリ管理者が
    # 把握するために使う。comken 配下に置くクラスは OWNER = "comken" にする。
    OWNER: ClassVar[str] = ""

    def __init__(
        self,
        name: str | None = None,
        *,
        download_dir: str | Path | None = None,
    ) -> None:
        # name=None のときは __enter__ で NAME を使うので、ここでは記録するだけ
        self._explicit_name = name
        self._explicit_download_dir = download_dir
        self.session: BrowserSession | None = None
        # 自分用に起動した BrowserSession。close() で閉じるかどうかの判定に使う
        self._owned_session: BrowserSession | None = None

    def __enter__(self) -> Self:
        from comken.toolbox.browser.management import BrowserSession

        session_name = self._explicit_name if self._explicit_name is not None else self.NAME
        if not session_name:
            raise _site_config_error(self.__class__, "NAME")
        type(self)._check_start()

        if session_name in _ACTIVE_SESSION_NAMES:
            raise _session_name_conflict_error(session_name)

        resolved_options = _resolve_options(self.OPTIONS)
        download_dir = _resolve_download_dir(
            session_name, resolved_options, self._explicit_download_dir
        )
        profile_dir = _resolve_profile_dir(session_name, resolved_options)

        logger.debug("ブラウザセッション起動開始: %s", session_name)
        session = BrowserSession(
            name=session_name,
            options=resolved_options,
            download_dir=download_dir,
            profile_dir=profile_dir,
        )
        # 起動が成功した後に名前を登録する。__enter__ が例外で抜けたときは
        # 登録していないので、集合にも残らない（二重登録・名前残りを起こさない）
        session.__enter__()
        _ACTIVE_SESSION_NAMES.add(session_name)
        self.session = session
        self._owned_session = session
        # SitePage.BASE_URL が未設定のときの参照先。with から直接起動したのでここで結びつける
        session._site = self
        # 起動成功後に1回だけ INFO ログを出す
        type(self)._log_started()
        logger.debug("ブラウザセッション起動完了: %s", session_name)
        return self

    @classmethod
    def _check_start(cls) -> None:
        """起動時に1回だけ行う検証（OWNER 必須とライブラリ公認サイトとの NAME 衝突）。

        comken 配下のクラスは検査対象外（管理者が既に判断した印）。
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

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._release_session(exc_type, exc_val, exc_tb)

    def close(self) -> None:
        """自分で起動したブラウザだけ閉じる。

        `with Kintai() as kintai:` で起動したインスタンスを `close()` しても安全。
        2回呼んでも安全（何もしないだけ）。
        """
        self._release_session(None, None, None)

    def _release_session(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """ブラウザを閉じて名前集合を解除する。

        起動成功後に登録した名前を必ず解除する（途中で例外が出ても残さない）。
        _owned_session を None にすれば2回目以降は何もしない（二重解除にならない）。
        """
        session = self._owned_session
        if session is None:
            self.session = None
            return
        self._owned_session = None
        try:
            session.__exit__(exc_type, exc_val, exc_tb)
        finally:
            # 解除はブラウザ終了の成功失敗に関わらず必ず行う
            _ACTIVE_SESSION_NAMES.discard(session.name)
            self.session = None

    @property
    def downloads(self) -> DownloadDir:
        """このサイトのダウンロード先。完了待ちに使う。

            files = kintai.downloads.wait()   # .crdownload が消えるまで待つ

        Raises:
            BrowserError: まだ起動していない場合。
        """
        if self.session is None:
            raise _site_not_started_error(self)
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
            raise _site_not_started_error(self)
        return page_class(self.session)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.NAME!r})"


def _check_not_in_library(cls: type[SiteBase]) -> None:
    """起動しようとしているクラスと同じ NAME がライブラリ公認サイトにあれば止める。

    ライブラリに同じ NAME のクラスがあるなら、プロジェクト側で再定義するのではなく
    ライブラリから import して使う形に直してほしい。`BrowserError` で
    「取り出して使う import パス」まで案内する。
    """
    # 循環 import 回避のため、ここで import する（`site.py` が `sites` を import する形になる）
    from comken.toolbox.browser.sites import SITES

    for library_cls in SITES:
        if library_cls.NAME == cls.NAME:
            raise _site_already_in_library_error(cls, library_cls)
