"""comken/toolbox/excel/computed.py — Excel の数式計算結果読み取り。

``Excel`` が内部で使う。利用者は直接使わない（``toolbox/excel/__init__.py`` の
``__all__`` にも入れていない）。``Excel`` 側の状態（作業ファイル・ストリーム
Workbook キャッシュなど）を参照するため、コンポジションで ``Excel`` インスタンス
への参照を持つ。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from comken.core.timer import measure

if TYPE_CHECKING:
    from comken.toolbox.excel.workbook import Excel

logger = logging.getLogger(__name__)


class ComputedValueReader:
    """``Excel`` から委譲される数式計算結果の読み取り。

    ``Excel._computed`` として保持され、``Excel`` のメソッド内で ``self._excel``
    経由で状態（``_working_path`` / ``_workbook`` / ``_is_dirty`` など）を操作する。
    """

    def __init__(self, excel: Excel) -> None:
        self._excel = excel

    @measure
    def _read_computed_rows(self, sheet_name: str, min_row: int = 2) -> list[tuple[Any, ...]]:
        """数式の計算結果を行単位で読む。未計算の数式がある場合だけCOMへ昇格する。

        公開 API の ``read()`` が内部で使う薄いヘルパー。下流のテストや COM 経由
        の ``read_row_values()`` との橋渡し用。``read()`` ではなく行タプルを
        直接欲しいときだけ利用する想定（通常は ``read()`` を使う）。
        """
        self._excel._ensure_open()
        rows, needs_com = self._cached_rows(sheet_name, min_row)
        if not needs_com:
            logger.debug(
                "_read_computed_rows: キャッシュ済み値で返します: sheet=%s min_row=%d rows=%d",
                sheet_name,
                min_row,
                len(rows),
            )
            return rows
        # 書込み後の計算読取りでも、後続処理が例外なら元ファイルを変えない。
        # COMへ同期する先を一時コピーへ切り替えてから保存する。
        logger.debug(
            "_read_computed_rows: COM へ昇格して再計算します: sheet=%s min_row=%d rows=%d",
            sheet_name,
            min_row,
            len(rows),
        )
        if self._excel._is_dirty:
            self._excel._prepare_com_working_copy()
        self._excel._sync_working_file()
        from comken.toolbox.windows.excel_com import ExcelCOMHandler

        with ExcelCOMHandler(self._excel._working_path, local_copy_threshold_mb=0) as excel_com:
            return excel_com.read_row_values(sheet_name, min_row)

    def _open_stream_workbook(self, *, data_only: bool) -> Workbook:
        """openpyxl の read_only ストリーム Workbook を遅延オープンして返す。

        zip を一度しか読まないよう Workbook をキャッシュし、``close()`` で閉じる。
        ``data_only`` の違いで別インスタンスを保持する。``_reload_workbook``
        のタイミングで破棄される。
        """
        cache = (
            self._excel._stream_workbook_data_only if data_only else self._excel._stream_workbook
        )
        if cache is not None:
            logger.debug("_open_stream_workbook: キャッシュを返します: data_only=%s", data_only)
            return cache
        workbook = load_workbook(
            self._excel._working_path,
            read_only=True,
            data_only=data_only,
            keep_vba=self._excel.path.suffix.casefold() in {".xlsm", ".xltm"},
        )
        if data_only:
            self._excel._stream_workbook_data_only = workbook
        else:
            self._excel._stream_workbook = workbook
        logger.debug(
            "_open_stream_workbook: 新しいストリーム Workbook を開きました: data_only=%s path=%s",
            data_only,
            self._excel._working_path,
        )
        return workbook

    def _cached_rows(self, sheet_name: str, min_row: int) -> tuple[list[tuple[Any, ...]], bool]:
        """キャッシュ値と数式を並べ、値がない数式だけをCOM昇格対象にする。

        ``read_only`` の Excel で ``_read_computed_rows`` だけを呼ぶ経路では
        通常 Workbook を開かず、openpyxl のストリーム読みだけで値を取り出す。
        数式が1つもないブックでは ``data_only=False`` の Workbook を開かない。
        書き込み後の dirty 時 (``_is_dirty=True``) や作業ファイルがまだ無い
        新規ブックではメモリ上の Workbook を読む（ストリームは古い値しか
        持っていないため）。
        """
        if self._excel._is_dirty or not self._excel._working_path.exists():
            logger.debug(
                "_cached_rows: メモリから読みます: sheet=%s min_row=%d",
                sheet_name,
                min_row,
            )
            return self._cached_rows_from_memory(sheet_name, min_row)
        logger.debug(
            "_cached_rows: ストリームから読みます: sheet=%s min_row=%d",
            sheet_name,
            min_row,
        )
        return self._cached_rows_from_stream(sheet_name, min_row)

    def _cached_rows_from_memory(
        self, sheet_name: str, min_row: int
    ) -> tuple[list[tuple[Any, ...]], bool]:
        """書き込み直後／新規ブック用: メモリ上の Workbook を読んで値と数式を返す。

        ``Worksheet.iter_rows(values_only=True)`` で行ごとに値を流し、セル単位の
        ``cell(row, column)`` 呼び出しを避けてオブジェクト生成コストを抑える。
        空行（全セルが ``None`` または空文字）はストリーム段階で落とす。
        """
        self._excel._ensure_normal_workbook()
        assert self._excel._workbook is not None
        formula_sheet = self._excel._workbook[sheet_name]
        rows: list[tuple[Any, ...]] = []
        needs_com = False
        for formula_row in formula_sheet.iter_rows(min_row=min_row, values_only=True):
            row_tuple = tuple(formula_row)
            # ``_row_is_blank`` は ``Excel`` 側に残してある（移動対象に含めなかった）。
            # ``computed.py`` が ``workbook.py`` を import すると循環になるため、
            # 関数内で遅延 import する。
            from comken.toolbox.excel.workbook import Excel

            if Excel._row_is_blank(row_tuple):
                # 空行は tuple 化せずにスキップ
                continue
            rows.append(row_tuple)
            for value in row_tuple:
                # OpenPyXL で何かを書いた後は既存キャッシュが残っていても現在の値に
                # 対応する保証がないので、Excel で再計算する。
                if isinstance(value, str) and value.startswith("=") and self._excel._is_dirty:
                    needs_com = True
        logger.debug(
            "_cached_rows_from_memory: sheet=%s min_row=%d rows=%d needs_com=%s",
            sheet_name,
            min_row,
            len(rows),
            needs_com,
        )
        return rows, needs_com

    def _cached_rows_from_stream(
        self, sheet_name: str, min_row: int
    ) -> tuple[list[tuple[Any, ...]], bool]:
        """通常時（read_only 含む）はストリームで読む。

        ``ReadOnlyWorksheet.iter_rows(values_only=True)`` で行ごとに値を流す。
        ``cell(row, column)`` でセルを1つずつ指すと ReadOnlyWorksheet が毎回
        先頭から走査し直すため、行 × 列で二乗になる。イテレータなら前から1度
        だけ流すので線形で済む。

        セル値が ``None`` のときだけ ``data_only=False`` の Workbook を遅延
        オープンして数式かどうかを判定するため、**数式が無いブックでは zip を
        1 度しか読まない**。判定後に改めて数式側も ``iter_rows`` で同じ行から
        流し、同じ位置のセルを突き合わせる。

        ``_open_stream_workbook()`` が返す Workbook はここでは閉じない。
        `self._excel._stream_workbook` / `self._excel._stream_workbook_data_only` に
        キャッシュされ、同じ ``Excel`` セッション内の複数回の呼び出しで
        使い回される前提のため（zip を毎回読み直さないための仕組み）。
        ここで閉じると、次に呼ばれたときキャッシュが閉じた zip を指したまま
        返り、"Attempt to use ZIP archive that was already closed" になる。
        実際に閉じるのは ``Excel.close()``（``with`` を抜けるとき）。
        """
        cached_workbook = self._open_stream_workbook(data_only=True)
        cached_sheet = cached_workbook[sheet_name]
        rows, row_indices, any_none = self._collect_cached_rows(cached_sheet, min_row)
        if not any_none:
            logger.debug(
                "_cached_rows_from_stream: None セルが無いので数式判定をスキップ: sheet=%s rows=%d",
                sheet_name,
                len(rows),
            )
            return rows, False
        logger.debug(
            "_cached_rows_from_stream: None セルがあるため数式判定を行います: sheet=%s rows=%d",
            sheet_name,
            len(rows),
        )
        formula_workbook = self._open_stream_workbook(data_only=False)
        formula_sheet = formula_workbook[sheet_name]
        return self._mark_uncalculated_formulas(rows, row_indices, formula_sheet, min_row)

    @staticmethod
    def _collect_cached_rows(
        cached_sheet: Worksheet, min_row: int
    ) -> tuple[list[tuple[Any, ...]], list[int], bool]:
        """``data_only=True`` の値を ``min_row`` から流し、空行は捨てる。

        「ストリーム段階」で落とす: ``iter_rows`` から yield された行を
        tuple 化して空行（全セルが ``None`` または空文字）か判定し、空なら
        メモリに積まずにスキップする。 ``0`` / ``False`` は値として残す。
        Excel の ``dimension`` が膨らんだブックでも、不要な tuple や dict を
        残さずに線形時間で返せる。

        あわせて、残した各行が ``iter_rows(min_row=min_row)`` の何番目
        （0始まり）だったかを ``row_indices`` として返す。数式側ストリーム
        （空行を捨てない）と突き合わせるとき、空行を挟んだ行がズレたまま
        ``zip`` されるのを防ぐために使う（``_mark_uncalculated_formulas``）。
        """
        rows: list[tuple[Any, ...]] = []
        row_indices: list[int] = []
        any_none = False
        cached_stream = cached_sheet.iter_rows(min_row=min_row, values_only=True)
        for index, cached_row in enumerate(cached_stream):
            row_tuple = tuple(cached_row)
            # ``_row_is_blank`` は ``Excel`` 側に残してある（移動対象に含めなかった）。
            # 循環 import を避けるため関数内で遅延 import する。
            from comken.toolbox.excel.workbook import Excel

            if Excel._row_is_blank(row_tuple):
                # 空行はメモリに積まずにスキップ
                continue
            rows.append(row_tuple)
            row_indices.append(index)
            if not any_none:
                for value in row_tuple:
                    if value is None:
                        any_none = True
                        break
        return rows, row_indices, any_none

    @staticmethod
    def _mark_uncalculated_formulas(
        rows: list[tuple[Any, ...]],
        row_indices: list[int],
        formula_sheet: Worksheet,
        min_row: int,
    ) -> tuple[list[tuple[Any, ...]], bool]:
        """数式側ストリームを流し、``rows`` の None セルのうち数式を ``needs_com`` に積む。

        ``rows`` は ``_collect_cached_rows`` が空行を捨てたあとの行なので、
        素直に ``formula_sheet.iter_rows()`` と ``zip`` すると、空行を1つでも
        挟んだ時点で以降のすべての行がズレて突き合わさる（別の行同士を
        比較してしまう）。``row_indices`` に記録された絶対位置まで
        formula 側ストリームを1本の forward イテレータで進めることで、
        ストリームを読み直さず（線形時間のまま）位置を合わせる。
        """
        new_rows: list[tuple[Any, ...]] = []
        needs_com = False
        formula_stream = enumerate(formula_sheet.iter_rows(min_row=min_row, values_only=True))
        next_index = -1
        formula_row: tuple[Any, ...] = ()
        for cached_row, target_index in zip(rows, row_indices, strict=True):
            while next_index < target_index:
                next_index, raw_formula_row = next(formula_stream)
                formula_row = tuple(raw_formula_row)
            # cached 側と formula 側で行長が違う場合（末尾の空セル等）に
            # 備えて cached 側に合わせる。
            formula_tuple = formula_row
            if len(formula_tuple) < len(cached_row):
                formula_tuple = formula_tuple + (None,) * (len(cached_row) - len(formula_tuple))
            new_row: list[Any] = []
            for cached_value, formula_value in zip(cached_row, formula_tuple, strict=False):
                if (
                    cached_value is None
                    and isinstance(formula_value, str)
                    and formula_value.startswith("=")
                ):
                    # 未計算の数式セル: COM で再計算する
                    needs_com = True
                new_row.append(cached_value)
            new_rows.append(tuple(new_row))
        return new_rows, needs_com

    def _cached_range(
        self, sheet_name: str, min_col: int, min_row: int, max_col: int, max_row: int
    ) -> tuple[list[tuple[Any, ...]], bool]:
        """実テーブル範囲の保存済み計算値と、COM再計算の要否を返す。

        ``_open_stream_workbook()`` が返す Workbook はここでは閉じない。
        `_cached_rows_from_stream()` と同じ理由（キャッシュされた Workbook を
        同一セッション内で使い回すため）で、閉じるのは ``Excel.close()`` に任せる。
        """
        if self._excel._is_dirty or not self._excel._working_path.exists():
            self._excel._ensure_normal_workbook()
            assert self._excel._workbook is not None
            formula_sheet = self._excel._workbook[sheet_name]
            rows = [
                tuple(
                    formula_sheet.cell(row=row_number, column=column).value
                    for column in range(min_col, max_col + 1)
                )
                for row_number in range(min_row, max_row + 1)
            ]
            needs_com = any(
                isinstance(value, str) and value.startswith("=") for row in rows for value in row
            )
            logger.debug(
                "_cached_range: メモリから読みました: sheet=%s rows=%d needs_com=%s",
                sheet_name,
                len(rows),
                needs_com,
            )
            return rows, needs_com
        cached_workbook = self._open_stream_workbook(data_only=True)
        formula_workbook: Workbook | None = None
        cached_sheet = cached_workbook[sheet_name]
        rows = []
        needs_com = False
        for row_number in range(min_row, max_row + 1):
            row_values = []
            for column in range(min_col, max_col + 1):
                cached_value = cached_sheet.cell(row=row_number, column=column).value
                if cached_value is None:
                    if formula_workbook is None:
                        formula_workbook = self._open_stream_workbook(data_only=False)
                    formula_value = (
                        formula_workbook[sheet_name].cell(row=row_number, column=column).value
                    )
                    if isinstance(formula_value, str) and formula_value.startswith("="):
                        needs_com = True
                row_values.append(cached_value)
            rows.append(tuple(row_values))
        logger.debug(
            "_cached_range: ストリームから読みました: sheet=%s rows=%d needs_com=%s",
            sheet_name,
            len(rows),
            needs_com,
        )
        return rows, needs_com
