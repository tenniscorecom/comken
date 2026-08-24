"""comken/exceptions/logger.py — ログ設定に関する例外。"""

from comken.exceptions.base import ComkenError


class LoggingAlreadyConfiguredError(ComkenError):
    """root logger がすでに設定されている

    対処:
        setup_logging() または setup_local_logging() はアプリの入口で1回だけ呼ぶ。
        実行基盤がログを設定する場合は呼ばない。
    """

    def __init__(self) -> None:
        super().__init__(
            "root logger はすでに設定されています。"
            "setup_logging() または setup_local_logging() は1回だけ呼んでください。"
        )


class LoggingConflictError(ComkenError):
    """root logger に comken 以外の handler が設定されている

    他ライブラリが先に root logger を設定した状態で ``setup_logging()`` /
    ``setup_local_logging()`` を呼ぶと、comken が既存 handler の出力先や
    レベルを勝手に変えてしまう。「何がどう混ざっているのか」を運用担当者に
    そのまま見せられるよう、既存 handler の正体を判別できる範囲で
    メッセージに並べる。

    この例外は ``setup_logging()`` / ``setup_local_logging()`` の呼び方では
    解決しない。利用者がコードを直しても他ライブラリの root logger 設定を
    止められないので、上が運用側へ通知されることを前提にした例外。

    対処:
        上の handler 一覧をそのままライブラリの管理者へ連絡してください
        （連絡先は環境ごとに異なるので、ここには書かない）。
        やむを得ず共存させたい場合は、呼び出し時に ``allow_existing=True``
        を指定すれば処理は続きますが、comken のハンドラーが追加されることで
        既存ライブラリのログが**二重**に出たり、出力先が想定と変わる可能性
        があります。
    """

    def __init__(self, handlers: list[str]) -> None:
        bullet = "\n".join(f"  - {line}" for line in handlers) if handlers else "  - (なし)"
        super().__init__(
            "root logger に comken 以外の handler が設定されているため、"
            "setup_logging() / setup_local_logging() を進められません。\n"
            f"{bullet}\n"
            "これは setup_logging() / setup_local_logging() の呼び出し回数では解決しません。"
            "上の一覧をそのままライブラリの管理者へ連絡してください。\n"
            "やむを得ず共存させたい場合は allow_existing=True を指定すれば"
            "処理は続行しますが、comken のハンドラーが追加されることで"
            "既存ライブラリのログが二重に出たり、出力先が想定と変わる可能性があります。"
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
