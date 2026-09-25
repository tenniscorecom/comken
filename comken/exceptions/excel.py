"""comken/exceptions/excel.py — Excel 操作に関する例外。"""

from collections.abc import Sequence
from pathlib import Path

from comken.exceptions.base import ComkenError


class ExcelError(ComkenError):
    """Excel に関するエラー

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class SheetNotFoundError(ExcelError):
    """指定した名前のシートがない

    発生箇所: Excel.sheet() / Excel.data_sheet()

    対処:
        Excel を開いて、下のシート名（タブ）が変わっていないか確認する。変えた場合は元に戻す
    """

    def __init__(self, name: str, sheets: list[str]) -> None:
        super().__init__(f"シートが見つかりません: {name}  存在するシート: {sheets}")


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


class TableColumnMismatchError(ExcelError):
    """渡された Table の列が既存テーブルの見出しと一致しない

    ``replace()`` / ``append()`` は、渡された Table の列を既存の見出しと
    名前で対応付ける。**既存の見出しに無い列名が含まれていた場合は例外**にし、
    黙って無視や位置ズレで書き込まない（書き漏らしに気づくのが遅れるため）。

    発生箇所: ExcelTable.replace() / ExcelTable.append()

    対処:
        既存の見出しと一致するように渡す Table の列を修正する。
        数式で参照される列は渡さない（「金額」のように計算で決まる列を
        Table に含めない、または数式を保持する前提の列として残す）
    """

    def __init__(self, table_name: str, missing: Sequence[str]) -> None:
        self.table_name = table_name
        self.missing = list(missing)
        sample = ", ".join(str(name) for name in missing)
        super().__init__(
            f"Excel テーブル「{table_name}」の見出しに無い列名が Table に含まれています: {sample}\n"
            "replace()/append() は既存の見出しと名前で対応付けます。"
            "既存の見出しと一致するように Table の列を修正してください。"
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


class ExcelHeaderError(ExcelError):
    """Excel の見出し行・テーブル定義に関するエラー

    見出しの空欄・重複、テーブル定義範囲から1行も読み取れない失敗を
    まとめて扱う。``replace()`` / ``append()`` は既定で数式セルを値で潰さない
    ので、空に見えるセルもここで発見できる。

    対処:
        - Excel の1行目（見出し行）の空欄・重複を直す
        - テーブル定義範囲が狭すぎないか、データシートと表示用シートの取り違えがないか確認する
    """

    def __init__(self, message: str, **attributes: object) -> None:
        super().__init__(message)
        for key, value in attributes.items():
            self.__dict__[key] = value


class ExcelNameError(ExcelError):
    """Excel のシート名・テーブル名に関するエラー

    対処:
        - 既に存在する名前は避ける（シート／テーブル）
        - ``PY_`` 接頭辞は ``create_data_sheet`` 用なので ``create_sheet`` には付けない
        - 空白・数字始まり・セル参照のような名前はテーブル名に使わない
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ExcelSaveError(ExcelError):
    """保存時に Excel ファイルを安全に置き換えられなかった

    元ファイルは保持される。VBA を保ったまま保存できなかった、
    保存したはずのファイルが Excel で開けないなどで発覚する。

    対処:
        元ファイルは変更されていない。空き容量・Excel のバージョン整合性・
        VBA の保存形式（``.xlsm`` になっているか）を確認して再実行する
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ExcelUsageError(ExcelError):
    """Excel の使い方に反する操作をした

    データシートと表示用シートの責務違反、``read_only=True`` への書き込み、
    見出し数不足、保存拡張子の不一致などをまとめて扱う。

    対処:
        エラーに表示された操作名・見出し数・拡張子を確認する。
        - ``read_only=True`` への書き込みは read_only=False で開き直す
        - データシート／表示用シートの API は ``Excel`` クラスのドキュメントを参照する
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ExcelApplicationNotAvailableError(ExcelError):
    """Excel を起動できない

    Excel が入っていない PC で、Excel 本体が要る操作をしようとした。
    次のときに要る。

    - 数式の計算結果を読む（計算結果がファイルに保存されていない場合）
    - マクロを実行する、パスワード付きで保存する

    **読み書きだけなら Excel は要らない**（openpyxl で動く）。

    発生箇所: comken.toolbox.windows の ExcelError

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
