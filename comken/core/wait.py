"""comken/core/wait.py — 待機ユーティリティ

時間 Sleep とファイル出現待ちをまとめて公開する。
業務自動化で頻出する「待つ」を 1 モジュールに集約した。
ファイル I/O 待ち (``wait_for_file``) もここに置くことで、
``core.wait`` を見れば「待ち」の API が全部そろうようにする。

    from comken.core.wait import wait_for_file

    path = wait_for_file(
        folder=r"\\server\\share\\input",
        name_pattern="data_*.csv",
        timeout=60.0,
        poll_interval=1.0,
    )

``wait.seconds()`` / ``wait.minutes()`` / ``wait.until()`` は「時間 Sleep /
条件ポーリング / タイムアウト管理」の汎用プリミティブで、ファイルと無関係。
``wait_for_file`` はその上に特化させたラッパーだが、``core.wait`` に置くことで
「待つ系が 2 箇所に散らばる」状態を防ぐ (``core.files.wait`` は作らない)。
"""

import logging
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["wait", "wait_for_file"]


class wait:
    """待機ユーティリティ。インスタンス化せず静的メソッドで使う。"""

    @staticmethod
    def seconds(n: float) -> None:
        """指定した秒数だけ待つ。

        Args:
            n: 待機秒数。小数も指定できる（例: 0.5）。
        """
        time.sleep(n)

    @staticmethod
    def minutes(n: float) -> None:
        """指定した分数だけ待つ。

        Args:
            n: 待機分数。小数も指定できる（例: 0.5 → 30秒）。
        """
        time.sleep(n * 60)

    @staticmethod
    def until(condition: Callable[[], bool], timeout: float = 60, interval: float = 1.0) -> bool:
        """条件が True になるまで繰り返し確認する。

        Args:
            condition: 引数なしで呼び出せる callable。True を返したら待機終了。
            timeout: 最大待機秒数（デフォルト: 60秒）。
            interval: 確認間隔（秒）（デフォルト: 1秒）。

        Returns:
            True: 条件が満たされた。
            False: タイムアウトした（条件は満たされなかった）。
        """
        # 条件確認 → 期限判定 → sleep の順にすることで、
        # 最後の sleep 中に条件が成立した場合も取りこぼさない
        deadline = time.monotonic() + timeout
        while True:
            if condition():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)


# ── ファイル I/O 待ち (Phase 4 で files.wait.py を統合) ──────────────────

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

    **この関数は「ファイルが存在するまで待つ」機能であり、
    「ファイルへの書き込み完了を待つ」機能ではない。** 作成直後のファイルは
    書き込み途中で ``is_file()`` が True になる。後続処理が読む前に
    ファイルサイズや mtime が安定したかを確認したい場合は呼び出し側で
    対処すること。

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
