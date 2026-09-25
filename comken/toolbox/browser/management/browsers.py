"""comken/toolbox/browser/management/browsers.py — 複数ブラウザーをまとめて管理する。

公開クラスは ``Browsers``。

このファイルは管理の入口だけを担当する。1つのブラウザーの起動・操作・終了は
``sessions.py`` が担う。

サイトが1つでも複数でも、書き方は変わらない。`SiteBase` サブクラスを `launch` に
渡せば、戻り値から `.session` 経由で BrowserSession に繋がる:

    with Browsers() as browsers:
        kintai = browsers.launch(Kintai)
        data = KintaiFlow(kintai.session).fetch()

サイトを増やすときは launch を1行足すだけでよい:

    with Browsers() as browsers:
        kintai = browsers.launch(Kintai)
        keiri = browsers.launch(Keiri)      # ← 増えるのはこの行だけ

        kintai_data = KintaiFlow(kintai.session).fetch()
        keiri_data = KeiriFlow(keiri.session).fetch()

**書いた順に上から動く（同期）が基本。**

ダウンロードフォルダとログイン状態はセッション名ごとに自動で分かれるので、
サイトを増やしても「どちらのファイルか分からない」状態にならない。
"""

# 定義中の Browsers を戻り値の型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
from contextlib import ExitStack
from pathlib import Path
from types import TracebackType
from typing import Self, TypeVar

from comken.core.timer import measure
from comken.exceptions import BrowserError
from comken.toolbox.browser.download import DownloadDir
from comken.toolbox.browser.management.sessions import BrowserSession
from comken.toolbox.browser.options import BrowserOptions
from comken.toolbox.browser.sitebase import SiteBase

logger = logging.getLogger(__name__)


def _session_name_conflict_error(name: str) -> BrowserError:
    """``BrowserError`` の「同じ名前で2回 launch した」文言。

    発生箇所: Browsers.launch() / Browsers.launch_session()
    """
    return BrowserError(
        f"セッション名が重複しています: {name}\n"
        "1つの Browsers の中で同じ名前は使えません。\n"
        "同じサイトに2つのアカウントでログインする場合は、"
        "「kintai_a」「kintai_b」のように名前を分けてください。"
        "\n対処: 名前を変えてください（同一サイトの別アカウントなら "
        "kintai_a / kintai_b など）。"
    )


def _session_not_found_error(name: str, launched: list[str]) -> BrowserError:
    """``BrowserError`` の「launch していない名前を取り出した」文言。

    発生箇所: Browsers.__getitem__()
    """
    launched_text = "、".join(launched) if launched else "（まだ1つも起動もしていません）"
    return BrowserError(
        f"起動していないセッションです: {name}\n"
        f"起動済み: {launched_text}\n"
        "Browsers.launch(name) で起動してから使ってください。"
        "\n対処: 先に launch してください。エラーに起動済みの一覧が出ます。"
    )


def _browser_not_started_error(operation: str) -> BrowserError:
    """``BrowserError`` の「`with` を使わずにブラウザを操作した」文言。"""
    return BrowserError(
        f"with に入れずに Browsers を使いました: {operation}\n"
        "Browsers は with 文の中でだけ使えます。\n"
        "  with Browsers() as browsers:\n"
        "      kintai = browsers.launch(Kintai)\n"
        "      ...\n"
        "こうしておくと、途中でエラーが出てもブラウザは必ず閉じます。"
        "\n対処: `with Browsers() as browsers:` の中で使ってください"
        "（ブラウザは起動していないので実害はない）。"
    )


def _browser_closed_error(operation: str) -> BrowserError:
    """``BrowserError`` の「`with` を抜けた後のブラウザを操作した」文言。"""
    return BrowserError(
        f"with を抜けた後の Browsers を使いました: {operation}\n"
        "ブラウザはすでに全部閉じています。\n"
        "続けて操作したい処理は with の中に入れてください。\n"
        "with の外へ持ち出すのはブラウザではなく、取り出した値にします。"
        "\n対処: 続けたい処理を `with` の中に入れてください。"
        "外へ持ち出すのは取り出した値だけにしてください。"
    )


