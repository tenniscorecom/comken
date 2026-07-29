"""
windows/handler.py — Windows API ユーティリティ（pywin32）

pywin32 を使った Windows 固有操作を提供する。

- ExcelComHandler: 数式の計算結果を読む、VBA マクロを実行する、パスワード付き保存など
- WindowHandler: ウィンドウの検索・前面表示
- RegistryHandler: レジストリ値の読み取り

通常の Excel 読み書きは excel/writer.py の ExcelWriter（openpyxl）を使うこと。
ExcelComHandler は数式やマクロが必要な場面に限定して使う。
"""

import logging
from pathlib import Path
from typing import Any

import win32api
import win32com.client
import win32con
import win32gui
from pywintypes import com_error

from ..constants import FileFormat
from ..exceptions import (
    EmptyHeaderCellError,
    ExcelFormulaError,
    ExcelHeadersTooFewError,
    FileFormatMismatchError,
    MacroError,
    RowTransferError,
    SheetNotFoundError,
    _warn_coerce,
)
from ..utils.data import col_to_num, column_number
from ..utils.files.base import FileBase

logger = logging.getLogger(__name__)


_SUFFIX_TO_FORMAT = {
    ".xlsx": FileFormat.XLSX,
    ".xlsm": FileFormat.XLSM,
    ".xlsb": FileFormat.XLSB,
    ".xls": FileFormat.XLS,
    ".csv": FileFormat.CSV,
}
_XL_CELL_TYPE_FORMULAS = -4123
_XL_ERRORS = 16
_DEFAULT_FORMULA_ERRORS = ("#NAME?", "#REF!")
_MAX_FORMULA_ERRORS_IN_MESSAGE = 10


