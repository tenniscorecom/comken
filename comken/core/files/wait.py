r"""comken/core/files/wait.py — ファイル出現待ち

業務自動化では「共有サーバーからCSVが落ちてくるのを待つ」「RPA基盤が
ファイルを置くのを待つ」など、**次の処理に進む前にファイルが揃っているか
確かめたい**場面が頻出する。``FileFinder.latest()`` は1回探すだけなので、
「無ければ待つ」には `wait_for_file` を使う。

    from comken.core.files import wait_for_file

    path = wait_for_file(
        folder=r"\\server\share\input",
        name_pattern="data_*.csv",
        timeout=60.0,
        poll_interval=1.0,
    )

タイムアウト時は ``FileNotFoundError`` を送出する。
「ファイルが無いこと」が業務的に想定内なら ``try / except`` で
捕捉する想定 (``Result.empty()`` を併用してもよい)。

**この関数は「ファイルが存在するまで待つ」機能であり、
「ファイルへの書き込み完了を待つ」機能ではない。** ファイルが作成
された瞬間に ``Path.is_file()`` が True になるため、書き込み途中の
ファイルを後続処理が読む可能性がある (大きなファイルで顕著)。
書き込み完了まで保証したい場合は、**呼び出し側でファイルサイズや
更新日時が安定したかを確認する** (例: 一定秒 sleep してから読む、
mtime の安定を待つ、等)。**今はこの最小実装で十分** (書き込み完了待ち
の需要は現時点で確認できていないため、必要になった時点で別 API を
追加する)。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["wait_for_file"]

# デフォルトの最大待機秒数。業務運用の感覚値 (1分)。
DEFAULT_TIMEOUT_SECONDS = 60.0
# デフォルトの再検索間隔。短すぎると I/O が無駄に増える。
DEFAULT_POLL_INTERVAL_SECONDS = 1.0


def wait_for_file(
    folder: str | Path,
    name_pattern: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> Path:
    """``folder`` 内で ``name_pattern`` にマッチするファイルが出現するまで待つ。

    1度でも見つかれば、その時点で mtime が最新のファイルを返して終了する。
    ``poll_interval`` 秒ごとに再検索し、``timeout`` 秒経っても見つからなければ
    ``FileNotFoundError`` を送出する。

    **この関数は「ファイルが出現するまで待つ」機能であり、
    「ファイルへの書き込み完了を待つ」機能ではない。** 作成直後のファイルは
    書き込み途中で ``is_file()`` が True になる。後続処理が読む前に
    ファイルサイズや mtime が安定したかを確認したい場合は呼び出し側で
    対処すること (詳細はモジュール docstring 参照)。

    Args:
        folder: 監視するフォルダ。
        name_pattern: ファイル名の glob パターン（例: ``"data_*.csv"``）。
        timeout: 最大待機秒数。デフォルトは 60 秒。
        poll_interval: 再検索の間隔秒数。デフォルトは 1 秒。

    Returns:
        見つかったファイルのうち mtime が最新のもの。

    Raises:
        FileNotFoundError: ``timeout`` 秒経っても該当ファイルが見つからなかった場合。
    """
    folder_path = Path(folder)
    # 期限は最初に1度だけ計算する (``time.sleep`` 中もカウントが進むように
    # するため、``monotonic`` を使って壁時計の変更に影響されないようにしている)
    deadline = time.monotonic() + timeout
    while True:
        matched = [p for p in folder_path.glob(name_pattern) if p.is_file()]
        if matched:
            return max(matched, key=lambda p: p.stat().st_mtime)
        if time.monotonic() >= deadline:
            raise FileNotFoundError(
                f"ファイルが見つかりません: {folder_path}\\{name_pattern} ({timeout}秒待ちました)"
            )
        time.sleep(poll_interval)
