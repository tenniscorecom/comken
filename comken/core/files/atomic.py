"""comken/core/files/atomic.py — 一時ファイル経由の安全な書き込み。

「途中で電源が落ちる／プロセスが落ちる／例外が出る」のいずれが起きても、
置き換え先が中途半端な状態にならないよう、**同じフォルダに一時ファイルを作り、
書き終わってから ``os.replace`` で一括入れ替え** する。``os.replace`` は
同一ボリューム上でないと使えない（別ドライブだと例外になる）ため、
一時ファイルは必ず出力先と同じフォルダに置く。
"""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["atomic_write"]


@contextmanager
def atomic_write(path: str | Path) -> Iterator[Path]:
    """出力先と同じフォルダに一時ファイルを作り、ブロック終了時に置き換える。

    ブロック内で起きた例外や、置き換える前の中断（プロセス停止など）に対しては、
    **一時ファイルを片付けてから** 例外をそのまま上位へ返す。置き換え先が
    既に存在する場合は ``os.replace`` で上書きされる。

    ブロック内では **出力先ファイル（``path``）に触らない** こと。同じプロセスが
    読んでいる最中に置換が走ると、読んでいる側が半端な状態を見る可能性がある。

    Args:
        path: 最終的に置きたいファイルのパス。親フォルダが無ければ作成する。

    Yields:
        一時ファイルのパス。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _new_temp_name(target)
    try:
        yield tmp_path
        tmp_path.replace(target)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("一時ファイルを削除できませんでした: %s（%s）", tmp_path, e)
        raise


def _new_temp_name(target: Path) -> Path:
    """同じフォルダに衝突しない一時ファイル名を作る。

    - 同時に走っても互いを壊さないよう、乱数を入れる
    - 先頭を ``~`` にして、利用者が ``"1001_*.csv"`` のような glob で拾わないようにする
    - 拡張子は置き換える側と揃える（呼び出し側が拡張子で分岐している場合に備える）
    """
    return target.with_name(f"~{target.stem}.{uuid.uuid4().hex}{target.suffix}")
