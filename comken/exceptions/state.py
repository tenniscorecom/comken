"""状態ファイルに関する例外。"""

from pathlib import Path

from .base import ComkenError


class StateError(ComkenError):
    """state.ini に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class StateFileCorruptedError(StateError):
    """state.ini が壊れていて読み取れない

    対処:
        内容を直す。直せない場合は別名に変更して、空の状態から再実行する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"state.ini を読み取れません: {path}\n"
            "ファイルの内容を確認してください。直せない場合は state.ini を別名に変更してから、"
            "再実行してください。"
        )


class StateLowerCaseNameError(StateError):
    """state のキー名に小文字がある

    対処:
        表示されたキー名を大文字に直す（`last_file` → `LAST_FILE`）
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"state のキー名は大文字で指定してください: {key} → {key.upper()}")


class StateValueTypeError(StateError):
    """state に保存できない型の値が渡された

    対処:
        真偽値・整数・小数・文字列・文字列のリストのいずれかに変更する
    """

    def __init__(self, value: object) -> None:
        super().__init__(
            f"state に保存できない値の型です: {type(value).__name__}\n"
            "保存できる型は、真偽値・整数・小数・文字列・文字列のリストです。"
            "渡す値を保存できる型に変更してください。"
        )
