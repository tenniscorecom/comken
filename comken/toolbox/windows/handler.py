"""comken/toolbox/windows/handler.py — Windows API ユーティリティ（pywin32）

pywin32 を使った Windows 固有操作を提供する。

- ExcelComHandler: 数式の計算結果を読む、VBA マクロを実行する、パスワード付き保存など
- WindowHandler: ウィンドウの検索・前面表示
- RegistryHandler: レジストリ値の読み取り

通常の Excel 読み書きは excel/writer.py の ExcelWriter（openpyxl）を使うこと。
ExcelComHandler は数式やマクロが必要な場面に限定して使う。
"""

# 定義中のハンドラー自身を戻り値の型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Self

import win32api
import win32com.client
import win32con
import win32gui

from comken.constants import FileFormat
from comken.core.data import column_number
from comken.core.files.base import FileBase
from comken.core.files.ops import copy_to_local_if_large
from comken.core.transfer import mapping_columns, normalize_lookup_key
from comken.exceptions import (
    EmptyHeaderCellError,
    ExcelApplicationNotAvailableError,
    ExcelFileNotFoundError,
    ExcelHeadersTooFewError,
    FileFormatMismatchError,
    MacroError,
    RowTransferError,
)
from comken.exceptions.warning import _warn_coerce
from comken.runtime import dry_run_log, is_dry_run

logger = logging.getLogger(__name__)


def _normalize_com_rows(values: Any, is_single_row: bool) -> tuple[tuple[Any, ...], ...]:
    """COM の Range.Value を常に行のタプルへ揃える。"""
    if not is_single_row:
        return values
    if not isinstance(values, tuple):
        return ((values,),)
    if values and not isinstance(values[0], tuple):
        return (values,)
    return values


def _consecutive_update_runs(
    updates: list[tuple[int, object]],
) -> list[list[tuple[int, object]]]:
    """連続した行への更新を、COM で一括書き込みできる単位へ分ける。"""
    runs: list[list[tuple[int, object]]] = []
    run_start = 0
    while run_start < len(updates):
        run_end = run_start + 1
        while run_end < len(updates) and updates[run_end][0] == updates[run_end - 1][0] + 1:
            run_end += 1
        runs.append(updates[run_start:run_end])
        run_start = run_end
    return runs


def _write_com_updates(ws: Any, output_by_column: dict[int, list[tuple[int, object]]]) -> None:
    """列ごとの更新を一括で書き、失敗した範囲だけセル単位へフォールバックする。"""
    for destination_column_number, updates in output_by_column.items():
        for run in _consecutive_update_runs(updates):
            target = ws.Range(
                ws.Cells(run[0][0], destination_column_number),
                ws.Cells(run[-1][0], destination_column_number),
            )
            try:
                target.Value = tuple((value,) for _, value in run)
            except Exception:
                for row_number, value in run:
                    try:
                        ws.Range(
                            ws.Cells(row_number, destination_column_number),
                            ws.Cells(row_number, destination_column_number),
                        ).Value = value
                    except Exception as error:
                        raise RowTransferError(row_number, error) from error


_SUFFIX_TO_FORMAT = {
    ".xlsx": FileFormat.XLSX,
    ".xlsm": FileFormat.XLSM,
    ".xltm": FileFormat.XLTM,
    ".xltx": FileFormat.XLTX,
    ".xlsb": FileFormat.XLSB,
    ".xls": FileFormat.XLS,
    ".csv": FileFormat.CSV,
}


def _block_values(ws, first_row: int, last_row: int, last_col: int) -> list[tuple]:
    """シートの矩形範囲をまとめて読み、行ごとのタプルにして返す。

    セルを1つずつ読むと COM の往復が「行数 × 列数」になり、数万行では実用にならない。
    Range で一度に読めば往復は1回で済む。
    """
    if first_row > last_row or last_col < 1:
        return []
    values = ws.Range(ws.Cells(first_row, 1), ws.Cells(last_row, last_col)).Value
    # Range.Value は1セルだけの範囲でスカラーを返すため、行のタプルの形にそろえる。
    if not isinstance(values, tuple):
        return [(values,)]
    if not isinstance(values[0], tuple):
        return [values]
    return [tuple(row) for row in values]


