"""comken/toolbox/csv/reader.py — CSV 読み込みユーティリティ

CsvReader クラスを通じて CSV ファイルの読み込み・検索・抽出を行う。
"""

import csv
import io
import logging
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from comken.constants import Encoding
from comken.core.data import col_to_num
from comken.core.timer import measure
from comken.exceptions import (
    CsvCellReferenceError,
    CsvColumnNotFoundError,
    CsvHeadersTooFewError,
    CsvNoDataRowsError,
    CsvRowDuplicateKeyError,
    CsvRowNotFoundError,
    EncodingDetectionError,
)
from comken.toolbox.csv.base import CsvBase

logger = logging.getLogger(__name__)


def index_files(paths: Sequence[str | Path], key_col: str) -> dict[str, dict[str, str]]:
    """複数 CSV を 1つの lookup 辞書へまとめる。

    各ファイルを ``CsvReader(path).index(key_col)`` で読み、1つの辞書にマージして
    返す。ファイルを跨いで同じキーが見つかった場合は ``CsvRowDuplicateKeyError``
    を投げて停止する。**黙って後勝ちにしない**: どちらを採用したか分からないまま
    突合が進むと結果が静かにブレるため。

    1ファイル内の重複は ``CsvReader.index()`` がそのまま例外を上げるので、ここで
    別途チェックしない。

    Args:
        paths: 対象 CSV ファイルパスのシーケンス。順序は結果の辞書に反映されない
               （キーで引ける形式のため）。
        key_col: インデックスに使う列名。

    Returns:
        ``{キー: 行データ}`` のマージ済み辞書。

    Raises:
        CsvRowDuplicateKeyError: ファイルを跨いで同じキーが見つかった場合。
            ``duplicates`` には ``{キー: 出現ファイル数}`` の dict、
            ``path`` には対象ファイルを区切って並べた文字列を乗せる。
    """
    seen_counts: Counter[str] = Counter()
    result: dict[str, dict[str, str]] = {}
    for path in paths:
        for key, row in CsvReader(path).index(key_col).items():
            seen_counts[key] += 1
            if key not in result:
                result[key] = row
    duplicates = {key: count for key, count in seen_counts.items() if count > 1}
    if duplicates:
        # 既存 CsvRowDuplicateKeyError を再利用（新規例外を増やさない）。
        # path には対象ファイルを区切って並べた文字列を渡し、どのファイル同士で
        # 衝突したか利用者が特定できるようにする
        raise CsvRowDuplicateKeyError(
            key_col,
            duplicates,
            ", ".join(str(Path(p)) for p in paths),
        )
    return result


