"""Excel 操作に関する例外。"""

from pathlib import Path

from .base import OriginalLibsError


class ExcelError(OriginalLibsError):
    """Excel 操作に関する例外をまとめて捕捉するための基底クラス。"""


class ExcelFileNotFoundError(ExcelError):
    """Excel ファイルが存在しない場合。

    発生箇所: ExcelBase.__init__()
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"Excel ファイルが見つかりません: {path}\n"
            "パスが正しいか、ファイルが存在するかを確認してください。"
        )


class SheetNotFoundError(ExcelError):
    """指定したシートが存在しない場合。

    発生箇所: ExcelBase._sheet() / ExcelComHandler._sheet()
    """

    def __init__(self, name: str, sheets: list[str]) -> None:
        super().__init__(f"シートが見つかりません: {name}  存在するシート: {sheets}")


class SheetAlreadyExistsError(ExcelError):
    """同名のシートが既に存在する場合。"""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"シート「{name}」は既に存在します。\n"
            "別のシート名を指定するか、既存のシートをリネームしてください。"
        )


class LastSheetDeletionError(ExcelError):
    """ブックの最後のシートを削除しようとした場合。"""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"最後のシート「{name}」は削除できません。\n"
            "先に別のシートを追加してから削除してください。"
        )


class MacroError(ExcelError):
    """VBA マクロの実行に失敗した場合。

    発生箇所: ExcelComHandler.run_macro()
    """

    def __init__(self, name: str, detail: Exception) -> None:
        super().__init__(
            f"VBA マクロの実行に失敗しました: {name}\n"
            f"Excel のマクロ名と内容を確認してください。（詳細: {detail}）"
        )


class RowTransferError(ExcelError):
    """Excel の行転記に失敗した場合。

    発生箇所: ExcelComHandler.transfer_by_key()
    """

    def __init__(self, row: int, detail: Exception) -> None:
        super().__init__(
            f"Excel {row}行目の転記中にエラーが発生しました。"
            f"該当行を確認してください。（詳細: {detail}）"
        )


class EmptyHeaderCellError(ExcelError):
    """Excel のヘッダー行に空のセルがある場合。

    発生箇所: ExcelBase.read_rows_as_dicts() / ExcelComHandler.read_rows_as_dicts()
    """

    def __init__(self, columns: list[int]) -> None:
        super().__init__(
            f"ヘッダー行に空のセルがあります。列番号: {columns}\n"
            "Excelの1行目（ヘッダー行）を確認してください。"
        )


class ExcelHeadersTooFewError(ExcelError):
    """指定したヘッダー数が Excel の列数より少ない場合。

    発生箇所: ExcelBase.read_rows_as_dicts() / ExcelComHandler.read_rows_as_dicts()
    """

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            f"headers の列数（{expected}列）がシートの列数（{actual}列）より少ないため、"
            "はみ出した列のデータが失われます。\n"
            "headers にすべての列名を指定してください。"
        )


class FileFormatMismatchError(ExcelError):
    """保存先の拡張子と Excel の保存形式が一致しない場合。

    発生箇所: ExcelComHandler.save_as()
    """

    def __init__(self, suffix: str) -> None:
        super().__init__(
            f"保存先の拡張子（{suffix}）が元ファイルの形式と一致しません。\n"
            "形式を変換して保存する場合は file_format 引数で FileFormat 定数を"
            "指定してください。（例: file_format=FileFormat.CSV）"
        )
