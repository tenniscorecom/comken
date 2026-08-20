"""comken/core/wait.py — 待機ユーティリティ

時間 Sleep とファイル出現待ちをまとめて公開する。
業務自動化で頻出する「待つ」を 1 モジュールに集約した。
ファイル I/O 待ち (``wait_for_file`` / ``wait_until_stable``) もここに置くことで、
``core.wait`` を見れば「待ち」の API が全部そろうようにする。

    from comken.core import wait_for_file, wait_seconds, wait_until

    path = wait_for_file(
        folder=r"\\server\\share\\input",
        name_pattern="data_*.csv",
        timeout=60.0,
        poll_interval=1.0,
    )

``wait_seconds()`` / ``wait_until()`` は「時間 Sleep / 条件ポーリング /
タイムアウト管理」の汎用プリミティブで、ファイルと無関係。
``wait_for_file`` はその上に特化させたラッパーだが、``core.wait`` に置くことで
「待つ系が 2 箇所に散らばる」状態を防ぐ (``core.files.wait`` は作らない)。

**全関数化した経緯 (2026-08-19・命名レビュー)**: 以前は `wait` クラス
（staticmethod のみ）に `seconds` / `minutes` / `until` を入れていたが、
クラスと関数が混在し、`wait.seconds()` / `wait_for_file()` のように呼び分けが
分かりにくかった。v1.0.0 で4関数に統一し、補完候補を `wait_` で揃えた。
`wait_minutes` は `time.sleep(n * 60)` の1行ラッパーで、利用が無かったため
含めていない。`wait_seconds(n * 60)` で代替する。
"""

import logging
import time
from collections.abc import Callable
from pathlib import Path

from comken.core.timer import measure

logger = logging.getLogger(__name__)

__all__ = ["wait_for_file", "wait_seconds", "wait_until", "wait_until_stable"]


def wait_seconds(n: float) -> None:
    """``n`` 秒待機する。

    Args:
        n: 待機秒数。小数も指定できる（例: 0.5）。
    """
    time.sleep(n)


def wait_until(condition: Callable[[], bool], timeout: float = 60, interval: float = 1.0) -> bool:
    """``condition`` が True になるまで待つ。

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
# 書き込み完了とみなすまでに、サイズと更新時刻が変わらないでいてほしい秒数。
# 短すぎると、書き込み側が一瞬止まっただけで「完成した」と誤判定する。
DEFAULT_STABLE_FOR_SECONDS = 2.0


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

    **「ファイルが存在するまで」しか待たない。** 作成直後のファイルは
    書き込み途中でも ``is_file()`` が True になるので、書き込み完了まで
    待ってから読みたいときは ``wait_until_stable()`` を続けて呼ぶ::

        path = wait_for_file(folder, "data_*.csv")
        path = wait_until_stable(path)   # サイズが落ち着くまで待つ

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


@measure
def wait_until_stable(
    path: str | Path,
    stable_for: float = DEFAULT_STABLE_FOR_SECONDS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> Path:
    r"""ファイルへの書き込みが終わるまで待つ。

    サイズと更新時刻を ``poll_interval`` 秒ごとに見て、``stable_for`` 秒のあいだ
    どちらも変わらなければ「書き終わった」とみなして返す。共有サーバーへ
    他のシステムが置きにくるファイルを、途中まで読んでしまうのを防ぐ。

        path = wait_until_stable(r"\\server\share\in\data.csv", stable_for=2.0)
        rows = read_csv(path)      # 全部書き終わってから読む

    **サイズと更新時刻でしか判断できないので、確実ではない。** 書き込み側が
    ``stable_for`` より長く止まると、途中でも「書き終わった」と判定する。
    ネットワークが不安定な共有フォルダでは ``stable_for`` を長めに取る。

    **書き込み側を自分で書けるなら、この関数より
    「別名で書いてから rename する」ほうが確実**（``comken.core.files`` の
    atomic 系がその形）。rename は一瞬で終わるので、読む側が途中の状態を
    見ることがない。この関数は**書き込み側に手を出せないとき**の手段。

    Args:
        path: 監視するファイル。
        stable_for: サイズと更新時刻が変わらないでいてほしい秒数。デフォルトは 2 秒。
            ``0`` 以下を渡すと待たずにそのまま返す。
        timeout: 最大待機秒数。デフォルトは 60 秒。
        poll_interval: 確認の間隔秒数。デフォルトは 1 秒。

    Returns:
        書き込みが終わったとみなせるファイルの ``Path``。

    Raises:
        FileNotFoundError: ファイルが無い場合。待っている間に消えた場合も同じ。
        TimeoutError: ``timeout`` までに書き込みが終わらなかった場合。
    """
    file_path = Path(path)
    deadline = time.monotonic() + timeout
    return _wait_until_stable(file_path, stable_for, poll_interval, deadline)


def _wait_until_stable(
    file_path: Path,
    stable_for: float,
    poll_interval: float,
    deadline: float,
) -> Path:
    """``deadline`` まで待って、サイズと更新時刻が落ち着いたら ``file_path`` を返す。

    ``wait_for_file`` と ``wait_until_stable`` で期限の持ち方が違う（前者は
    探す時間と共通、後者は自前）ので、期限だけを引数で受け取る形にしている。
    """
    if stable_for <= 0:
        return file_path

    # (サイズ, 更新時刻) が変わらないまま stable_for 秒たったら書き終わりとみなす。
    # 更新時刻はナノ秒で見る (秒単位だと、1 秒以内の連続書き込みを取りこぼす)
    last_seen: tuple[int, int] | None = None
    unchanged_since = 0.0
    while True:
        try:
            stat = file_path.stat()
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"待っている間にファイルが消えました: {file_path}\n"
                "別の処理が移動または削除していないか確認してください。"
            ) from e

        current = (stat.st_size, stat.st_mtime_ns)
        now = time.monotonic()
        if current != last_seen:
            last_seen = current
            unchanged_since = now
        elif now - unchanged_since >= stable_for:
            return file_path

        if now >= deadline:
            raise TimeoutError(
                f"書き込みが終わりません: {file_path}"
                f" (サイズ {stat.st_size} バイトのまま {stable_for} 秒を待てませんでした)\n"
                "書き込み側が止まっていないか、timeout を延ばすかを確認してください。"
            )
        time.sleep(poll_interval)
