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


class LoggerHostNotConfiguredError(ComkenError):
    """実行端末のログ保存先が LoggerSite に登録されていない

    対処:
        対象サイトの LOG_FOLDERS に、エラーに表示された端末名と保存先フォルダを登録する。
    """

    def __init__(self, hostname: str, site_name: str) -> None:
        super().__init__(
            f"端末 '{hostname}' のログ保存先がサイト '{site_name}' に登録されていません。"
            "対象サイトの LOG_FOLDERS に端末名と保存先フォルダを登録してください。"
        )
