"""comken/exceptions/files.py — ファイル・CSV・状態ファイル・ログ設定に関する例外。"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class ComkenFileNotFoundError(ComkenError, FileNotFoundError):
    """ファイルまたはフォルダが見つからない

    対処:
        エラーに表示されたパスと名前が正しいか、存在するかを確認する
    """

    def __init__(self, what: str, path: Path | str, hint: str | None = None) -> None:
        self.path = path
        message = f"{what}が見つかりません: {path}"
        if hint is not None:
            message = f"{message}\n{hint}"
        super().__init__(message)


class UnsupportedFileSuffixError(ComkenError):
    """対応外の拡張子が指定された

    対処:
        CSV / Excel の対応する拡張子のファイルを指定する
    """

    def __init__(self, path: Path, suffixes: tuple[str, ...]) -> None:
        expected = "、".join(suffixes)
        super().__init__(
            f"対応していないファイル形式です: {path}\n"
            f"拡張子が {expected} のファイルを指定してください。"
        )


class FileDeletionError(ComkenError):
    """ファイルを削除できなかった

    発生箇所: comken.core.files.delete_files()

    対処:
        他のプロセスがファイルを掴んでいないか、読み取り専用になっていないかを確認して
        もう一度実行する。消せたファイルは消えている

    Attributes:
        remaining: 削除できなかったファイルのパス一覧。
    """

    def __init__(self, remaining: list[Path]) -> None:
        self.remaining = remaining
        details = "\n".join(f"  - {p}" for p in remaining)
        super().__init__(
            f"次のファイルを削除できませんでした:\n{details}\n"
            "他のプロセスがファイルを掴んでいないか、読み取り専用になっていないかを確認して"
            "もう一度実行してください。\n"
            "消せたファイルは既に消えています。"
        )


class FileSuffixMissingError(ComkenError):
    """ファイル名に拡張子が無い

    発生箇所:
        comken.core.files.DateNameBuilder() / DateFileFinder.find() /
        DateFileFinder.find_all()

    対処:
        ファイル名に拡張子（例: ``.csv`` / ``.xlsx``）を含めて指定する。
        拡張子は名前の文字列にだけ書く。引数 ``ext`` / ``extension`` は廃止済みのため使えない。
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"ファイル名に拡張子がありません: {name!r}\n"
            "拡張子（例: '.csv' / '.xlsx'）を含めたファイル名を指定してください。"
            "拡張子は名前の文字列にだけ書きます。"
            "引数 ext / extension は廃止済みのため指定できません。"
        )


class CSVError(ComkenError):
    """CSV に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class StateError(ComkenError):
    """state.ini に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


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
