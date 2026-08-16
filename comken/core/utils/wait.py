"""comken/core/utils/wait.py — 待機ユーティリティ

time.sleep の薄いラッパー。単位を明示することで可読性を上げる。
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