class ExcelComHandler(FileBase):
    """win32com を使った Excel 操作クラス。

    openpyxl では対応できない以下の操作に使う:
        - 数式の計算結果を読む（CalculateFull で再計算してから取得）
        - VBA マクロを実行する
        - パスワード付きで保存する

    使い方:
        with ExcelComHandler("data.xlsx") as h:
            # 数式の計算結果を取得
            value = h.read_cell("Sheet1", row=2, col=3)

            # 行データをまとめて取得
            rows = h.read_rows("Sheet1")
            rows = h.read_rows_as_dicts("Sheet1")

            # 最終行を取得
            last_row = h.used_last_row("Sheet1")

            # 行全体が空かどうか確認
            if h.count_a("Sheet1", row=5) == 0:
                print("5行目は空行")

            # キー突合で転記（XLOOKUP 的転記）
            matched = h.transfer_by_key("T_data", key_col="Q",
                                        lookup=lookup, column_mapping={"A": "顧客名"})

            # マクロを実行
            h.run_macro("Module1.UpdateData")

            # 上書き保存（close() は保存しないため、変更を残すなら必須）
            h.save()

            # パスワードをかけて別名保存
            h.save_as("output.xlsx", read_pw="読み取りPW", write_pw="書き込みPW")
    """

    SUFFIXES = (".xlsx", ".xlsm", ".xlsb", ".xls", ".xltx", ".xltm")

    def __init__(
        self, path: str | Path, password: str = "", headers: list[str] | None = None
    ) -> None:
        """
        Args:
            path: Excel ファイルのパス。
            password: 読み取りパスワード（パスワード保護されたファイルを開く場合）。
            headers: ヘッダー行がない Excel の場合に、列名のリストをここで付ける。
                     指定すると read_rows_as_dicts() は全行をデータとして読む。
        """
        super().__init__(path)
        self._headers = headers
        self._wb = None
        # DispatchEx は常に新規の Excel プロセスを起動する。
        # Dispatch だとユーザーが開いている Excel に接続してしまい、
        # Visible=False で画面を消したり close() の Quit で相手のブックを閉じる事故が起きる
        self._excel = win32com.client.DispatchEx("Excel.Application")
        self._excel.Visible = False
        self._excel.DisplayAlerts = False
        # 外部リンクを持つブックを開いたときの「リンクを更新しますか」ダイアログで
        # 無人実行が止まるのを防ぐ（DisplayAlerts では抑制されない）
        self._excel.AskToUpdateLinks = False
        # Open に失敗すると with に入る前に例外で抜けるため、ここで Quit しないと
        # 起動済みの Excel プロセスが残り続ける
        try:
            kwargs = {"Filename": str(self.path.resolve())}
            if password:
                kwargs["Password"] = password
            self._wb = self._excel.Workbooks.Open(**kwargs)
            self._excel.CalculateFull()
        except Exception:
            self._excel.Quit()
            self._excel = None
            raise

    def __enter__(self) -> "ExcelComHandler":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _sheet(self, name) -> Any:
        """シートオブジェクトを返す。"""
        return self._wb.Sheets(_warn_coerce(name, str, "sheet_name", stacklevel=3))

    def read_cell(self, sheet_name: str, row: int, col: int | str) -> Any:
        """セルの値を返す（数式の計算結果）。

        Args:
            sheet_name: シート名。
            row: 行番号（1始まり）。
            col: 列番号（1始まり）または列記号（"A" / "AA"）。
        """
        return self._sheet(sheet_name).Cells(int(row), column_number(col)).Value

    def write_cell(self, sheet_name: str, row: int, col: int | str, value) -> None:
        """セルに値を書き込む。

        Args:
            sheet_name: シート名。
            row: 行番号（1始まり）。
            col: 列番号（1始まり）または列記号（"A" / "AA"）。
            value: 書き込む値。
        """
        self._sheet(sheet_name).Cells(int(row), column_number(col)).Value = value

    def recalculate(
        self,
        error_values: tuple[str, ...] = _DEFAULT_FORMULA_ERRORS,
        ranges: dict[str, str] | None = None,
    ) -> None:
        """ブックを再計算し、指定した数式エラーがあれば例外にする。

        既定では、数式やテーブル名などの書き間違いを強く示す ``#NAME?`` と、
        消えた参照先を示す ``#REF!`` を異常とする。``#N/A`` や ``#DIV/0!`` は
        業務データ次第で正常に起こりうるため、既定では異常としない。

        dry-run でもファイル保存はせず、再計算と検査は行う。ファイルを変更せずに
        数式を検査できるため、事前確認として有用だからである。

        Args:
            error_values: 異常とする Excel エラー表示のタプル。
            ranges: 検査する範囲を ``{シート名: "A1:C100"}`` で指定する。
                省略時はブック全体を検査する。

                範囲を指定すると、自分が書いていないセルの数式が変更の影響で
                壊れた場合は見つけられない。テーブル名の変更、シートの削除、
                行や列の削除など参照を壊す変更後は省略して全体を検査すること。

        Raises:
            ExcelFormulaError: 対象の数式エラーが見つかった場合。
        """
        logger.info("Excel の再計算を開始します: %s", self.path)
        self._excel.CalculateFull()

        found: list[tuple[str, str, str]] = []
        total = 0
        available_sheets = {str(sheet.Name): sheet for sheet in self._wb.Worksheets}
        if ranges is None:
            targets = [(sheet, sheet.UsedRange) for sheet in available_sheets.values()]
        else:
            missing = next(
                (sheet_name for sheet_name in ranges if sheet_name not in available_sheets),
                None,
            )
            if missing is not None:
                raise SheetNotFoundError(missing, list(available_sheets))
            targets = [
                (available_sheets[sheet_name], available_sheets[sheet_name].Range(cell_range))
                for sheet_name, cell_range in ranges.items()
            ]

        for sheet, target_range in targets:
            try:
                error_cells = target_range.SpecialCells(_XL_CELL_TYPE_FORMULAS, _XL_ERRORS)
            except com_error:
                # SpecialCells は該当セルがない場合にも COM 例外を送出する。
                continue

            for cell in error_cells.Cells:
                error = str(cell.Text)
                if error not in error_values:
                    continue
                total += 1
                if len(found) < _MAX_FORMULA_ERRORS_IN_MESSAGE:
                    found.append((str(sheet.Name), str(cell.Address), error))

        logger.info("Excel の再計算が完了しました: %s", self.path)
        if found:
            raise ExcelFormulaError(found, total - len(found))

    def read_rows(self, sheet_name: str, min_row: int = 2) -> list[tuple]:
        """指定シートの行データをタプルのリストで返す。

        Args:
            sheet_name: シート名。
            min_row: 読み始める行番号（デフォルト: 2 でヘッダーをスキップ）。

        Returns:
            各行を値のタプルにしたリスト。
        """
        ws = self._sheet(sheet_name)
        last_row = self.used_last_row(sheet_name)
        last_col = ws.UsedRange.Column + ws.UsedRange.Columns.Count - 1
        return [
            tuple(ws.Cells(row, col).Value for col in range(1, last_col + 1))
            for row in range(int(min_row), last_row + 1)
        ]

    def read_rows_as_dicts(self, sheet_name: str, header_row: int = 1) -> list[dict]:
        """ヘッダー行をキーとした辞書のリストで返す。

        ヘッダー行がないファイルは ExcelComHandler(path, headers=[...]) で列名を指定すること。

        Args:
            sheet_name: シート名。
            header_row: ヘッダーが存在する行番号（デフォルト: 1）。
                        __init__ で headers を指定した場合は無視される。

        Returns:
            [{"列名": 値, ...}, ...] の形式のリスト。全セルが空の行は除外される。

        Raises:
            ExcelError: ヘッダー行に空のセルがある場合（headers 未指定時のみ）、
                        または headers の列数がシートの列数より少ない場合。
        """
        ws = self._sheet(sheet_name)
        last_row = self.used_last_row(sheet_name)
        last_col = ws.UsedRange.Column + ws.UsedRange.Columns.Count - 1
        if self._headers is not None:
            if last_col > len(self._headers):
                raise ExcelHeadersTooFewError(len(self._headers), last_col)
            rows = [
                tuple(ws.Cells(row, col).Value for col in range(1, last_col + 1))
                for row in range(1, last_row + 1)
            ]
            return [
                # headers が実データ列より多い場合は、従来どおり余った見出しを含めない。
                dict(zip(self._headers, row, strict=False))
                for row in rows
                if not all(c is None for c in row)
            ]
        header_row = int(header_row)
        file_headers = [ws.Cells(header_row, col).Value for col in range(1, last_col + 1)]
        if all(h is None for h in file_headers):
            return []  # 空シート（ExcelWriter 側と挙動を揃える）
        none_cols = [i + 1 for i, h in enumerate(file_headers) if h is None]
        if none_cols:
            raise EmptyHeaderCellError(none_cols)
        return [
            dict(
                zip(
                    file_headers,
                    (ws.Cells(row, col).Value for col in range(1, last_col + 1)),
                    strict=False,
                )
            )
            for row in range(header_row + 1, last_row + 1)
        ]

    def count_a(self, sheet_name: str, row: int) -> int:
        """指定行の空でないセル数を返す。

        数式が入っていても "" を返すセルは空としてカウントされる。
        行全体が空かどうかの判定（スキップ処理）に使う。

        Args:
            sheet_name: シート名。
            row: 確認する行番号。

        Returns:
            空でないセルの数。0 なら行全体が空。
        """
        ws = self._sheet(sheet_name)
        return self._excel.WorksheetFunction.CountA(ws.Rows(int(row)))

    def used_last_row(self, sheet_name: str) -> int:
        """データが存在する最終行の行番号を返す。

        UsedRange を使うため、数式が入ったセルも含めて正確に最終行を取得できる。

        Args:
            sheet_name: シート名。

        Returns:
            最終行の行番号（1始まり）。
        """
        ws = self._sheet(sheet_name)
        return ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1

    def transfer_by_key(
        self,
        sheet_name: str,
        key_col: int | str,
        lookup: dict[str, dict],
        column_mapping: dict[str, str],
        start_row: int = 2,
    ) -> int:
        """キー列の値で lookup を引き、一致した行に値を転記する（XLOOKUP 的転記）。

        Excel の各行についてキー列の値を lookup のキーと突合し、
        一致したら column_mapping に従って値を書き込む。
        空行・キーが空の行・lookup に存在しないキーの行はスキップする。

        使い方:
            lookup = {"A001": {"顧客名": "株式会社A", "金額": "1000"}, ...}
            mapping = {"A": "顧客名", "B": "金額"}  # 列レター → lookup の列名

            with ExcelComHandler("data.xlsx") as h:
                matched = h.transfer_by_key("T_data", key_col="Q",
                                            lookup=lookup, column_mapping=mapping)

        Args:
            sheet_name: シート名。
            key_col: キー列。列レター（"Q"）または列番号（17）で指定する。
            lookup: {キーの値: {列名: 値}} の辞書。CsvReader.index() 等で作る。
            column_mapping: {列レター: lookup の列名} の辞書。
            start_row: 転記を始める行番号（デフォルト: 2。1行目はヘッダー想定）。

        Returns:
            転記した行数。

        Raises:
            ExcelError: 行の処理に失敗した場合（メッセージに行番号を含む）。
        """
        key_col_num = column_number(key_col)
        mapping = {col_to_num(letter): name for letter, name in column_mapping.items()}

        ws = self._sheet(sheet_name)
        last_row = self.used_last_row(sheet_name)
        logger.info("シート「%s」: 最終行 %d行", sheet_name, last_row)

        if last_row < int(start_row):
            return 0

        first_row = int(start_row)
        last_col = ws.UsedRange.Column + ws.UsedRange.Columns.Count - 1
        read_last_col = max(last_col, key_col_num, *mapping)
        values = ws.Range(ws.Cells(first_row, 1), ws.Cells(last_row, read_last_col)).Value
        if first_row == last_row and not isinstance(values, tuple):
            values = ((values,),)
        elif first_row == last_row and values and not isinstance(values[0], tuple):
            values = (values,)

        matched = 0
        output_by_column: dict[int, list[tuple[int, object]]] = {col_num: [] for col_num in mapping}
        for row_offset, row_values in enumerate(values):
            row = first_row + row_offset
            try:
                if all(value is None for value in row_values):
                    continue

                key_value = row_values[key_col_num - 1]
                if not key_value or str(key_value).strip() == "":
                    continue

                # 数値セルは COM 経由だと float になり "1001.0" になってしまうため、
                # 整数値なら int を経由して "1001" に揃える（CSV 側の文字列と一致させる）
                if isinstance(key_value, float) and key_value.is_integer():
                    key_value = int(key_value)

                lookup_row = lookup.get(str(key_value).strip())
                if lookup_row is None:
                    logger.debug("%d行目: キー「%s」が lookup に存在しません", row, key_value)
                    continue

                for col_num, name in mapping.items():
                    output_by_column[col_num].append((row, lookup_row.get(name, "")))
                logger.debug("%d行目: 転記完了（キー: %s）", row, key_value)
                matched += 1

            except Exception as e:
                raise RowTransferError(row, e) from e

        for col_num, updates in output_by_column.items():
            run_start = 0
            while run_start < len(updates):
                run_end = run_start + 1
                while run_end < len(updates) and updates[run_end][0] == updates[run_end - 1][0] + 1:
                    run_end += 1
                run = updates[run_start:run_end]
                target = ws.Range(ws.Cells(run[0][0], col_num), ws.Cells(run[-1][0], col_num))
                try:
                    target.Value = tuple((value,) for _, value in run)
                except Exception:
                    for row, value in run:
                        try:
                            ws.Range(ws.Cells(row, col_num), ws.Cells(row, col_num)).Value = value
                        except Exception as row_error:
                            raise RowTransferError(row, row_error) from row_error
                run_start = run_end

        logger.info("転記完了: %d件一致（シート: %s）", matched, sheet_name)
        return matched

    def run_macro(self, macro_name: str) -> None:
        """VBA マクロを実行する。

        Args:
            macro_name: 実行するマクロ名。"モジュール名.プロシージャ名" の形式で指定する。
                        例: "Module1.UpdateData"
        """
        try:
            self._excel.Run(str(macro_name))
        except Exception as e:
            raise MacroError(str(macro_name), e) from e

    def save(self) -> None:
        """元のファイルに上書き保存する。

        close() は保存せずに閉じる（SaveChanges=False）ため、
        write_cell や transfer_by_key での変更を残す場合は必ず呼ぶこと。
        """
        self._wb.Save()

    def save_as(
        self,
        path: str | Path,
        read_pw: str = "",
        write_pw: str = "",
        file_format: int | None = None,
    ) -> None:
        """ファイルを別名で保存する。パスワードを設定できる。

        Args:
            path: 保存先のパス。
            read_pw: 読み取りパスワード（省略可）。
            write_pw: 書き込みパスワード（省略可）。
            file_format: FileFormat 定数（例: FileFormat.CSV）。
                         省略すると元ファイルと同じ形式で保存する。

        Raises:
            ExcelError: 保存先の拡張子が元ファイルの形式と食い違う場合
                        （file_format 未指定時のみ）。
        """
        save_path = Path(path).resolve()
        if file_format is None:
            file_format = self._wb.FileFormat
            # 拡張子と中身の形式がズレたファイルは Excel で開くときに警告が出るため、
            # 変換の意図がある場合は file_format の明示を必須にする
            suffix_format = _SUFFIX_TO_FORMAT.get(save_path.suffix.lower())
            if suffix_format is not None and suffix_format != file_format:
                raise FileFormatMismatchError(save_path.suffix)
        # NOTE: FileFormat を省略して SaveAs すると Password / WriteResPassword が
        # 反映されないことがあるため、必ず明示して渡す
        self._wb.SaveAs(
            str(save_path),
            FileFormat=file_format,
            Password=read_pw,
            WriteResPassword=write_pw,
        )

    def close(self) -> None:
        """Excel を閉じる。with 文を使う場合は自動で呼ばれる。

        Close が失敗しても Quit は必ず実行する（Excel プロセスを残さないため）。
        2回呼んでも安全。
        """
        try:
            if self._wb:
                self._wb.Close(SaveChanges=False)
        finally:
            self._wb = None
            excel = self._excel
            self._excel = None
            if excel:
                excel.Quit()


