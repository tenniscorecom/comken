"""comken/exceptions/excel.py — Excel 操作に関する例外。"""

from collections.abc import Sequence
from pathlib import Path

from comken.exceptions.base import ComkenError


class ExcelError(ComkenError):
    """Excel に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class DataSheetAccessError(ExcelError):
    """データシートと表示用シートの責務に反する操作をした。

    対処:
        data_ で始まるシートは table()、それ以外はセル・範囲 API で操作する
    """

    def __init__(self, sheet_name: str, operation: str) -> None:
        super().__init__(
            f"シート「{sheet_name}」では {operation} を使用できません。\n"
            "データシートは table()、表示用シートはセル・範囲 API で操作してください。"
        )


class ExcelFileNotFoundError(ExcelError):
    """Excel ファイルが見つからない

    発生箇所: Excel.__init__() / ExcelCOMHandler.__init__()

    対処:
        ファイルの置き場所と名前を確認する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"Excel ファイルが見つかりません: {path}\n"
            "パスが正しいか、ファイルが存在するかを確認してください。"
        )


class SheetNotFoundError(ExcelError):
    """指定した名前のシートがない

    発生箇所: Excel.sheet() / Excel.data_sheet()

    対処:
        Excel を開いて、下のシート名（タブ）が変わっていないか確認する。変えた場合は元に戻す
    """

    def __init__(self, name: str, sheets: list[str]) -> None:
        super().__init__(f"シートが見つかりません: {name}  存在するシート: {sheets}")


class SheetAlreadyExistsError(ExcelError):
    """同じ名前のシートが既にある

    対処:
        別のシート名を指定するか、既存のシート名を変更する
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"シート「{name}」は既に存在します。\n"
            "別のシート名を指定するか、既存のシートをリネームしてください。"
        )


class SheetNameError(ExcelError):
    """表示用シートに使えない名前を ``create_sheet`` に渡した

    ``PY_`` で始まる名前はデータシート用なので ``create_data_sheet`` で作る。

    発生箇所: ``Excel.create_sheet()``

    対処:
        予約接頭辞 ``PY_`` を除いた名前を ``create_sheet`` に渡すか、
        データシートとして作る場合は ``create_data_sheet`` を使う
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"シート「{name}」は表示用シートとして作成できません。\n"
            "「PY_」で始まる名前はデータシート用なので create_data_sheet() を使ってください。"
        )


