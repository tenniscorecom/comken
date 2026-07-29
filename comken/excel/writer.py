"""Excel の書き込み・書式設定・保存を行う入口。"""

import logging
import os
import tempfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from ..exceptions import _warn_coerce
from ..runtime import dry_run_log, is_dry_run
from ..utils.data import col_to_num
from ..utils.files.base import FileBase
from ..utils.timer import measure
from .base import ExcelBase
from .sheet import Sheet

logger = logging.getLogger(__name__)


class ExcelWriter(ExcelBase):
    """Excel ブックの読み取り・書き込み・保存を行うクラス。

    読み取りメソッドも継承しているため、データを読んでから write_cell() や
    transfer_by_key() で書き換える処理を1つのブックで完結できる。

    使い方:
        # 既存ブックを開いて編集する
        with ExcelWriter("data.xlsx") as f:
            rows = f.read_rows_as_dicts("Sheet1")
            f.write_cell("Sheet1", row=2, col=1, value="新しい値")
            f.save()

        # 新規ブックを作る
        with ExcelWriter.create("report.xlsx") as f:
            sheet = f.sheet("Sheet1")
            sheet.write_table([{"注文番号": "A001", "金額": 1000}])
            f.save()
    """

    def __init__(
        self,
        path: str | Path,
        data_only: bool = False,
        local_copy_threshold_mb: float = 10,
        headers: list[str] | None = None,
    ) -> None:
        """
        Args:
            path: Excel ファイルのパス。
            data_only: True にすると数式セルのキャッシュ値を読む（read_computed_rows 推奨）。
            local_copy_threshold_mb: この MB 以上のファイルはローカルにコピーしてから開く。
                NAS・ネットワークドライブのファイルが遅い・不安定な場合に有効。
                0 を指定するとローカルコピーを無効化できる。
            headers: ヘッダー行がない Excel の場合に、列名のリストをここで付ける。
                指定すると read_rows_as_dicts() は全行をデータとして読む。
        """
        super().__init__(
            path,
            data_only=data_only,
            read_only=False,
            local_copy_threshold_mb=local_copy_threshold_mb,
            headers=headers,
        )

    def sheet(self, name: str) -> Sheet:
        """シートの高レベルラッパーを返す（シート単位でセル・行を書き込む）。

        Args:
            name: シート名。

        Raises:
            SheetNotFoundError: 指定したシートが存在しない場合。
        """
        return Sheet(self._sheet(name))

    @classmethod
    def create(cls, path: str | Path, sheet_name: str = "Sheet1") -> "ExcelWriter":
        """新規ブックを作る（ファイルはまだ作られず、save() で path に保存される）。

        使い方:
            rows = CsvReader("data.csv").rows()
            with ExcelWriter.create(r"C:\\作業\\report.xlsx") as f:
                s = f.sheet("Sheet1")
                s.write_table(rows)
                s.auto_width()
                f.save()

        Args:
            path: save() で保存されるパス。親フォルダがなければ保存時に自動作成される。
            sheet_name: 最初のシートの名前（デフォルト: "Sheet1"）。
        """
        instance = cls.__new__(cls)
        FileBase.__init__(instance, path)
        instance._original_path = instance._path
        instance._tmp = None
        instance._working_path = instance._original_path
        instance._headers = None
        instance._wb = Workbook()
        instance._wb.active.title = sheet_name
        return instance

    def write_cell(self, sheet_name: str, row: int, col: int, value) -> None:
        """セルに値を書き込む。

        Args:
            sheet_name: シート名。
            row: 行番号（1始まり）。
            col: 列番号（1始まり。A列=1、B列=2、…）。
            value: 書き込む値。
        """
        self._sheet(sheet_name).cell(row=int(row), column=int(col)).value = value

    @measure
    def transfer_by_key(
        self,
        sheet_name: str,
        key_col: int | str,
        lookup: dict[str, dict],
        column_mapping: dict[str, str],
        start_row: int = 2,
    ) -> int:
        """キー列の値で lookup を引き、一致した行に値を転記する（XLOOKUP 的転記）。

        ExcelComHandler.transfer_by_key の openpyxl 版。
        Excel を起動しないため数万行でも速い。数式の再計算が必要な場合だけ COM 版を使う。
        書き込み後は save() を忘れずに呼ぶこと。

        使い方:
            lookup = CsvReader("data.csv").index("注文番号")
            mapping = {"A": "顧客名", "B": "金額"}  # 列レター → lookup の列名

            with ExcelWriter("data.xlsx") as f:
                matched = f.transfer_by_key("T_data", key_col="Q",
                                            lookup=lookup, column_mapping=mapping)
                f.save()

        Args:
            sheet_name: シート名。
            key_col: キー列。列レター（"Q"）または列番号（17）で指定する。
            lookup: {キーの値: {列名: 値}} の辞書。CsvReader.index() 等で作る。
            column_mapping: {列レター: lookup の列名} の辞書。
            start_row: 転記を始める行番号（デフォルト: 2。1行目はヘッダー想定）。

        Returns:
            転記した行数。

        Raises:
            SheetNotFoundError: 指定したシートが存在しない場合。
        """
        key_col_num = col_to_num(key_col) if isinstance(key_col, str) else int(key_col)
        mapping = {col_to_num(letter): name for letter, name in column_mapping.items()}

        ws = self._sheet(sheet_name)
        last_row = ws.max_row
        logger.info("シート「%s」: 最終行 %d行", sheet_name, last_row)

        matched = 0
        for row in range(int(start_row), last_row + 1):
            key_value = ws.cell(row=row, column=key_col_num).value
            if key_value is None or str(key_value).strip() == "":
                continue

            # 数値セルが float で入っていると "1001.0" になってしまうため、
            # 整数値なら int を経由して "1001" に揃える（CSV 側の文字列と一致させる）
            if isinstance(key_value, float) and key_value.is_integer():
                key_value = int(key_value)

            lookup_row = lookup.get(str(key_value).strip())
            if lookup_row is None:
                logger.debug("%d行目: キー「%s」が lookup に存在しません", row, key_value)
                continue

            for col_num, name in mapping.items():
                ws.cell(row=row, column=col_num).value = lookup_row.get(name, "")
            logger.debug("%d行目: 転記完了（キー: %s）", row, key_value)
            matched += 1

        logger.info("転記完了: %d件一致（シート: %s）", matched, sheet_name)
        return matched

    @measure
    def save(self, path: str | Path | None = None) -> None:
        """ファイルを保存する。

        ローカルコピーで開いている場合も、省略時の保存先は元のファイル
        （一時コピーに保存すると close() でコピーごと消えてしまうため）。

        Args:
            path: 保存先のパス。省略すると開いた元のファイルに上書き保存する。
        """
        save_path = Path(path) if path else self._original_path
        if is_dry_run():
            dry_run_log("Excel を保存: %s", save_path)
            return
        save_path.parent.mkdir(parents=True, exist_ok=True)
        # os.replace は同一ドライブ内で使うため、保存先と同じフォルダに一時ファイルを作る。
        tmp = tempfile.NamedTemporaryFile(
            dir=save_path.parent, prefix=f".{save_path.name}.", suffix=".tmp", delete=False
        )
        tmp_path = Path(tmp.name)
        tmp.close()
        try:
            self._wb.save(tmp_path)
            os.replace(tmp_path, save_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def set_fill(self, sheet_name: str, row: int, col: int, color: str) -> None:
        """セルの背景色を設定する。

        よく使う色コード:
            "FFFF00" → 黄色
            "FF0000" → 赤
            "00FF00" → 緑
            "FFFFFF" → 白（色なし）

        使い方:
            with ExcelWriter("data.xlsx") as f:
                f.set_fill("Sheet1", row=2, col=1, color="FFFF00")
                f.save()

        Args:
            sheet_name: シート名。
            row: 行番号（1始まり）。
            col: 列番号（1始まり）。
            color: 16進数カラーコード（"RRGGBB" 形式、# なし）。
        """
        color = _warn_coerce(color, str, "color", stacklevel=2)
        fill = PatternFill(fill_type="solid", fgColor=color)
        self._sheet(sheet_name).cell(row=int(row), column=int(col)).fill = fill

    def set_column_width(self, sheet_name: str, col: int, width: float) -> None:
        """列幅を設定する。

        Excel の列幅の目安: 標準フォント（11pt）で 1文字 ≈ 1。
        日本語文字は全角なので 2文字分として計算する（"山田太郎" = 8程度）。

        使い方:
            with ExcelWriter("data.xlsx") as f:
                f.set_column_width("Sheet1", col=1, width=20)  # A列を幅20に
                f.save()

        Args:
            sheet_name: シート名。
            col: 列番号（1始まり。A列=1、B列=2、…）。
            width: 列幅（Excel の列幅単位）。
        """
        col_letter = get_column_letter(int(col))
        self._sheet(sheet_name).column_dimensions[col_letter].width = float(width)

    def set_number_format(self, sheet_name: str, row: int, col: int, fmt: str) -> None:
        """セルの数値フォーマットを設定する。

        よく使うフォーマット:
            "#,##0"          → 1,000（カンマ区切り整数）
            "#,##0.00"       → 1,000.00（小数2桁）
            "0%"             → 50%（パーセント）
            "yyyy/mm/dd"     → 2026/07/10（日付）
            "yyyy/mm/dd hh:mm" → 2026/07/10 09:00（日時）
            "@"              → 文字列として扱う

        使い方:
            with ExcelWriter("data.xlsx") as f:
                f.set_number_format("Sheet1", row=2, col=3, fmt="#,##0")
                f.save()

        Args:
            sheet_name: シート名。
            row: 行番号（1始まり）。
            col: 列番号（1始まり）。
            fmt: Excel の書式文字列。
        """
        fmt = _warn_coerce(fmt, str, "fmt", stacklevel=2)
        self._sheet(sheet_name).cell(row=int(row), column=int(col)).number_format = fmt

    def set_bold(self, sheet_name: str, row: int, col: int, bold: bool = True) -> None:
        """セルの太字を設定する。

        使い方:
            with ExcelWriter("data.xlsx") as f:
                f.set_bold("Sheet1", row=1, col=1)  # ヘッダーを太字に
                f.save()

        Args:
            sheet_name: シート名。
            row: 行番号（1始まり）。
            col: 列番号（1始まり）。
            bold: True で太字、False で解除。
        """
        cell = self._sheet(sheet_name).cell(row=int(row), column=int(col))
        cell.font = Font(bold=bool(bold))

    def run_macro(self, macro_name: str, save: bool = True) -> None:
        """VBA マクロを実行する。内部で win32com（pywin32）を使用する。

        COM は保存せずに閉じる仕様のため、save=True（デフォルト）で実行後に
        元ファイルへ保存する。マクロがブックを変更しても保存しないと結果は破棄される。

        WARNING: このメソッドは COM で元ファイルを直接編集する。openpyxl 側
            （write_cell 等）の未保存の変更とは独立で、run_macro の後に f.save() を
            呼ぶと openpyxl の内容で上書きされマクロの結果が消える。
            マクロと openpyxl 書き込みを混在させないこと。

        Args:
            macro_name: 実行するマクロ名。"モジュール名.プロシージャ名" の形式で指定する。
                        例: "Module1.UpdateData"
            save: True（デフォルト）ならマクロ実行後に元ファイルへ保存する。
        """
        from ..windows.handler import ExcelComHandler

        # local_copy の一時コピーではなく元ファイルに対して実行・保存する
        with ExcelComHandler(self._original_path) as com:
            com.run_macro(macro_name)
            if save:
                com.save()