def _site_config_error(site_cls: type, missing: str) -> BrowserError:
    """``BrowserError`` の「SiteBase サブクラスの設定が不足している」文言。

    発生箇所: Browsers.launch(SiteBase)
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


# launch() の戻り値を渡したサブクラスの型に合わせるための束縛 TypeVar。
# 素の T だと SiteBase 以外も受理してしまい、束縛しないと pyright が
# launch(Kintai) の戻り値を SiteBase 止まりで推論し、Kintai 固有の
# メソッド（go_login() など）が補完に出なくなる。
S = TypeVar("S", bound=SiteBase)


class Browsers:
    """複数サイト分のブラウザをまとめて起動・終了する。**with 文の中でだけ使える。**

    どこで例外が出ても、起動済みのブラウザはすべて閉じる。
    1つのブラウザの終了に失敗しても、残りの終了は続行される。

    with を使わずに launch すると BrowserError になる（ブラウザは起動しない）。
    with を必須にしているのは、途中で例外が出たときにブラウザのプロセスが残り、
    次の実行でドライバーの更新まで邪魔するのを防ぐため。

    Attributes:
        names: 起動済みのセッション名（起動した順）。
    """

    def __init__(self) -> None:
        self._stack = ExitStack()
        self._sessions: dict[str, BrowserSession] = {}
        self._is_started = False
        self._is_closed = False

    def __enter__(self) -> Self:
        self._stack.__enter__()
        self._is_started = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # 待っている途中で Ctrl+C を押されても、ブラウザだけは必ず閉じる。
        # ここを try/finally にしないと、ブラウザ終了に到達せず Edge のプロセスが残る
        try:
            # ExitStack が起動と逆順にすべてのセッションを閉じる。
            # 途中の終了処理が失敗しても、残りの終了は実行される
            self._stack.__exit__(exc_type, exc_value, traceback)
        finally:
            self._is_closed = True
            self._sessions.clear()

    def launch(
        self,
        site: type[S],
        download_dir: str | Path | None = None,
    ) -> S:
        """サイトクラスを渡してブラウザを1つ起動する（推奨経路）。

        サブクラスの NAME と OPTIONS を読んで、内部で `launch_session()` を
        呼び出す。呼び出し側に「名前」と「オプション」を別々に書かせないことで、
        取り違えが起きにくく、固有の値が1か所に集まる。

        Args:
            site: 起動する SiteBase サブクラス。`NAME` が必須（空だと BrowserError）。
            download_dir: ダウンロード先。省略時は OPTIONS.DOWNLOAD_DIR/<NAME>、
                          それも未設定なら一時フォルダを作り、終了時に削除する。

        Returns:
            起動済みの SiteBase インスタンス。`.session` で BrowserSession に繋がる。

        Raises:
            BrowserError: サブクラスに NAME が設定されていない場合、
                同じ NAME ですでに起動している場合、ブラウザを起動できなかった場合
                （具体的な理由はメッセージに出る）。
        """
        if not site.NAME:
            raise _site_config_error(site, "NAME")
        operation = f"launch({site.__name__})"
        self._require_in_with(operation)
        # OWNER 検査と SITES 衝突検査は SiteBase._check_start() に集約。
        # `with SiteBase()` 経由とここ（Browsers.launch() 経由）の両方から同じ検証が走る。
        # `with` の中であることが確かめてから動かす（外のときに OWNER 不足を言うのは筋が違う）
        site._check_start()
        session = self.launch_session(site.NAME, site.OPTIONS, download_dir)
        instance = site(session)
        # SitePage.BASE_URL が未設定のときの参照先。launch_session() から直接
        # 起動したセッションには紐付かない（SiteBase 経由で起動したときだけ設定する）
        session._site = instance
        # 起動成功後に1回だけ INFO ログを出す。`with SiteBase()` 経路は
        # SiteBase.__enter__() 経由でログを出すため、ここは通らない
        site._log_started()
        return instance

    @measure
    def launch_session(
        self,
        name: str,
        options: type[BrowserOptions] | BrowserOptions | None = None,
        download_dir: str | Path | None = None,
    ) -> BrowserSession:
        """名前とオプションを直接渡してブラウザを1つ起動する（低レベル経路）。

        `launch(SiteBase)` の中から呼ばれる雑務用。SiteBase サブクラスが用意できない
        場面（テスト・一時的な検証）で使う。通常は `launch(SiteBase)` を使う。

        ダウンロードフォルダとログイン状態はこの名前ごとに分かれる。
        同じサイトへ2つのアカウントでログインしたい場合も、
        「kintai_a」「kintai_b」と名前を分ければ混ざらない。

        Args:
            name: セッション名。ログとエラーメッセージに出るので、
                  「kintai」「keiri」のようにサイトが分かる名前にする。
            options: 起動オプション。BrowserOptions のサブクラスをそのまま渡せる
                     （セッションごとに別インスタンスを作るので、設定が混ざらない）。
                     省略時は BrowserOptions の初期値で起動する。
            download_dir: ダウンロード先。省略時は options.DOWNLOAD_DIR/<name>、
                          それも未設定なら一時フォルダを作り、終了時に削除する。

        Returns:
            起動済みの BrowserSession。この with を抜けるまで使える。

        Raises:
            BrowserError: 同じ名前ですでに起動している場合、
                ブラウザを起動できなかった場合（具体的な理由はメッセージに出る）。
        """
        self._require_in_with(f"launch_session({name!r})")
        if name in self._sessions:
            raise _session_name_conflict_error(name)

        logger.debug("ブラウザセッション起動開始: %s", name)
        resolved_options = _resolve_options(options)
        session = BrowserSession(
            name=name,
            options=resolved_options,
            download_dir=_resolve_download_dir(name, resolved_options, download_dir),
            profile_dir=_resolve_profile_dir(name, resolved_options),
        )

        # ExitStack に預けた時点で、この with を抜けるときの終了が保証される
        self._stack.enter_context(session)
        self._sessions[name] = session
        logger.debug("ブラウザセッション起動完了: %s", name)
        return session

    @property
    def names(self) -> list[str]:
        """起動済みのセッション名（起動した順）。"""
        return list(self._sessions)

    def __getitem__(self, name: str) -> BrowserSession:
        """名前でセッションを取り出す（browsers["kintai"] のように書ける）。

        launch の戻り値を変数に入れておけば普通は不要。
        処理を関数へ切り出したときに、引数を増やさず取り出すためにある。
        """
        self._require_in_with(f"browsers[{name!r}]")
        if name not in self._sessions:
            raise _session_not_found_error(name, self.names)
        return self._sessions[name]

    def _require_in_with(self, operation: str) -> None:
        """with の中で使われているかを確かめる。

        with を使わないと、途中で例外が出たときにブラウザのプロセスが残り続ける。
        起動してしまう前にここで止めるので、弾かれた時点では何も起きていない。

        Raises:
            BrowserError: with に入れずに使った場合、または with を抜けた後に使った場合
                （具体的な理由はメッセージに出る）。
        """
        if self._is_closed:
            raise _browser_closed_error(operation)
        if not self._is_started:
            raise _browser_not_started_error(operation)

    def __repr__(self) -> str:
        launched = "、".join(self.names) if self._sessions else "なし"
        return f"Browsers(起動済み: {launched})"


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
