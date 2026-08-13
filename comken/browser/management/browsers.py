"""comken/browser/management/browsers.py — 複数ブラウザーをまとめて管理する公開クラス ``Browsers``。

このファイルは管理の入口だけを担当する。1つのブラウザーの起動・操作・終了は
``sessions.py``、バックグラウンド処理の結果管理は ``tasks.py`` が担う。

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

**書いた順に上から動く（同期）のが基本。** 待っている間に別のことを進めたいときだけ、
start() で先に始めておき、結果が必要になったところで wait() で受け取る:

        勤怠 = browsers.start(lambda: KintaiFlow(kintai).fetch())  # 始めるだけ。待たない
        keiri_data = KeiriFlow(keiri).fetch()                      # その間にこちらを進める
        kintai_data = 勤怠.wait()                                  # 戻って結果を受け取る

重い画面の読み込みを待っている間、ブラウザは何も消費していないので、
その時間で別のサイトの操作が進む。読み込みが終われば、そちらも自分で続きを始める。

全部まとめて同時に始めて、全部の結果を受け取るだけなら parallel で短く書ける
（start して wait するのと同じことをしている）:

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

from comken.exceptions import (
    BrowsersClosedError,
    BrowsersNotStartedError,
    SessionNameConflictError,
    SessionNotFoundError,
)

from ..download import DownloadDir
from ..options import BrowserOptions
from .sessions import BrowserSession
from .tasks import BackgroundTask

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 裏で動かす処理の同時実行数の上限。ブラウザ操作は待ち時間がほとんどで
# CPU を使わないため、サイト数として現実的な範囲を確保しておけばよい
_MAX_BACKGROUND_TASKS = 16


class Browsers:
    """複数サイト分のブラウザをまとめて起動・終了する。**with 文の中でだけ使える。**

    どこで例外が出ても、起動済みのブラウザはすべて閉じる。
    1つのブラウザの終了に失敗しても、残りの終了は続行される。

    with を使わずに launch すると BrowsersNotStartedError になる（ブラウザは起動しない）。
    with を必須にしているのは、途中で例外が出たときにブラウザのプロセスが残り、
    次の実行でドライバーの更新まで邪魔するのを防ぐため。

    **start() で始めた処理が終わらないと、with も終わらない。** ブラウザを閉じる前に
    裏の処理の終了を待つため（操作の途中でブラウザが消えると原因が分かりにくいエラーになる）。
    終わらない可能性がある処理には、その中で待ち時間の上限を設けること。

    Attributes:
        names: 起動済みのセッション名（起動した順）。
    """

    def __init__(self) -> None:
        self._stack = ExitStack()
        self._sessions: dict[str, BrowserSession] = {}
        self._executor: ThreadPoolExecutor | None = None
        self._tasks: list[BackgroundTask] = []
        # 既定の名前（処理1、処理2 …）の連番。回収済みを捨てても番号が戻らないよう、
        # リストの長さではなく開始した総数で数える
        self._started_count = 0
        self._is_started = False
        self._is_closed = False

    def __enter__(self) -> "Browsers":
        self._stack.__enter__()
        self._is_started = True
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # 待っている途中で Ctrl+C を押されても、ブラウザだけは必ず閉じる。
        # ここを try/finally にしないと、待ち合わせで例外が飛んだ時点で
        # 下のブラウザ終了に到達せず、Edge のプロセスが残る
        try:
            # ブラウザを閉じる前に、裏で動いている処理の終了を待つ。
            # 先に閉じると、操作の途中でブラウザが消えて追いにくいエラーになる
            self._finish_background_tasks()
        finally:
            # 裏の処理が終わってから閉じたことにする。先に閉じたことにすると、
            # 動き出すのが遅れたタスクが browsers[...] を使えなくなる
            self._is_closed = True
            try:
                # ExitStack が起動と逆順にすべてのセッションを閉じる。
                # 途中の終了処理が失敗しても、残りの終了は実行される
                self._stack.__exit__(exc_type, exc_value, traceback)
            finally:
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
        self._require_in_with(f"launch({name!r})")
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

    def start(self, task: Callable[[], T], label: str = "") -> BackgroundTask[T]:
        """処理を裏で始めて、すぐ次の行へ進む。結果は wait() で受け取る。

        普通に書けば上から順に動く。時間のかかる処理を待っている間に
        別のことを進めたいときだけ、これで先に始めておく:

            勤怠 = browsers.start(lambda: KintaiFlow(kintai).search())
            KeiriFlow(keiri).login(user, password)   # 勤怠の読み込み中にこちらが進む
            days = 勤怠.wait()                        # 戻って結果を受け取る

        **裏で動かす処理と、その後に自分で書く処理で、同じセッションを触らないこと。**
        同じセッションを同時に触ると ConcurrentSessionUseError で止まる
        （黙って別の画面を操作するより、早く気づけるほうが安全なため）。

        Args:
            task: 引数を取らない呼び出し可能オブジェクト。lambda で包んで渡す。
            label: 何の処理か。省略するとセッション名の代わりに連番が付く。
                   ログとエラーメッセージに出るので、付けておくと原因を追いやすい。

        Returns:
            結果を受け取るための取っ手。wait() で結果、is_done で終了確認ができる。
        """
        self._require_in_with("start")
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=_MAX_BACKGROUND_TASKS, thread_name_prefix="browser"
            )

        # 受け取り済みのものは手放す。ここで捨てないと、繰り返し start する処理で
        # 結果や例外の情報を持ったまま溜まり続ける。
        # 未回収のものは、終了時に報告するために残す
        self._tasks = [pending for pending in self._tasks if not pending.is_collected]

        name = label or f"処理{self._started_count + 1}"
        self._started_count += 1
        background_task = BackgroundTask(self._executor.submit(task), name)
        self._tasks.append(background_task)
        logger.debug("裏で開始しました: %s", name)
        return background_task

    def parallel(self, *tasks: Callable[[], T]) -> list[T]:
        """複数の処理を同時に始めて、全部終わるまで待ち、渡した順に結果を返す。

        start() で始めて wait() で受け取るのを、まとめて書けるようにしたもの。
        「全部同時に始めて、全部の結果が欲しい」だけならこちらが短い:

            # 逐次（上から順に動く）
            a = KintaiFlow(kintai).fetch()
            b = KeiriFlow(keiri).fetch()

            # 同時（同じ呼び出しを lambda で包む）
            a, b = browsers.parallel(
                lambda: KintaiFlow(kintai).fetch(),
                lambda: KeiriFlow(keiri).fetch(),
            )

        受け取るタイミングを自分で決めたい場合は start() を使う。

        1つの処理では1つのセッションだけを触ること。同じセッションを2つの処理から
        触ると ConcurrentSessionUseError で止まる。

        Args:
            *tasks: 引数を取らない呼び出し可能オブジェクト。

        Returns:
            各処理の戻り値を、渡した順に並べたリスト。

        Raises:
            Exception: いずれかの処理で発生した例外。複数失敗した場合は、
                       すべてをログに出したうえで、引数の並び順で最初に失敗したものを送出する
                       （時間的に最初に失敗したものとは限らない）。
        """
        self._require_in_with("parallel")
        if not tasks:
            return []

        started = [self.start(task, label=f"処理{index + 1}") for index, task in enumerate(tasks)]

        # 例外が出ても、走り出した処理は最後まで待つ。
        # 途中で打ち切るとブラウザを操作中のまま放置することになるため
        results: list[T] = []
        errors: list[Exception] = []
        for background_task in started:
            try:
                results.append(background_task.wait())
            except Exception as exc:
                logger.error("「%s」が失敗しました: %s", background_task.label, exc)
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
        self._require_in_with(f"browsers[{name!r}]")
        if name not in self._sessions:
            raise SessionNotFoundError(name, self.names)
        return self._sessions[name]

    def _require_in_with(self, operation: str) -> None:
        """with の中で使われているかを確かめる。

        with を使わないと、途中で例外が出たときにブラウザのプロセスが残り続ける。
        起動してしまう前にここで止めるので、弾かれた時点では何も起きていない。

        Raises:
            BrowsersNotStartedError: with に入れずに使った場合。
            BrowsersClosedError: with を抜けた後に使った場合。
        """
        if self._is_closed:
            raise BrowsersClosedError(operation)
        if not self._is_started:
            raise BrowsersNotStartedError(operation)

    def _finish_background_tasks(self) -> None:
        """裏で動いている処理の終了を待ってから、実行の仕組みを片付ける。

        待ち時間に上限は設けない。処理の途中でブラウザを閉じるより、
        終わるまで待つほうが安全なため（終わらない処理があると with も終わらない）。

        wait() を呼ばずに with を抜けた処理があると、その中で起きた例外は
        誰にも渡らない。黙って消えると原因調査ができないため、ここでログに出す。
        """
        if self._executor is None:
            return

        self._executor.shutdown(wait=True)
        for background_task in self._tasks:
            if background_task.is_collected:
                continue
            try:
                background_task.wait(timeout=0)
                logger.warning(
                    "「%s」の結果が受け取られないまま終了しました（wait の呼び忘れ）",
                    background_task.label,
                )
            except Exception as exc:
                logger.error(
                    "「%s」が失敗していました（wait で受け取られないまま終了）: %s",
                    background_task.label,
                    exc,
                )

        self._executor = None
        self._tasks.clear()

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