class WindowHandler:
    """ウィンドウの検索・操作クラス。

    タイトルでウィンドウを検索し、前面に表示する。

    使い方:
        w = WindowHandler("メモ帳")
        w.activate() # ウィンドウを前面に表示
        w.get_title() # ウィンドウタイトルを取得
    """

    def __init__(self, title: str) -> None:
        """
        Args:
            title: 検索するウィンドウのタイトル（完全一致）。

        Raises:
            RuntimeError: ウィンドウが見つからない場合。
        """
        self._hwnd = win32gui.FindWindow(None, title)
        if self._hwnd == 0:
            raise RuntimeError(f"ウィンドウが見つかりません: {title}")

    def activate(self) -> None:
        """ウィンドウを前面に表示する。最小化されている場合は復元する。"""
        win32gui.ShowWindow(self._hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(self._hwnd)

    def get_title(self) -> str:
        """ウィンドウのタイトルを返す。"""
        return win32gui.GetWindowText(self._hwnd)


class RegistryHandler:
    """レジストリ値の読み取りクラス。with 文で確実にキーを閉じる。

    使い方:
        import win32con
        from comken.windows.handler import RegistryHandler

        with RegistryHandler(win32con.HKEY_CURRENT_USER, r"Software\\MyApp") as r:
            value = r.read("SettingName")
            print(value)
    """

    def __init__(self, hive: int, key_path: str) -> None:
        """
        Args:
            hive: レジストリのルートキー（例: win32con.HKEY_CURRENT_USER）。
            key_path: キーのパス（例: r"Software\\MyApp"）。
        """
        self._key = win32api.RegOpenKey(hive, key_path)

    def __enter__(self) -> "RegistryHandler":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def read(self, value_name: str) -> str:
        """レジストリ値を読み取る。

        Args:
            value_name: 読み取る値の名前。

        Returns:
            レジストリ値の文字列。
        """
        value, _ = win32api.RegQueryValueEx(self._key, value_name)
        return value

    def close(self) -> None:
        """レジストリキーを閉じる。with 文を使う場合は自動で呼ばれる。"""
        win32api.RegCloseKey(self._key)
