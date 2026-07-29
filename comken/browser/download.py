"""
browser/download.py — ブラウザダウンロード用フォルダの管理

DownloadDir は Edge/Chrome がダウンロード中に作る ".crdownload" ファイルを監視して
完了を判定するため、ブラウザ専用のクラスとして browser パッケージに置いている
（requests 等の API ダウンロードには使わない。あちらは自分でファイルに書くだけ）。
"""

import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class DownloadDir:
    """ブラウザダウンロード用のフォルダ。作成・完了待ち・後片付けをまとめて扱う。

    with 文で使うと、一時フォルダは with を抜けた時点で自動削除される（消し忘れ防止）。
    必要なファイルは with 内で移動しておくこと。
    ダウンロードしたものを残したい場合は path で固定フォルダを指定する
    （固定フォルダは with を抜けても削除されない）:
        with DownloadDir(path=r"C:\\作業\\downloads") as dl, EdgeDriver(download_dir=dl) as d:
            ...
            files = dl.wait()
        # ← C:\\作業\\downloads とファイルはそのまま残る
        # wait() は作成時点で既にあったファイルを無視し、
        # 新しく増えたファイルだけを完了対象にする
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
        # os.PathLike 対応。EdgeDriver(download_dir=dl) のように直接渡せるようにする
        return str(self.path)

    def __enter__(self) -> "DownloadDir":
        return self

    def __exit__(self, *args) -> None:
        # 一時フォルダは自動削除（消し忘れ防止）。path 指定の固定フォルダは残す
        if self._is_temp:
            shutil.rmtree(self.path, ignore_errors=True)

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
            TimeoutError: timeout 秒以内にダウンロードが完了しなかった場合。
        """
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = {p: p.stat().st_mtime_ns for p in self.path.iterdir() if p.is_file()}
            changed = {
                p for p, modified_at in current.items() if self._initial_files.get(p) != modified_at
            }
            in_progress = [p for p in changed if p.suffix in (".crdownload", ".tmp")]
            files = [p for p in changed if p.suffix not in (".crdownload", ".tmp")]
            if files and not in_progress:
                return sorted(files, key=lambda p: p.stat().st_mtime)
            time.sleep(0.5)

        raise TimeoutError(f"ダウンロードが {timeout} 秒以内に完了しませんでした: {self.path}")

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