class InvalidTableNameError(ExcelError):
    """Excel で使えないテーブル名を指定した

    対処:
        空白・数字始まり・セル参照のような名前を避ける
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"テーブル名「{name}」は Excel で使用できません。\n"
            "空白を含めず、数字以外から始まり、セル参照（A1、R1C1 など）と"
            "紛らわしくない名前を指定してください。"
        )


class TableAlreadyExistsError(ExcelError):
    """同じ名前のテーブルが既にある

    対処:
        別のテーブル名を指定する
    """

    def __init__(self, name: str) -> None:
        super().__init__(
            f"テーブル「{name}」は既に存在します。\n別のテーブル名を指定してください。"
        )


class TableNotFoundError(ExcelError):
    """指定したテーブルがシートにない

    対処:
        エラーに表示された既存テーブル名を確認する
    """

    def __init__(self, name: str, tables: list[str]) -> None:
        super().__init__(f"テーブルが見つかりません: {name}  存在するテーブル: {tables}")


class TableFormulaOverwriteError(ExcelError):
    """テーブル内の人が入れた数式を値で潰そうとした

    数式セルがあると ``replace()`` / ``append()`` は既定で止まる。
    黙って値で潰すと、依存セルや集計式が壊れたことに遅れて気づくため。

    発生箇所: ExcelTable.replace() / ExcelTable.append()

    対処:
        数式を保持したい場合は、``replace()`` のあとに該当セルへ元の数式を
        書き戻す。意図的に値で潰してよいときだけ ``allow_formula_overwrite=True`` を渡す
    """

    def __init__(self, table_name: str, locations: Sequence[str]) -> None:
        sample = ", ".join(locations[:3])
        suffix = "" if len(locations) <= 3 else f" 他 {len(locations) - 3} 件"
        self.table_name = table_name
        self.locations = list(locations)
        super().__init__(
            f"Excel テーブル「{table_name}」に数式セルがあります: {sample}{suffix}\n"
            "replace()/append() は既定で数式を値で潰しません。"
            "数式を保持する場合は replace のあとに該当セルへ書き戻す、"
            "または allow_formula_overwrite=True で意図的な上書きを明示してください。"
        )


class MacroError(ExcelError):
    """Excel のマクロが失敗した

    発生箇所: ExcelCOMHandler.run_macro()

    対処:
        Excel をすべて閉じて再実行する。続く場合は管理者へ
    """

    def __init__(self, name: str, detail: Exception) -> None:
        super().__init__(
            f"VBA マクロの実行に失敗しました: {name}\n"
            f"Excel のマクロ名と内容を確認してください。（詳細: {detail}）"
        )


class EmptyHeaderCellError(ExcelError):
    """Excel の見出しに空欄がある

    発生箇所: Excel.read_computed_rows_as_dicts() / ExcelTable.read() /
             ExcelCOMHandler.read_rows_as_dicts()

    対処:
        Excel の1行目の空欄を埋める
    """

    def __init__(self, columns: list[int]) -> None:
        super().__init__(
            f"ヘッダー行に空のセルがあります。列番号: {columns}\n"
            "Excelの1行目（ヘッダー行）を確認してください。"
        )


class DuplicateHeaderCellError(ExcelError):
    """Excel の見出し名が重複している

    発生箇所: Sheet.read_rows_as_dicts()

    対処:
        Excel の見出し名を重複しない名前に変更する
    """

    def __init__(self, headers: Sequence[object]) -> None:
        super().__init__(
            f"ヘッダー行に同じ見出しがあります: {headers}\n"
            "Excelの見出し名を重複しない名前に変更してください。"
        )


class EmptyExcelTableError(ExcelError):
    """Excel テーブル定義はあるが、定義範囲を1行も読み取れない。

    対処:
        Excel のテーブル定義範囲を確認する
    """

    def __init__(self, sheet_name: str, reason: str) -> None:
        self.sheet_name = sheet_name
        self.reason = reason
        super().__init__(f"Excel テーブル「{sheet_name}」が空です: {reason}")


class ExcelHeadersTooFewError(ExcelError):
    """指定した見出し数が列数より少ない

    発生箇所: ExcelCOMHandler.read_rows_as_dicts()

    対処:
        管理者へ連絡する
    """

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            f"headers の列数（{expected}列）がシートの列数（{actual}列）より少ないため、"
            "はみ出した列のデータが失われます。\n"
            "headers にすべての列名を指定してください。"
        )


class FileFormatMismatchError(ExcelError):
    """保存拡張子と形式が合わない

    発生箇所: ExcelCOMHandler.save_as()

    対処:
        管理者へ連絡する
    """

    def __init__(self, suffix: str) -> None:
        super().__init__(
            f"保存先の拡張子（{suffix}）が元ファイルの形式と一致しません。\n"
            "形式を変換して保存する場合は file_format 引数で FileFormat 定数を"
            "指定してください。（例: file_format=FileFormat.CSV）"
        )


class ExcelSaveValidationError(ExcelError):
    """保存予定のExcelファイルを再度開けず、安全に置き換えられない。

    対処:
        元ファイルは保持される。空き容量とExcel形式を確認して再実行する
    """

    def __init__(self, path: Path | str, detail: object) -> None:
        super().__init__(
            f"保存予定のExcelファイルを検証できませんでした: {path}\n"
            f"元ファイルは変更していません。（詳細: {detail}）"
        )


class ExcelMacroPreservationError(ExcelError):
    """保存予定のブックからVBAプロジェクトが欠落または変化した。

    対処:
        元ファイルは保持される。管理者に連絡し、Excel実機で保存方法を確認する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"VBAを保持できないためExcelを保存しませんでした: {path}\n"
            "元ファイルは変更していません。管理者に連絡してください。"
        )


class ExcelApplicationNotAvailableError(ExcelError):
    """Excel を起動できない

    Excel が入っていない PC で、Excel 本体が要る操作をしようとした。
    次のときに要る。

    - 数式の計算結果を読む（計算結果がファイルに保存されていない場合）
    - マクロを実行する、パスワード付きで保存する

    **読み書きだけなら Excel は要らない**（openpyxl で動く）。

    発生箇所: comken.toolbox.windows の ExcelCOMHandler

    対処:
        この PC に Excel が入っているか確認する。入れられない PC で動かすなら、
        数式ではなく値で書いてもらう（管理表なら、数式の結果を貼り付けてもらう）
    """

    def __init__(self, path: Path, error: Exception) -> None:
        super().__init__(
            f"Excel を起動できませんでした: {path}\n"
            f"（{error}）\n"
            "この PC に Excel が入っているか確認してください。\n"
            "数式の計算結果を読むときだけ Excel が必要です。"
            "数式をやめて値で書いてもらえば、Excel なしで動きます。"
        )


class ExcelReadOnlyOperationError(ExcelError):
    """read_only=True の Excel に書き込もうとした。

    Excel(path, read_only=True) は読み取り専用なので、保存やシート作成を
    行う create_sheet / create_data_sheet / run_macro 系の API は使えない。

    発生箇所: Excel.create_data_sheet() / Excel.create_sheet() /
             Excel.run_macro()

    対処:
        read_only=False で開き直すか、書き込みが要らない操作かを
        見直す（読み取りだけなら Excel(path, read_only=True) で十分）
    """

    def __init__(self, operation: str) -> None:
        super().__init__(f"read_only=True のExcelでは{operation}できません。")
