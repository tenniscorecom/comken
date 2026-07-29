"""
csv/handler.py — CSV 読み込みユーティリティ

CsvReader クラスを通じて CSV ファイルの読み込み・検索・抽出を行う。

使い方:
    from comken.csv import CsvReader

    reader = CsvReader("data.csv")
    reader.rows() # 全行を辞書のリストで取得
    reader.find("注文番号", "A001") # 1件検索
    reader.filter("ステータス", "完了") # 複数行検索
    reader.column("金額") # 列の値一覧
    reader.index("注文番号") # 辞書化（突合に使う）
"""

import csv
import io
from pathlib import Path

from ..constants import Encoding
from ..exceptions import CsvColumnNotFoundError, CsvHeadersTooFewError, EncodingDetectionError
from ..utils.timer import measure
from .base import CsvBase


class CsvReader(CsvBase):
    """CSV ファイルの読み込みユーティリティ。

    ヘッダー行をキーにした辞書のリストとして扱う。
    読み込みは各メソッド呼び出し時に毎回行う（キャッシュなし）。

    使い方:
        reader = CsvReader("支店A.csv")

        # 全行取得
        rows = reader.rows()
        # → [{"注文番号": "A001", "金額": "1000", "担当者": "山田"}, ...]

        # 特定列のみ取得
        rows = reader.rows(columns=["注文番号", "金額"])
        # → [{"注文番号": "A001", "金額": "1000"}, ...]

        # キーで1件検索
        row = reader.find("注文番号", "A001")
        # → {"注文番号": "A001", ...} または None（見つからない場合）

        # キーで複数行検索
        rows = reader.filter("担当者", "山田")

        # 列の値一覧
        amounts = reader.column("金額")
        # → ["1000", "2000", "3000"]

        # キー列でインデックス化（突合用辞書の作成）
        lookup = reader.index("注文番号")
        # → {"A001": {"注文番号": "A001", ...}, "A002": {...}}
    """

    # encoding=Encoding.AUTO のときに試す文字コード（この順に試す）
    # UTF-8 を先にするのは、CP932 は大半のバイト列を「読めてしまう」ため
    # （逆順にすると UTF-8 のファイルが文字化けしたまま通ってしまう）
    AUTO_ENCODINGS = (Encoding.UTF8_SIG, Encoding.CP932)

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
        self._cache: list[dict[str, str]] | None = None

    def _load(self) -> list[dict[str, str]]:
        """
        Raises:
            CsvError: headers の列数が CSV の実際の列数より少ない場合
                      （はみ出した列が黙って失われるのを防ぐ）。
        """
        # 同じインスタンスで複数メソッドを呼んでもファイルを読むのは1回だけにする
        # （rows() の後に index() を呼ぶ等で毎回 IO するのを防ぐ）
        if self._cache is not None:
            return self._cache
        # headers 指定時は1行目をヘッダーではなくデータとして扱う
        rows = list(csv.DictReader(io.StringIO(self._read_text()), fieldnames=self._headers))
        # DictReader は headers より多い列を None キーに押し込む。無音のデータ落ちを防ぐ
        if self._headers is not None and any(None in row for row in rows):
            raise CsvHeadersTooFewError(len(self._headers), self._path)
        self._cache = rows
        return rows

    @staticmethod
    def _validate_columns(rows: list[dict[str, str]], columns: list[str]) -> None:
        """指定した列名が CSV に存在するか確認する。

        非エンジニアがヘッダーを変更したとき「黙って0件」ではなく
        明確なエラーで気づけるようにする。

        Raises:
            ColumnNotFoundError: 存在しない列名が含まれる場合。
        """
        if not rows:
            return  # データがなければ検証できない（空の結果を返す側に任せる）
        missing = [col for col in columns if col not in rows[0]]
        if missing:
            raise CsvColumnNotFoundError(missing, list(rows[0].keys()))

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
    def rows(self, columns: list[str] | None = None) -> list[dict[str, str]]:
        """全行を返す。

        Args:
            columns: 取得する列名のリスト。省略すると全列を返す。

        Returns:
            辞書のリスト。columns 指定時は指定列のみ含む。
        """
        data = self._load()
        if columns is None:
            return data
        self._validate_columns(data, columns)
        return [{col: row[col] for col in columns} for row in data]

    def find(self, key_col: str, value: str) -> dict[str, str] | None:
        """key_col が value に一致する最初の行を返す。

        Args:
            key_col: 検索対象の列名。
            value: 検索する値。

        Returns:
            一致した行の辞書。見つからない場合は None。
        """
        data = self._load()
        self._validate_columns(data, [key_col])
        target = str(value)
        for row in data:
            # CSV の値は常に文字列。int 等を渡されても取りこぼさないよう文字列で比較する
            if str(row.get(key_col, "")) == target:
                return row
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
        self._validate_columns(data, [key_col])
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
        self._validate_columns(data, [col_name])
        return [row[col_name] for row in data]

    def index(self, key_col: str) -> dict[str, dict[str, str]]:
        """key_col をキーにした辞書を返す。

        Excel との突合など、キーで素早く行を引きたい場合に使う。
        キーが重複する場合は後の行で上書きされる。

        Args:
            key_col: キーとして使う列名。

        Returns:
            {キー値: 行の辞書} の形式の辞書。
        """
        data = self._load()
        self._validate_columns(data, [key_col])
        return {row[key_col]: row for row in data}