class CsvReader(CsvBase):
    """CSV ファイルの読み込みユーティリティ。

    ヘッダー行をキーにした辞書のリストとして扱う。
    読み込みは最初のメソッド呼び出し時に行い、同じインスタンス内では結果を再利用する。

    """

    # encoding=Encoding.AUTO のときに試す文字コード（この順に試す）
    # UTF-8 を先にするのは、CP932 は大半のバイト列を「読めてしまう」ため
    # （逆順にすると UTF-8 のファイルが文字化けしたまま通ってしまう）
    AUTO_ENCODINGS = (Encoding.UTF8_SIG, Encoding.CP932)
    CELL_REFERENCE_PATTERN = re.compile(r"([A-Za-z]+)([1-9][0-9]*)")

    def __init__(
        self,
        path: str | Path,
        encoding: str = Encoding.AUTO,
        headers: list[str] | None = None,
    ) -> None:
        """
        Args:
            path: CSV ファイルのパス。
            encoding: 文字コード。Encoding.AUTO（デフォルト）は UTF-8（BOM付き含む）→
                      CP932（Shift-JIS）の順に自動判定する。
                      明示したい場合は Encoding.UTF8_SIG / Encoding.CP932 を指定する。
            headers: ヘッダー行がない CSV の場合に、列名のリストをここで付ける。
                     指定すると1行目からデータとして読む。
                     例: CsvReader("data.csv", headers=["注文番号", "金額", "担当者"])
        """
        super().__init__(path, encoding)
        self._headers = headers
        # csv.DictReader.fieldnames の型スタブは Sequence[str] | None。
        # 読み出しは in 演算子しかしないため list[str] | None より緩い型で受ける
        self._fieldnames: Sequence[str] | None = None
        self._cache: list[dict[str, str]] | None = None

    def _load(self) -> list[dict[str, str]]:
        """
        Raises:
            CsvError: headers の列数が CSV の実際の列数より少ない場合
                      （はみ出した列が黙って失われるのを防ぐ）。
        """
        # 同じインスタンスで複数メソッドを呼んでもファイルを読むのは1回だけにする
        # （read_rows() の後に index() を呼ぶ等で毎回 IO するのを防ぐ）
        if self._cache is not None:
            logger.debug("CSV読込済みデータを再利用: 件数=%d", len(self._cache))
            return self._cache
        logger.debug("CSV読み込み開始: %s", self._path)
        # headers 指定時は1行目をヘッダーではなくデータとして扱う
        reader = csv.DictReader(io.StringIO(self._read_text()), fieldnames=self._headers)
        rows = list(reader)
        self._fieldnames = reader.fieldnames
        # DictReader は headers より多い列を None キーに押し込む。無音のデータ落ちを防ぐ
        if self._headers is not None and any(None in row for row in rows):
            raise CsvHeadersTooFewError(len(self._headers), self._path)
        self._cache = rows
        logger.debug("CSV読み込み完了: %s 件数=%d", self._path, len(rows))
        return rows

    def _validate_columns(self, columns: list[str]) -> None:
        """指定した列名が CSV に存在するか確認する。

        非エンジニアがヘッダーを変更したとき「黙って0件」ではなく
        明確なエラーで気づけるようにする。

        Raises:
            ColumnNotFoundError: 存在しない列名が含まれる場合。
        """
        if self._fieldnames is None:
            return  # データがなければ検証できない（空の結果を返す側に任せる）
        missing = [col for col in columns if col not in self._fieldnames]
        if missing:
            # CsvColumnNotFoundError は list[str] を要求するため、Sequence[str] を list にキャスト
            raise CsvColumnNotFoundError(missing, cast(list[str], self._fieldnames))

    def _read_text(self) -> str:
        """ファイルを読み、文字コードを判定してテキストとして返す。

        Raises:
            CsvError: encoding=Encoding.AUTO でどの文字コードでも読めなかった場合。
        """
        raw = self._path.read_bytes()
        if self._encoding != Encoding.AUTO:
            return raw.decode(self._encoding)

        for encoding in self.AUTO_ENCODINGS:
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise EncodingDetectionError(self._path)

    @measure
    def read_rows(self, columns: list[str] | None = None) -> list[dict[str, str]]:
        """全行を返す。

        Args:
            columns: 取得する列名のリスト。省略すると全列を返す。

        Returns:
            辞書のリスト。columns 指定時は指定列のみ含む。
        """
        data = self._load()
        if columns is None:
            return data
        self._validate_columns(columns)
        return [{col: row[col] for col in columns} for row in data]

    def rows(self, columns: list[str] | None = None):
        """列名でアクセスできる行を、for文で順に返す。"""
        yield from self.read_rows(columns)

    def cell(self, ref: str) -> str:
        """Excel 風のセル参照で、CSV の1セルを返す。

        ヘッダー付き辞書を作る ``_load()`` とは別に生の行を読むため、
        列名や ``headers`` の指定には依存しない。ヘッダー行も1行目として数える。
        列の位置に依存するため、上流で列が増減すると別の値を読む可能性がある。
        ヘッダーがある CSV では、列の位置が変わっても壊れない ``first()`` を推奨する。

        Args:
            ref: A1、B2 のような1始まりのセル参照。

        Returns:
            セルの文字列。空セルの場合は空文字。

        Raises:
            CsvCellReferenceError: 参照が不正、またはCSVの範囲外の場合。
        """
        match = self.CELL_REFERENCE_PATTERN.fullmatch(ref)
        if match is None:
            raise CsvCellReferenceError(ref, self._path, "セル参照の書き方が正しくありません")

        column_letters, row_text = match.groups()
        row_index = int(row_text) - 1
        column_index = col_to_num(column_letters) - 1

        raw_rows = list(csv.reader(io.StringIO(self._read_text())))
        if row_index >= len(raw_rows):
            raise CsvCellReferenceError(
                ref,
                self._path,
                f"指定した行は範囲外です（CSV は {len(raw_rows)} 行です）",
            )
        if column_index >= len(raw_rows[row_index]):
            column_count = len(raw_rows[row_index])
            raise CsvCellReferenceError(
                ref,
                self._path,
                f"指定した列は範囲外です（{row_index + 1} 行目は {column_count} 列です）",
            )
        return raw_rows[row_index][column_index]

    def first(self, column: str) -> str:
        """ヘッダー名で列を指定し、最初のデータ行の値を返す。

        ヘッダーがある CSV では、列の位置が変わっても壊れないこのメソッドを推奨する。
        ヘッダーがない、または位置で決まっている CSV では ``cell("A2")`` を使う。

        Args:
            column: 取得する列名。

        Returns:
            最初のデータ行にある指定列の文字列。空セルの場合は空文字。

        Raises:
            CsvColumnNotFoundError: 指定した列名が存在しない場合。
            CsvNoDataRowsError: データ行が1行もない場合。
        """
        data = self._load()
        self._validate_columns([column])
        if not data:
            raise CsvNoDataRowsError(self._path)
        return data[0][column]

    def find(self, key_col: str, value: str, required: bool = True) -> dict[str, str] | None:
        """key_col が value に一致する最初の行を返す。

        見つからないときは既定で CsvRowNotFoundError。
        「無くても処理を続けたい」場合だけ required=False にすると None を返す。

        Raises:
            CsvRowNotFoundError: required=True で該当行がない場合。
        """
        data = self._load()
        self._validate_columns([key_col])
        target = str(value)
        for row in data:
            # CSV の値は常に文字列。int 等を渡されても取りこぼさないよう文字列で比較する
            if str(row.get(key_col, "")) == target:
                return row
        if required:
            raise CsvRowNotFoundError(key_col, target, self.path)
        return None

    def filter(self, key_col: str, value: str) -> list[dict[str, str]]:
        """key_col が value に一致する全行を返す。

        Args:
            key_col: 検索対象の列名。
            value: 検索する値。

        Returns:
            一致した行の辞書のリスト。一致しない場合は空リスト。
        """
        data = self._load()
        self._validate_columns([key_col])
        target = str(value)
        # CSV の値は常に文字列。int 等を渡されても取りこぼさないよう文字列で比較する
        return [row for row in data if str(row.get(key_col, "")) == target]

    def column(self, col_name: str) -> list[str]:
        """指定列の値一覧を返す。

        Args:
            col_name: 取得する列名。

        Returns:
            列の値のリスト（ヘッダー行を除く）。
        """
        data = self._load()
        self._validate_columns([col_name])
        return [row[col_name] for row in data]

    def index(self, key_col: str) -> dict[str, dict[str, str]]:
        """key_col をキーにした {キー: 行} の辞書を返す。

        キーで1行を引く用途に使う。
        キーが重複していれば CsvRowDuplicateKeyError。重複が普通のデータは group_by() を使う。

        Raises:
            CsvRowDuplicateKeyError: キーが重複している場合。
        """
        data = self._load()
        self._validate_columns([key_col])
        indexed = {row[key_col]: row for row in data}
        # 黙って後勝ちにすると、転記結果が静かに変わって気づけない。
        if len(indexed) != len(data):
            duplicates = Counter(row[key_col] for row in data)
            raise CsvRowDuplicateKeyError(
                key_col,
                {key: count for key, count in duplicates.items() if count > 1},
                self.path,
            )
        return indexed

    def group_by(self, key_col: str) -> dict[str, list[dict[str, str]]]:
        """key_col をキーにした {キー: 行のリスト} の辞書を返す。

        同じキーの行が複数あるデータを、キーごとにまとめたいときに使う。
        1件だけ引きたい（重複しないはずの）データは index() を使う。
        """
        data = self._load()
        self._validate_columns([key_col])
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in data:
            grouped.setdefault(row[key_col], []).append(row)
        return grouped