class ExcelComHandler(FileBase):
    """win32com を使った Excel 操作クラス。

    openpyxl では対応できない以下の操作に使う:
        - 数式の計算結果を読む（CalculateFull で再計算してから取得）
        - VBA マクロを実行する
        - パスワード付きで保存する

    """

    SUFFIXES = (".xlsx", ".xlsm", ".xlsb", ".xls", ".xltx", ".xltm")

    def __init__(
        self,
        path: str | Path,
        password: str = "",
        headers: list[str] | None = None,
        local_copy_threshold_mb: float = 10,
    ) -> None:
        """
        Args:
            path: Excel ファイルのパス。
            password: 読み取りパスワード（パスワード保護されたファイルを開く場合）。
            headers: ヘッダー行がない Excel の場合に、列名のリストをここで付ける。
                     指定すると read_rows_as_dicts() は全行をデータとして読む。
            local_copy_threshold_mb: この MB 以上のファイルはローカルにコピーしてから開く。
                NAS やネットワークドライブのファイルが遅い・不安定な場合に有効。
                0 を指定するとローカルコピーを無効化できる
                （社内ルールでローカルコピーが禁止されている環境向け。
                ExcelReader / ExcelWriter と挙動を揃えるためのオプトアウト）。
                マクロ起動が UNC / 共有サーバー上のファイルを参照する場合、
                コピー元では見つからないことがある。そのときは
                ``local_copy_threshold_mb=0`` を指定して元の場所で開く。
        """
        super().__init__(path)
        self._original_path = self._path
        if not self._original_path.exists():
            raise ExcelFileNotFoundError(self._original_path)
        # save() は元ファイルへ保存するので、コピーで開いたかどうかは _working_path と
        # _original_path を比べることで判別する。
        self._working_path, self._tmp = copy_to_local_if_large(
            self._original_path, local_copy_threshold_mb
        )
        self._headers = headers
        # COM オブジェクトは型を持たず、閉じたあとは None になる（Access と同じ）
        self._wb: Any = None
        # DispatchEx は常に新規の Excel プロセスを起動する。
        # Dispatch だとユーザーが開いている Excel に接続してしまい、
        # Visible=False で画面を消したり close() の Quit で相手のブックを閉じる事故が起きる
        try:
            self._excel: Any = win32com.client.DispatchEx("Excel.Application")
        except Exception as e:
            # Excel が入っていない PC では com_error がそのまま出て原因が分からない
            self._cleanup_tmp()
            raise ExcelApplicationNotAvailableError(self.path, e) from e
        try:
            self._excel.Visible = False
            self._excel.DisplayAlerts = False
            # 外部リンクを持つブックを開いたときの「リンクを更新しますか」ダイアログで
            # 無人実行が止まるのを防ぐ（DisplayAlerts では抑制されない）
            self._excel.AskToUpdateLinks = False
            kwargs = {"Filename": str(self._working_path.resolve())}
            if password:
                kwargs["Password"] = password
            self._wb = self._excel.Workbooks.Open(**kwargs)
            self._excel.CalculateFull()
        except Exception:
            # COM の設定や Open に失敗すると with に入れないため、ここで確実に終了する。
            # Quit 自体の失敗で、本来の初期化エラーを隠さない。
            try:
                self._excel.Quit()
            except Exception:
                logger.warning("初期化失敗後の Excel 終了に失敗しました", exc_info=True)
            finally:
                self._excel = None
                # 初期化失敗時も一時コピーは片付けておく
                self._cleanup_tmp()
            raise

    def __enter__(self) -> Self:
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

    def read_rows(self, sheet_name: str, min_row: int = 2) -> list[tuple]:
        """指定シートの行データをタプルのリストで返す。

        Args:
            sheet_name: シート名。
            min_row: 読み始める行番号（デフォルト: 2 でヘッダーをスキップ）。

        Returns:
            各行を値のタプルにしたリスト。
        """
        ws = self._sheet(sheet_name)
        last_row = self.last_row(sheet_name)
        last_col = ws.UsedRange.Column + ws.UsedRange.Columns.Count - 1
        return _block_values(ws, int(min_row), last_row, last_col)

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
        last_row = self.last_row(sheet_name)
        last_col = ws.UsedRange.Column + ws.UsedRange.Columns.Count - 1
        if self._headers is not None:
            if last_col > len(self._headers):
                raise ExcelHeadersTooFewError(len(self._headers), last_col)
            return [
                # headers が実データ列より多い場合は、従来どおり余った見出しを含めない。
                dict(zip(self._headers, row, strict=False))
                for row in _block_values(ws, 1, last_row, last_col)
                if not all(c is None for c in row)
            ]
        header_row = int(header_row)
        header_values = _block_values(ws, header_row, header_row, last_col)
        file_headers = list(header_values[0]) if header_values else []
        if not file_headers or all(h is None for h in file_headers):
            return []  # 空シート（ExcelWriter 側と挙動を揃える）
        none_cols = [i + 1 for i, h in enumerate(file_headers) if h is None]
        if none_cols:
            raise EmptyHeaderCellError(none_cols)
        return [
            dict(zip(file_headers, row, strict=False))
            for row in _block_values(ws, header_row + 1, last_row, last_col)
        ]

    def count_non_empty_cells(self, sheet_name: str, row: int) -> int:
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

    def last_row(self, sheet_name: str) -> int:
        """データが存在する最終行の行番号を返す。

        UsedRange を使うため、数式が入ったセルも含めて正確に最終行を取得できる。

        Args:
            sheet_name: シート名。

        Returns:
            最終行の行番号（1始まり）。
        """
        ws = self._sheet(sheet_name)
        return ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1

    def transfer_by_mapping(
        self,
        sheet_name: str,
        key_col: str,
        lookup: dict[str, dict],
        mapping: dict[str, str],
        header_row: int = 1,
    ) -> int:
        """列名で指定し、キーが一致した行に値を転記する（XLOOKUP 的転記）。

        Excel の各行についてキー列の値を lookup のキーと突合し、
        一致したら mapping に従って値を書き込む。
        空行・キーが空の行・lookup に存在しないキーの行はスキップする。

        Sheet.transfer_by_mapping() と同じ引数・対応表の向きであり、数式の再計算や
        パスワード付き保存など COM が必要なブックに限ってこちらを使う。
        ヘッダーがない、または列位置が固定された帳票には transfer_by_letter() を使う。
        Args:
            sheet_name: シート名。
            key_col: 転記先 Excel で照合に使う列名。
            lookup: {キーの値: {列名: 値}} の辞書。CsvReader.index() 等で作る。
            mapping: {転記元の列名: 転記先の列名} の辞書。
            header_row: 転記先 Excel のヘッダー行番号（1始まり）。

        Returns:
            転記した行数。

        Raises:
            ExcelError: 行の処理に失敗した場合（メッセージに行番号を含む）。
        """
        ws = self._sheet(sheet_name)
        last_row = self.last_row(sheet_name)
        last_col = ws.UsedRange.Column + ws.UsedRange.Columns.Count - 1
        header_values = _block_values(ws, int(header_row), int(header_row), last_col)
        headers = header_values[0] if header_values else ()
        header_columns, destination_columns = mapping_columns(headers, key_col, lookup, mapping)
        logger.info("シート「%s」: 最終行 %d行", sheet_name, last_row)
        if last_row <= int(header_row):
            return 0
        first_row = int(header_row) + 1
        values = ws.Range(ws.Cells(first_row, 1), ws.Cells(last_row, last_col)).Value
        values = _normalize_com_rows(values, first_row == last_row)

        matched = 0
        output_by_column: dict[int, list[tuple[int, object]]] = {
            col_num: [] for col_num in destination_columns.values()
        }
        for row_offset, row_values in enumerate(values):
            row = first_row + row_offset
            try:
                if all(value is None for value in row_values):
                    continue

                key_value = row_values[header_columns[key_col] - 1]
                lookup_key = normalize_lookup_key(key_value)
                if lookup_key is None:
                    continue
                lookup_row = lookup.get(lookup_key)
                if lookup_row is None:
                    logger.debug("%d行目: キー「%s」が lookup に存在しません", row, key_value)
                    continue

                for source, col_num in destination_columns.items():
                    output_by_column[col_num].append((row, lookup_row[source]))
                logger.debug("%d行目: 転記完了（キー: %s）", row, key_value)
                matched += 1

            except Exception as error:
                raise RowTransferError(row, error) from error

        _write_com_updates(ws, output_by_column)

        logger.info("転記完了: %d件一致（シート: %s）", matched, sheet_name)
        return matched

    def transfer_by_letter(
        self,
        sheet_name: str,
        key_col: int | str,
        lookup: dict[str, dict],
        mapping: dict[str, int | str],
        start_row: int = 2,
    ) -> int:
        """列記号で指定し、キーが一致した行へ値を転記する。

        ヘッダーがない、または列位置が仕様として固定された Excel に使う。
        ヘッダー名で指定できる帳票には transfer_by_mapping() を使う。
        mapping は両メソッド共通で ``{転記元の列名: 転記先}`` の向き。
        """
        ws = self._sheet(sheet_name)
        last_row = self.last_row(sheet_name)
        key_col_num = column_number(key_col)
        destination_columns = {
            column_number(destination): source for source, destination in mapping.items()
        }
        if last_row < int(start_row):
            return 0
        first_row = int(start_row)
        last_col = ws.UsedRange.Column + ws.UsedRange.Columns.Count - 1
        read_last_col = max(last_col, key_col_num, *destination_columns)
        values = ws.Range(ws.Cells(first_row, 1), ws.Cells(last_row, read_last_col)).Value
        values = _normalize_com_rows(values, first_row == last_row)
        matched = 0
        output_by_column: dict[int, list[tuple[int, object]]] = {
            column: [] for column in destination_columns
        }
        for row_offset, row_values in enumerate(values):
            row = first_row + row_offset
            try:
                key_value = row_values[key_col_num - 1]
                lookup_key = normalize_lookup_key(key_value)
                if lookup_key is None:
                    continue
                lookup_row = lookup.get(lookup_key)
                if lookup_row is None:
                    continue
                for destination_column, source in destination_columns.items():
                    output_by_column[destination_column].append((row, lookup_row.get(source, "")))
                matched += 1
            except Exception as error:
                raise RowTransferError(row, error) from error
        _write_com_updates(ws, output_by_column)
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

        NAS 上のファイルをローカルコピーして開いている場合も、保存先は元のファイル
        （一時コピーに保存すると close() でコピーごと消えるため）。
        動作は ExcelWriter.save() と同じ考え方（開いた場所ではなく、元の場所へ保存）。
        close() は保存せずに閉じる（SaveChanges=False）ため、
        write_cell や transfer_by_mapping での変更を残す場合は必ず呼ぶこと。

        Raises:
            FileFormatMismatchError: 保存先の拡張子がワークブックの形式と食い違う場合。
        """
        original = Path(self._original_path)
        if is_dry_run():
            dry_run_log("Excel を保存: %s", original)
            return
        if self._working_path == original:
            # そのまま開いているケース。Save() で上書き。
            self._wb.Save()
            return
        # ローカルコピーで開いているときは SaveAs で元ファイルへ。
        # FileFormat を明示しないと xlOpenXMLWorkbook 固定になり、.xlsm などの
        # マクロ付きブックが壊れる（ExcelWriter の save_as() と同じ理由）。
        file_format = self._wb.FileFormat
        suffix_format = _SUFFIX_TO_FORMAT.get(original.suffix.lower())
        if suffix_format is not None and suffix_format != file_format:
            raise FileFormatMismatchError(original.suffix)
        self._wb.SaveAs(str(original), FileFormat=file_format)
        # SaveAs 後は開いているブック自体が元ファイルへ切り替わる。
        # 次回の save() は同じファイルに対する Save() にする。
        self._working_path = original

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
        if is_dry_run():
            # パスワードは秘匿値なのでログには出さない（save_path のみ）
            dry_run_log("Excel を別名保存: %s", save_path)
            return
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
            try:
                if excel:
                    excel.Quit()
            finally:
                # ローカルコピーは不要になったので消す。Excel がファイルロックを
                # 握っている間に消そうとすると Windows で失敗するため try で握る。
                self._cleanup_tmp()

    def _cleanup_tmp(self) -> None:
        """ローカルコピー（_tmp）を削除する（ライブラリ内部用）。

        2回呼ばれても安全。削除できた場合だけ _tmp を None に戻す。
        失敗時は次回の ``close()`` で再試行できるようパスを残すが、例外は上げない
        （Excel がファイルロックを握っているケースがあるため）。
        """
        tmp = self._tmp
        if tmp is None:
            return
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            logger.debug("一時ファイルを削除できませんでした: %s", tmp, exc_info=True)
        else:
            self._tmp = None


class WindowHandler:
    """ウィンドウの検索・操作クラス。

    タイトルでウィンドウを検索し、前面に表示する。

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
    """レジストリ値の読み取りクラス。with 文で確実にキーを閉じる。"""

    def __init__(self, hive: int, key_path: str) -> None:
        """
        Args:
            hive: レジストリのルートキー（例: win32con.HKEY_CURRENT_USER）。
            key_path: キーのパス（例: r"Software\\MyApp"）。
        """
        self._key = win32api.RegOpenKey(hive, key_path)

    def __enter__(self) -> Self:
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
