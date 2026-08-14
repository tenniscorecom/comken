"""comken/exceptions/access.py — Microsoft Access 操作に関する例外。"""

from pathlib import Path

from .base import ComkenError


class AccessError(ComkenError):
    """Access に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class AccessFileNotFoundError(AccessError):
    """Access ファイルが見つからない

    対処:
        ファイルの置き場所と名前を確認する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"Access ファイルが見つかりません: {path}\n"
            "パスが正しいか、ファイルが存在するかを確認してください。"
        )


class AccessLocalCopyError(AccessError):
    """Access ファイルを一時フォルダへコピーできない

    対処:
        使用状況・読み取り権限・空き容量を確認する
    """

    def __init__(self, path: Path | str, detail: Exception) -> None:
        super().__init__(
            f"Access ファイルをローカルにコピーできませんでした: {path}\n"
            "ファイルがほかの処理で使用中でないか、読み取り権限があるか、"
            f"一時フォルダに空き容量があるかを確認してください。（詳細: {detail}）"
        )


class AccessBackupError(AccessError):
    """元 DB を開く前のバックアップに失敗した

    対処:
        保存先の空き容量・書き込み権限・元 DB の読み取り権限を確認する
    """

    def __init__(self, path: Path | str, backup_path: Path | str, detail: Exception) -> None:
        super().__init__(
            f"Access ファイルをバックアップできませんでした: {path}\n"
            f"保存先: {backup_path}\n"
            "更新を中止しました。読み取り権限・保存先の空き容量・書き込み権限を"
            "確認してください。共有フォルダに書き込めない場合は、backup_dir で"
            f"書き込み可能なローカルフォルダを指定してください。（詳細: {detail}）"
        )


class AccessRoutineError(AccessError):
    """Access マクロまたは VBA の実行に失敗した

    対処:
        表示された名前と Access 側の内容を確認する
    """

    def __init__(self, name: str, kind: str, detail: Exception) -> None:
        super().__init__(
            f"Access {kind}の実行に失敗しました: {name}\n"
            f"名前と内容を確認してください。（詳細: {detail}）"
        )


class AccessSourceNotFoundError(AccessError):
    """テーブルまたはクエリが見つからない

    対処:
        エラーに表示された存在する名前を確認する
    """

    def __init__(self, name: str, sources: list[str]) -> None:
        super().__init__(
            f"Access のテーブルまたはクエリが見つかりません: {name}  "
            f"存在するテーブル／クエリ: {sources}"
        )
