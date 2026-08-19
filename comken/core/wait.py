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

from comken.core.timer import measure

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


@measure
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

    **フォルダが無い場合は待たずに即座に失敗する。** ``Path.glob()`` は
    存在しないフォルダでも例外を出さず空を返すので、そのまま回すと
    「共有サーバーが切れている」「パスを打ち間違えた」も
    「ファイルがまだ来ていない」と同じ形で ``timeout`` 秒後に失敗し、
    原因が分からなくなる。フォルダの不在は待っても直らないので、
    ここで区別して即座に知らせる。

    Args:
        folder: 監視するフォルダ。
        name_pattern: ファイル名の glob パターン（例: ``"data_*.csv"``）。
        timeout: 最大待機秒数。デフォルトは 60 秒。
        poll_interval: 再検索の間隔秒数。デフォルトは 1 秒。

    Returns:
        見つかったファイルのうち mtime が最新のもの。

    Raises:
        FileNotFoundError: 監視するフォルダが存在しない場合（待たずに即座）。
            待っている間にフォルダが消えた場合も同じ（``timeout`` 到達時）。
        NotADirectoryError: ``folder`` にフォルダではなくファイルを渡した場合。
        FileNotFoundError: ``timeout`` 秒経っても該当ファイルが見つからなかった場合。
    """
    folder_path = Path(folder)
    _ensure_watchable_folder(folder_path)
    # 期限は最初に1度だけ計算する (``time.sleep`` 中もカウントが進むように
    # するため、``monotonic`` を使って壁時計の変更に影響されないようにしている)
    deadline = time.monotonic() + timeout
    while True:
        matched = [p for p in folder_path.glob(name_pattern) if p.is_file()]
        if matched:
            return max(matched, key=lambda p: p.stat().st_mtime)
        if time.monotonic() >= deadline:
            # 待っている間にフォルダごと消えた（共有サーバーが切れた等）場合は、
            # 「ファイルが来ない」ではなくそちらを知らせる
            _ensure_watchable_folder(folder_path)
            raise FileNotFoundError(
                f"ファイルが見つかりません: {folder_path}\\{name_pattern} ({timeout}秒待ちました)"
            )
        time.sleep(poll_interval)


def _ensure_watchable_folder(folder_path: Path) -> None:
    """監視できるフォルダかを確かめる。駄目なら理由の分かる例外を投げる。

    Raises:
        FileNotFoundError: フォルダが存在しない。
        NotADirectoryError: 存在するがフォルダではない（ファイルだった）。
    """
    if folder_path.is_dir():
        return
    if folder_path.exists():
        raise NotADirectoryError(
            f"フォルダではありません: {folder_path}\n"
            "監視するフォルダを指定してください（ファイルは指定できません）。"
        )
    raise FileNotFoundError(
        f"監視するフォルダがありません: {folder_path}\n"
        "共有サーバーにつながっているか、パスが正しいかを確認してください。"
    )
