"""comken/exceptions/logger.py — ログ設定に関する例外。"""

from comken.exceptions.base import ComkenError


class LoggingAlreadyConfiguredError(ComkenError):
    """root logger がすでに設定されている

    対処:
        setup() または local() はアプリの入口で1回だけ呼ぶ。
        実行基盤がログを設定する場合は呼ばない。
    """

    def __init__(self) -> None:
        super().__init__(
            "root logger はすでに設定されています。setup() または local() は1回だけ呼んでください。"
        )


class LogRootNotConfiguredError(ComkenError):
    """LoggerSite の LOG_ROOT が設定されていない

    ファイルを作る前にここで止める。空のフォルダが現場へ残ると
    「設定し忘れたのか、運用で消すのか」が判断できなくなるため。

    対処:
        サブクラスに ``LOG_ROOT = "\\\\server\\share\\logs"`` を1行追加する
        （絶対パスまたは UNC 文字列。LOG_FOLDER_NAMES のフォルダ名はこの下に作られる）。
    """

    def __init__(self, site_cls: type) -> None:
        super().__init__(
            f"{site_cls.__name__} に LOG_ROOT が設定されていません。\n"
            f"  class {site_cls.__name__}(LoggerSite):\n"
            '      LOG_ROOT = "\\\\server\\share\\logs"   # ← この1行を追加してください\n'
            "LOG_ROOT はログを保存するルートの絶対パスまたは UNC 文字列です。\n"
            "LOG_FOLDER_NAMES に書いたフォルダ名はこの LOG_ROOT の下に作られます。"
        )
