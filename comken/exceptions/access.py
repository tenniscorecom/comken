"""Microsoft Access 操作に関する例外。"""

from pathlib import Path

from .base import OriginalLibsError


class AccessError(OriginalLibsError):
    """Access 操作に関する例外をまとめて捕捉するための基底クラス。"""


class AccessFileNotFoundError(AccessError):
    """Access ファイルが存在しない場合。"""

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"Access ファイルが見つかりません: {path}\n"
            "パスが正しいか、ファイルが存在するかを確認してください。"
        )


class AccessLocalCopyError(AccessError):
    """Access ファイルのローカルコピーに失敗した場合。"""

    def __init__(self, path: Path | str, detail: Exception) -> None:
        super().__init__(
            f"Access ファイルをローカルにコピーできませんでした: {path}\n"
            "ファイルがほかの処理で使用中でないか、読み取り権限があるか、"
            f"一時フォルダに空き容量があるかを確認してください。（詳細: {detail}）"
        )


class AccessBackupError(AccessError):
    """Access ファイルのバックアップに失敗した場合。"""

    def __init__(self, path: Path | str, backup_path: Path | str, detail: Exception) -> None:
        super().__init__(
            f"Access ファイルをバックアップできませんでした: {path}\n"
            f"保存先: {backup_path}\n"
            "更新を中止しました。読み取り権限・保存先の空き容量・書き込み権限を"
            f"確認してください。（詳細: {detail}）"
        )


class AccessRoutineError(AccessError):
    """Access マクロまたは VBA の実行に失敗した場合。"""

    def __init__(self, name: str, kind: str, detail: Exception) -> None:
        super().__init__(
            f"Access {kind}の実行に失敗しました: {name}\n"
            f"名前と内容を確認してください。（詳細: {detail}）"
        )


class AccessSourceNotFoundError(AccessError):
    """指定したテーブルまたはクエリが存在しない場合。"""

    def __init__(self, name: str, sources: list[str]) -> None:
        super().__init__(
            f"Access のテーブルまたはクエリが見つかりません: {name}  "
            f"存在するテーブル／クエリ: {sources}"
        )
