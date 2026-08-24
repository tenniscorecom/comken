"""comken/exceptions/file.py — ファイル形式の検証に関する例外。"""

from pathlib import Path

from comken.exceptions.base import ComkenError


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

    発生箇所: comken.core.files.DateNameBuilder() / DateFileFinder.prefix() / DateFileFinder.dated()

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
