"""
utils/wait.py — 待機ユーティリティ

time.sleep の薄いラッパー。単位を明示することで可読性を上げる。

使い方:
    from comken.utils import wait

    wait.seconds(3)           # 3秒待つ
    wait.minutes(1)           # 1分待つ
    wait.seconds(0.5)         # 0.5秒待つ

    # 条件が満たされるまで待つ（最大60秒、1秒間隔）
    ok = wait.until(lambda: Path("result.xlsx").exists())
    if not ok:
        raise TimeoutError("ファイルが生成されませんでした")

    # タイムアウトや間隔を変えたい場合
    ok = wait.until(lambda: flag, timeout=120, interval=2)
"""

import time
from collections.abc import Callable


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
