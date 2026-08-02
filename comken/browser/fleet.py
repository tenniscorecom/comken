"""Browsers — サイトごとのブラウザをまとめて管理する。

サイトが1つでも複数でも、書き方は変わらない:

    with Browsers() as browsers:
        kintai = browsers.launch("kintai", KintaiOptions)
        data = KintaiFlow(kintai).fetch()

サイトを増やすときは launch を1行足すだけでよい:

    with Browsers() as browsers:
        kintai = browsers.launch("kintai", KintaiOptions)
        keiri = browsers.launch("keiri", KeiriOptions)      # ← 増えるのはこの行だけ

        kintai_data = KintaiFlow(kintai).fetch()
        keiri_data = KeiriFlow(keiri).fetch()

同時に走らせたくなったら、上の呼び出しを lambda で包むだけで並列になる:

        kintai_data, keiri_data = browsers.parallel(
            lambda: KintaiFlow(kintai).fetch(),
            lambda: KeiriFlow(keiri).fetch(),
        )

ダウンロードフォルダとログイン状態はセッション名ごとに自動で分かれるので、
サイトを増やしても「どちらのファイルか分からない」状態にならない。
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from typing import TypeVar

from comken.exceptions import SessionNameConflictError, SessionNotFoundError

from .download import DownloadDir
from .options import BrowserOptions
from .session import BrowserSession

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Browsers:
    """複数サイト分のブラウザをまとめて起動・終了する。with 文の中で使う。

    どこで例外が出ても、起動済みのブラウザはすべて閉じる。
    1つのブラウザの終了に失敗しても、残りの終了は続行される。

    Attributes:
        names: 起動済みのセッション名（起動した順）。
    """

    def __init__(self) -> None:
        self._stack = ExitStack()
        self._sessions: dict[str, BrowserSession] = {}

    def __enter__(self) -> "Browsers":
        self._stack.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # ExitStack が起動と逆順にすべてのセッションを閉じる。
        # 途中の終了処理が失敗しても、残りの終了は実行される
        self._stack.__exit__(exc_type, exc_value, traceback)
        self._sessions.clear()

    def launch(
        self,
        name: str,
        options: "type[BrowserOptions] | BrowserOptions | None" = None,
        download_dir: "str | Path | None" = None,
    ) -> BrowserSession:
        """名前を付けてブラウザを1つ起動する。

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
            SessionNameConflictError: 同じ名前ですでに起動している場合。
            DriverStartError: ブラウザを起動できなかった場合。
        """
        if name in self._sessions:
            raise SessionNameConflictError(name)

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
        return session

    def parallel(self, *tasks: Callable[[], T]) -> list[T]:
        """複数の処理を同時に走らせ、渡した順に結果を返す。

        逐次で書いたコードを lambda で包むだけで並列になる:

            # 逐次
            a = KintaiFlow(kintai).fetch()
            b = KeiriFlow(keiri).fetch()

            # 並列（同じ呼び出しを lambda で包む）
            a, b = browsers.parallel(
                lambda: KintaiFlow(kintai).fetch(),
                lambda: KeiriFlow(keiri).fetch(),
            )

        1つの処理では1つのセッションだけを触ること。同じセッションを2つの処理から
        触ると ConcurrentSessionUseError で止まる（黙って壊れるより早く気づけるように、
        待たずにエラーにしている）。

        Args:
            *tasks: 引数を取らない呼び出し可能オブジェクト。

        Returns:
            各処理の戻り値を、渡した順に並べたリスト。

        Raises:
            Exception: いずれかの処理で発生した例外。複数失敗した場合は、
                       すべてをログに出したうえで最初の1つを送出する。
        """
        if not tasks:
            return []

        with ThreadPoolExecutor(max_workers=len(tasks), thread_name_prefix="browser") as executor:
            # 例外が出ても、走り出した処理は最後まで待つ。
            # 途中で打ち切るとブラウザを操作中のまま放置することになるため
            futures = [executor.submit(task) for task in tasks]
            results: list[T] = []
            errors: list[Exception] = []
            for index, future in enumerate(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    logger.error("並列処理の %d 番目が失敗しました: %s", index + 1, exc)
                    errors.append(exc)

        if errors:
            raise errors[0]
        return results

    @property
    def names(self) -> list[str]:
        """起動済みのセッション名（起動した順）。"""
        return list(self._sessions)

    def __getitem__(self, name: str) -> BrowserSession:
        """名前でセッションを取り出す（browsers["kintai"] のように書ける）。

        launch の戻り値を変数に入れておけば普通は不要。
        処理を関数へ切り出したときに、引数を増やさず取り出すためにある。
        """
        if name not in self._sessions:
            raise SessionNotFoundError(name, self.names)
        return self._sessions[name]

    def __repr__(self) -> str:
        launched = "、".join(self.names) if self._sessions else "なし"
        return f"Browsers(起動済み: {launched})"


def _resolve_options(
    options: "type[BrowserOptions] | BrowserOptions | None",
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
    download_dir: "str | Path | None",
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
    """
    if not options.PROFILE_ROOT:
        return None

    profile_dir = Path(options.PROFILE_ROOT) / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    logger.info("ログイン状態を引き継ぎます: %s", profile_dir)
    return profile_dir
