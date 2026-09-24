"""comken/services/salesforce_downloader/history_file_lock.py — 履歴CSVの排他制御。"""

import contextlib
import logging
import msvcrt
import time
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Self

from comken.exceptions import HistoryLockTimeoutError

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 10.0
LOCK_RETRY_SECONDS = 0.05


class HistoryFileLock:
    """Windows のファイルロックで、履歴CSVの読み書きを別プロセス間で直列化する。

    ``__init__`` には**保護したい履歴ファイルのパス**を渡す（ロック用ファイルの
    パスではない）。ロック用ファイル ``{path}.lock`` はこのクラスが内部で作る。
    ロックはファイルハンドルに結び付くため、プロセスが異常終了しても Windows が
    解放する。共有サーバー上でも同じパスを使うプロセス同士が同じ1バイトを
    ロックすることで、見出し作成と1行追記をひとまとまりに保つ。

    ``__exit__`` でロックを解放した直後に、ロック用ファイルを**ベストエフォートで
    削除**する。Windows では他プロセスが開いているファイルを削除できない
    （``PermissionError``）ので、待機中だったプロセスは削除に失敗するが、その
    プロセスは ``__enter__`` が既に ``self._file = None`` で失敗しているため、
    自分側からは削除しない（既にロックを保持しているプロセスが ``__exit__`` で
    消す）。これにより「自分がロックを保持していないのにロック用ファイルを消す」
    レースは起こらない。共有サーバー上にも古い ``.lock`` が溜まらない。
    """

    def __init__(self, history_path: str | Path, timeout: float = LOCK_TIMEOUT_SECONDS) -> None:
        self._path = Path(f"{Path(history_path)}.lock")
        self._timeout = timeout
        self._file: BinaryIO | None = None
        logger.debug(
            "HistoryFileLock を作成しました: path=%s timeout=%s",
            self._path,
            self._timeout,
        )

    def __enter__(self) -> Self:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self._path.open("a+b")
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        deadline = time.monotonic() + self._timeout
        logger.debug("履歴CSVのロック取得を開始します: path=%s", self._path)
        while True:
            try:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                self._file = lock_file
                logger.debug("履歴CSVのロック取得が完了しました: path=%s", self._path)
                return self
            except OSError as exc:
                if time.monotonic() >= deadline:
                    # ロック取得に失敗しただけ。自分が作ったファイルでも他プロセスが
                    # 掴んでいる可能性があるので、ここでは削除せず、ファイルだけを
                    # 閉じて ``HistoryLockTimeoutError`` を送出する。ロックを実際に
                    # 保持しているプロセスが ``__exit__`` でロック用ファイルを消す。
                    lock_file.close()
                    logger.debug(
                        "履歴CSVのロック取得がタイムアウトしました: path=%s timeout=%s",
                        self._path,
                        self._timeout,
                    )
                    raise HistoryLockTimeoutError(self._path, self._timeout) from exc
                time.sleep(LOCK_RETRY_SECONDS)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._file is None:
            # ロックを取得できずに ``__exit__`` まで来た場合（タイムアウト等）。
            # ロック用ファイルは ``__enter__`` が閉じ済みなので、ここでは何もしない
            return
        try:
            self._file.seek(0)
            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            logger.debug("履歴CSVのロックを解放しました: path=%s", self._path)
        finally:
            self._file.close()
            self._file = None
        # ロック解除とファイルクローズの後、ロック用ファイルを削除する。
        # ベストエフォート: Windows は他プロセスが開いているファイルを削除できない
        # ため、待機中だった側で PermissionError が出ても無視する（その側で
        # 削除する必要はない — 自分がロックを保持していたのは自分だけなので、
        # 自分だけがファイルを消す）。
        with contextlib.suppress(OSError):
            self._path.unlink()
