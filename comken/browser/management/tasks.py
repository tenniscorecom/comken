"""comken/browser/management/tasks.py — 非同期処理の結果を保持するタスク。

スレッドの起動やブラウザーの管理は行わず、結果・例外・受取済み状態だけを管理する。

ブラウザ操作は基本的に上から順に動く（同期）。
重い画面の読み込みなど、待っている間に別のことを進めたいときだけ、
Browsers.run_task() で始めて、必要になったところで wait() で受け取る。

    勤怠 = browsers.run_task(lambda: KintaiFlow(kintai).search())  # 始めるだけ
    KeiriFlow(keiri).login(user, password)                      # その間に別サイトを進める
    days = 勤怠.wait()                                          # 戻って結果を受け取る

このクラスを直接作らない。Browsers.run_task() が返すものを受け取って使う。
"""

import logging
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BackgroundTask(Generic[T]):
    """裏で動いている処理の取っ手。Browsers.run_task() が返す。

    Attributes:
        label: 何の処理か。ログとエラーメッセージに出る。
    """

    def __init__(self, future: "Future[T]", label: str) -> None:
        """直接呼ばず、Browsers.run_task() から作る。"""
        self._future = future
        self.label = label
        # wait() で結果（や例外）を受け取ったか。受け取られないまま終わった処理だけを
        # Browsers の終了時に報告するために使う
        self._is_collected = False

    def wait(self, timeout: float | None = None) -> T:
        """終わるのを待って、結果を返す。

        すでに終わっていれば、待たずにすぐ返る。
        中で例外が起きていた場合は、ここで送出される
        （裏で起きた失敗が黙って消えないよう、必ず受け取る側で表に出す）。

        Args:
            timeout: 待つ秒数の上限。省略すると終わるまで待つ。

        Returns:
            渡した処理の戻り値。

        Raises:
            TimeoutError: timeout 秒以内に終わらなかった場合。処理自体は動き続ける。
            Exception: 処理の中で起きた例外をそのまま送出する。
        """
        try:
            result = self._future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            # まだ動いている。受け取ったことにはしない
            raise TimeoutError(
                f"「{self.label}」が {timeout} 秒以内に終わりませんでした。\n"
                "処理自体は続いています。待ち時間を延ばすか、"
                "重い画面なら先に start しておく位置を見直してください。"
            ) from exc
        except Exception:
            self._is_collected = True
            raise

        self._is_collected = True
        return result

    @property
    def is_collected(self) -> bool:
        """wait() で結果や例外を受け取り済みなら True。"""
        return self._is_collected

    @property
    def is_done(self) -> bool:
        """終わっていれば True。まだ動いていれば False。

        待たずに様子だけ見たいときに使う。
        True になっていても、結果や例外を受け取るには wait() を呼ぶ。
        """
        return self._future.done()

    def __repr__(self) -> str:
        state = "完了" if self.is_done else "実行中"
        return f"BackgroundTask(label={self.label!r}, {state})"
