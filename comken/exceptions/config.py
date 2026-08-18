"""comken/exceptions/config.py — 設定ファイルに関する例外。"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class ConfigError(ComkenError):
    """config.ini に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class ConfigFileNotFoundError(ConfigError):
    """config.ini が見つからない

    発生箇所: Config.__init__() / generate_stub()

    対処:
        config.ini.example が同じ場所にあるか確認する（あれば実行し直すだけで作られる）
    """

    def __init__(self, path: Path | str) -> None:
        # config.ini.example があれば ConfigCreatedFromExampleError の側へ行く。
        # ここへ来たということは example も無いので、「コピーして作る」は案内できない
        super().__init__(
            f"config.ini が見つかりません: {path}\n"
            "同じ場所に config.ini.example があるか確認してください。"
            "あれば、もう一度実行するだけで config.ini が作られます。"
        )


class ConfigCreatedFromExampleError(ConfigError):
    """config.ini が無かったので example から作った

    発生箇所: Config.__init__()

    対処:
        作られた config.ini の値を書き換えて、もう一度実行する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"config.ini が無かったので、config.ini.example から作成しました: {path}\n"
            "中の値（フォルダの場所など）を確認して書き換えてから、もう一度実行してください。"
        )


class ConfigLowerCaseNameError(ConfigError):
    """config.ini のセクション名・キー名に小文字がある

    発生箇所: Config.__init__()

    対処:
        表示された名前を大文字に書き換える（`[files]` → `[FILES]`）
    """

    def __init__(self, path: Path | str, wrong: list[str]) -> None:
        super().__init__(
            f"config.ini のセクション名とキー名は大文字で書いてください: {path}\n"
            + "\n".join(f"  {item}" for item in wrong)
        )


class ConfigSectionNotFoundError(ConfigError):
    """config.ini の必要な節がない

    発生箇所: Config.__getattr__()

    対処:
        表示されたセクション名を config.ini に追加する
    """

    def __init__(self, name: str, existing: list[str]) -> None:
        super().__init__(
            f"config.ini に [{name}] セクションがありません。\n"
            f"存在するセクション: {existing}\n"
            "セクション名の綴りと、config.ini に定義されているかを確認してください。"
        )


class ConfigRequiredKeysMissingError(ConfigError):
    """config.ini に必須の項目がない

    対処:
        エラーに表示された項目を config.ini へ追加する
    """

    def __init__(self, missing: list[str], path: Path) -> None:
        items = "\n".join(f"  - {name}" for name in missing)
        super().__init__(
            f"config.ini に必要な項目がありません。\n{items}\n"
            f"このファイルへ追加してください: {path}"
        )
