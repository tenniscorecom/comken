"""設定ファイルに関する例外。"""

from pathlib import Path

from .base import OriginalLibsError


class ConfigError(OriginalLibsError):
    """設定エラーをまとめて捕捉するための基底クラス。"""


class ConfigFileNotFoundError(ConfigError):
    """config.ini が存在しない場合。

    発生箇所: Config.__init__() / generate_stub()
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"config.ini が見つかりません: {path}\n"
            "config.ini.example をコピーして config.ini を作成してください。"
        )


class ConfigCreatedFromExampleError(ConfigError):
    """config.ini が無かったため example から作成し、確認を求める場合。

    発生箇所: Config.__init__()
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"config.ini が無かったので、config.ini.example から作成しました: {path}\n"
            "中の値（フォルダの場所など）を確認して書き換えてから、もう一度実行してください。"
        )


class ConfigLowerCaseNameError(ConfigError):
    """config.ini のセクション名・キー名に小文字が使われている場合。

    発生箇所: Config.__init__()
    """

    def __init__(self, path: Path | str, wrong: list[str]) -> None:
        super().__init__(
            f"config.ini のセクション名とキー名は大文字で書いてください: {path}\n"
            + "\n".join(f"  {item}" for item in wrong)
        )


class ConfigSectionNotFoundError(ConfigError):
    """config.ini に要求されたセクションが存在しない場合。

    発生箇所: Config.__getattr__()
    """

    def __init__(self, name: str, existing: list[str]) -> None:
        super().__init__(
            f"config.ini に [{name}] セクションがありません。\n"
            f"存在するセクション: {existing}\n"
            "セクション名の綴りと、config.ini に定義されているかを確認してください。"
        )
