"""状態ファイルに関する例外。"""

from pathlib import Path

from .base import ComkenError


class StateError(ComkenError):
    """状態ファイルのエラーをまとめて捕捉するための基底クラス。"""


class StateFileCorruptedError(StateError):
    """state.ini を正しく読み取れない場合。"""

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"state.ini を読み取れません: {path}\n"
            "ファイルの内容を確認してください。直せない場合は state.ini を別名に変更してから、"
            "再実行してください。"
        )


class StateLowerCaseNameError(StateError):
    """状態のキー名に小文字が使われた場合。"""

    def __init__(self, key: str) -> None:
        super().__init__(f"state のキー名は大文字で指定してください: {key} → {key.upper()}")


class StateValueTypeError(StateError):
    """state.ini に保存できない型の値が渡された場合。"""

    def __init__(self, value: object) -> None:
        super().__init__(
            f"state に保存できない値の型です: {type(value).__name__}\n"
            "保存できる型は、真偽値・整数・小数・文字列・文字列のリストです。"
            "渡す値を保存できる型に変更してください。"
        )
