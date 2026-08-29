"""comken/toolbox/browser/download.py — ブラウザダウンロード用フォルダの管理

DownloadDir は Edge/Chrome がダウンロード中に作る ".crdownload" ファイルを監視して
完了を判定するため、ブラウザ専用のクラスとして browser パッケージに置いている
（requests 等の API ダウンロードには使わない。あちらは自分でファイルに書くだけ）。
"""

# 定義中の DownloadDir を戻り値の型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path
from types import TracebackType
from typing import Self

from comken.core.timer import measure
from comken.exceptions import DownloadTimeoutError

logger = logging.getLogger(__name__)

# ダウンロード完了を確認する間隔（秒）
_POLL_INTERVAL_SECONDS = 0.5

# ダウンロード中のファイルに付く拡張子。これが消えたら完了とみなす
_IN_PROGRESS_SUFFIXES = (".crdownload", ".tmp")


class DownloadDir:
    """ブラウザダウンロード用のフォルダ。作成・完了待ち・後片付けをまとめて扱う。

    通常は Browsers.launch() がセッションごとに1つ用意するので、自分で作る必要はない
    （session.download_dir で受け取り、session.download_dir.wait() で完了を待つ）。

    一時フォルダの場合、セッションの with を抜けた時点で自動削除される（消し忘れ防止）。
    必要なファイルは with の中で移動しておくこと。
    ダウンロードしたものを残したい場合は、起動時に保存先を指定する
    （固定フォルダは with を抜けても削除されない）:

        with Browsers() as browsers:
            kintai = browsers.launch(Kintai, download_dir=r"C:\\作業\\downloads")
            files = kintai.session.download_dir.wait()
        # ← C:\\作業\\downloads とファイルはそのまま残る

    wait() は作成時点で既にあったファイルを無視し、新しく増えたファイルだけを完了対象にする。
    """

    def __init__(self, prefix: str = "comken_dl_", path: str | Path | None = None) -> None:
        """
        Args:
            prefix: 一時フォルダ名のプレフィックス（path 指定時は使われない）。
            path: 使用するフォルダのパス。指定するとそのフォルダを使う（なければ作成）。
                  省略時は一時フォルダを新規作成する。
        """
        if path:
            self.path = Path(path)
            self.path.mkdir(parents=True, exist_ok=True)
            self._is_temp = False
        else:
            self.path = Path(tempfile.mkdtemp(prefix=prefix))
            self._is_temp = True
        # 既存フォルダを指定した場合、前回のファイルを wait() の完了対象にしないための記録
        self._initial_files = {p: p.stat().st_mtime_ns for p in self.path.iterdir() if p.is_file()}

    def __fspath__(self) -> str:
        # os.PathLike 対応。パスを受け取る関数へそのまま渡せるようにする
        return str(self.path)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # 一時フォルダは自動削除（消し忘れ防止）。path 指定の固定フォルダは残す
        if self._is_temp:
            shutil.rmtree(self.path, ignore_errors=True)

    @measure
    def wait(self, timeout: int = 30) -> list[Path]:
        """ダウンロードが完了するまで待機し、完了したファイルの一覧を返す。

        Edge/Chrome はダウンロード中のファイルを ".crdownload" 拡張子で保存する。
        この拡張子のファイルが消えたらダウンロード完了と判断する。
        DownloadDir 作成時点で既にあったファイルは対象外
        （固定フォルダに前回のファイルが残っていても誤検出しない）。

        Args:
            timeout: タイムアウトまでの秒数（デフォルト: 30秒）。

        Returns:
            新しくダウンロードされたファイルのパスリスト（更新日時順）。

        Raises:
            DownloadTimeoutError: timeout 秒以内にダウンロードが完了しなかった場合。
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = {p: p.stat().st_mtime_ns for p in self.path.iterdir() if p.is_file()}
            changed = {
                p for p, modified_at in current.items() if self._initial_files.get(p) != modified_at
            }
            in_progress = [p for p in changed if p.suffix in _IN_PROGRESS_SUFFIXES]
            files = [p for p in changed if p.suffix not in _IN_PROGRESS_SUFFIXES]
            if files and not in_progress:
                return sorted(files, key=lambda p: p.stat().st_mtime)
            time.sleep(_POLL_INTERVAL_SECONDS)

        raise DownloadTimeoutError(self.path, timeout)

    def remove(self, force: bool = False) -> None:
        """フォルダごと削除する。ファイルを残したい場合は呼ばなくてよい。

        誤削除防止のため、path で指定した固定フォルダは削除せず警告を出す
        （自動作成した一時フォルダだけを削除する）。
        固定フォルダも本当に削除したい場合は force=True を指定する。

        Args:
            force: True にすると path 指定した固定フォルダも削除する。
        """
        if not self._is_temp and not force:
            logger.warning(
                "path 指定されたフォルダのため削除しません（削除するには remove(force=True)）: %s",
                self.path,
            )
            return
        shutil.rmtree(self.path, ignore_errors=True)
