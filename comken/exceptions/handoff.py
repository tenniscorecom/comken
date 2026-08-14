"""comken/exceptions/handoff.py — 受け渡しフォルダに関する例外。"""

from collections.abc import Sequence
from pathlib import Path

from .base import ComkenError


class HandoffError(ComkenError):
    """受け渡しフォルダに関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class HandoffFilesMissingError(HandoffError):
    """受け渡しフォルダに必要なファイルが揃っていない

    対処:
        画面に出たファイル名のとおりに、表示された場所へ置いてから再実行する
        （取得が失敗したときは、手で置けばそのまま続きから動く）
    """

    def __init__(self, folder: Path | str, missing: Sequence[str]) -> None:
        # 足りないものを1件ずつ知らせると「1つ置いて再実行」を繰り返すことになるので、
        # 名前と置き場所をまとめて1回で伝える。
        names = "\n".join(f"  {name}" for name in missing)
        super().__init__(
            f"受け渡しフォルダに {len(missing)} 件足りません。\n"
            f"{names}\n"
            f"上のファイルを次の場所へ置いてから、もう一度実行してください:\n"
            f"  {folder}"
        )
