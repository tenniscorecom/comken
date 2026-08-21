"""ログ設定に関する例外。"""

from comken.exceptions.base import ComkenError


class LoggingAlreadyConfiguredError(ComkenError):
    """root logger がすでに設定されている

    対処:
        setup_logging() はアプリの入口で1回だけ呼ぶ。実行基盤がログを設定する場合は呼ばない。
    """

    def __init__(self) -> None:
        super().__init__(
            "root logger はすでに設定されています。setup_logging() は1回だけ呼んでください。"
        )
