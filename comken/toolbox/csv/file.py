"""comken/toolbox/csv/file.py — CSV ファイルを1つのデータ領域として扱う。"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, Self, TypeAlias

from comken.constants import Encoding
from comken.core.files import atomic_write
from comken.core.table.model import Table
from comken.core.timer import measure
from comken.exceptions.csv import (
    CSVColumnsRequiredError,
    CSVFileNotFoundError,
    CSVHeaderMissingError,
    CSVInvalidHeaderError,
    CSVRowLengthError,
    EncodingDetectionError,
)
from comken.exceptions.file import UnsupportedFileSuffixError
from comken.exceptions.table import (
    InvalidTableInputError,
    InvalidTableOperationError,
    TableNotOpenError,
)
from comken.runtime import is_dry_run

Value: TypeAlias = str | int | float | bool


class CSV:
    """CSV ファイルを1つのデータ領域として読み書きする。

    Table と同じ「行の集合」として Transfer へ渡せる境界を提供する。
    ヘッダーのないファイルは ``columns`` で列名を指定する。
    """

    def __init__(
        self,
        source: str | Path,
        *,
        encoding: str = Encoding.AUTO,
        columns: list[str] | None = None,
        types: Mapping[str, Callable[[Any], Any]] | None = None,
        read_only: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.path = Path(source)
        if self.path.suffix.lower() != ".csv":
            raise UnsupportedFileSuffixError(self.path, (".csv",))
        self._encoding = encoding
        self._columns = list(columns) if columns is not None else None
        self._types = dict(types or {})
        self._read_only = read_only
        self._dry_run = dry_run
        self._pending: Table | None = None
        # ``with`` の中だけで操作させるため、開いたかどうかを追跡する。
        self._is_open = False

    def __enter__(self) -> Self:
        self._is_open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if (
            exc_type is None
            and not (self._read_only or self._dry_run or is_dry_run())
            and self._pending is not None
        ):
            self._write(self._pending)
        self._is_open = False

    def _ensure_open(self) -> None:
        if not self._is_open:
            raise TableNotOpenError("CSV")

    @measure
    def read(self) -> Table:
        """全行を読み、指定された列だけを変換したTableを返す。

        ファイルの内容を**全件メモリに展開**する。行数が大きいファイル
        （目安: 1 万行を超えるもの）は ``read_rows()`` を使い、1 行ずつ処理する
        ことでメモリ消費を抑える。``read_rows()`` は列名も返さないので、
        列名は ``read()`` または ``columns`` 引数で先に取っておく。
        """
        self._ensure_open()
        if self._pending is not None:
            # replace/write の結果は保存前でも、同じ処理中の「現在の Table」として読める。
            return self._pending
        if not self.path.exists():
            raise CSVFileNotFoundError(self.path)
        if self.path.stat().st_size == 0:
            if self._columns is None:
                raise CSVHeaderMissingError(self.path)
            return Table(self._columns, [], types=self._types)
        raw_rows = list(csv.reader(io.StringIO(self._read_text())))
        if not raw_rows and self._columns is None:
            # UTF-8 BOM は文字ではなく署名なので、BOM だけのファイルにも見出しはない。
            raise CSVHeaderMissingError(self.path)
        columns = self._columns if self._columns is not None else raw_rows.pop(0)
        self._validate_columns(columns)
        first_data_line = 1 if self._columns is not None else 2
        rows: list[dict[str, str]] = []
        for line_number, values in enumerate(raw_rows, start=first_data_line):
            if len(values) != len(columns):
                raise CSVRowLengthError(self.path, line_number, len(columns), len(values))
            rows.append(dict(zip(columns, values, strict=True)))
        return Table(columns, rows, types=self._types)

    def read_rows(self) -> Iterator[dict[str, str]]:
        """CSV を 1 行ずつ ``{列名: 値}`` の dict で返すイテレーター。

        ``read()`` と違ってファイル全体を内存に展開しないため、**行数が大きい
        CSV（数万件以上）**ではこちらを使う。``read()`` と同じく見出し行を
        自動で解釈し、列名は ``csv.DictReader`` の動作に従う。

        列名は戻り値の dict から直接取れない（イテレーターは順番に値を返す
        だけ）。先に ``csv.read().columns`` または ``csv.columns`` 引数で
        列名を取得しておく。

        このメソッドは ``with`` の中でだけ呼ぶこと（``TableNotOpenError``）。
        文字コードの自動判定（``Encoding.AUTO`` のとき）は ``read()`` と
        同じ ``_read_text`` を使う。
        """
        # generator 関数のため body は ``next()`` まで遅延評価される。
        # ``with`` 外での呼び出しを即座に ``TableNotOpenError`` で止めるため、
        # 先に ``_ensure_open`` だけを実行する内部ヘルパーを通す。
        self._ensure_open()
        return self._iter_rows()

    def _iter_rows(self) -> Iterator[dict[str, str]]:
        """``read_rows()`` のジェネレータ本体（事前条件は ``_ensure_open`` が済んでいること）。"""
        if self._pending is not None:
            # ``read()`` と同じく保留中の Table を 1 行ずつ返す。読み取り経路で
            # ``replace`` された結果はここでストリーム消費できる。
            yield from self._pending.read_rows()
            return
        if not self.path.exists():
            raise CSVFileNotFoundError(self.path)
        if self.path.stat().st_size == 0:
            if self._columns is None:
                raise CSVHeaderMissingError(self.path)
            return
        text = self._read_text()
        if self._columns is None:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                # DictReader は None を含むキー/値を返さないので ``dict(row)`` で十分
                yield dict(row)
            return
        # 列名があらかじめ決まっているときは DictReader の headers を上書きして
        # ``csv.DictReader`` にヘッダー行を読ませない。残るのはデータ行のみ。
        reader = csv.DictReader(io.StringIO(text), fieldnames=self._columns)
        for row in reader:
            yield dict(row)

    def _validate_columns(self, columns: list[str]) -> None:
        if not columns:
            raise CSVHeaderMissingError(self.path)
        empty = [index for index, column in enumerate(columns, 1) if column == ""]
        if empty:
            raise CSVInvalidHeaderError(self.path, f"空の見出しがあります（{empty}列目）。")
        duplicates = [column for column in dict.fromkeys(columns) if columns.count(column) > 1]
        if duplicates:
            raise CSVInvalidHeaderError(self.path, f"重複する見出しがあります: {duplicates}")

    def _read_text(self) -> str:
        raw = self.path.read_bytes()
        if self._encoding != Encoding.AUTO:
            return raw.decode(self._encoding)
        for encoding in (Encoding.UTF8_SIG, Encoding.CP932):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise EncodingDetectionError(self.path)

    def replace(self, rows: list[dict[str, Value]] | Table) -> None:
        """ファイルのデータ領域を全置換する。"""
        self._ensure_open()
        if self._read_only:
            raise InvalidTableOperationError("read_only=True のCSVには書き込めません。")
        if not isinstance(rows, (list, Table)):
            raise InvalidTableInputError("CSV の置換には Table または行リストを指定してください。")
        if isinstance(rows, Table):
            table = rows
        elif rows:
            columns = self._columns or list(rows[0])
            table = Table(columns, rows, types=self._types)
        else:
            columns = self._columns
            if columns is None and self._pending is not None:
                columns = self._pending.columns
            if columns is None and self.path.exists() and self.path.stat().st_size > 0:
                columns = self.read().columns
            if columns is None:
                raise CSVColumnsRequiredError(self.path)
            table = Table(columns, [], types=self._types)
        self._pending = table
        # replace は計画を作るだけにする。途中で例外が起きたときに、
        # それまでの一部だけがファイルへ残ると復旧しにくいためである。

    def append(self, rows: list[dict[str, Value]] | dict[str, Value] | Table) -> None:
        """行を保留中のTableへ追加する。確定はsaveまたはwith正常終了で行う。"""
        self._ensure_open()
        if self._read_only:
            raise InvalidTableOperationError("read_only=True のCSVには書き込めません。")
        if self._pending is not None or self.path.exists():
            current = self.read()
        elif self._columns is not None:
            current = Table(self._columns, [], types=self._types)
        else:
            raise CSVFileNotFoundError(self.path)
        if isinstance(rows, Table):
            additions = rows.read_rows()
        elif isinstance(rows, dict):
            additions = [rows]
        elif isinstance(rows, list):
            additions = rows
        else:
            raise InvalidTableInputError(
                "CSV の追記には Table、1行、または行リストを指定してください。"
            )
        current.append(additions)
        self._pending = current

    @measure
    def save(self) -> None:
        """保留中のTableをCSVファイルへ保存する。

        長い処理の途中で確定したいときに使う。``with`` を分けて閉じ開きすると、
        共有サーバー上のファイルではロックや同期の問題を自分で作り出すことになるため、
        この経路を残している。``save()`` の後は ``_pending = None`` を立て、
        ``with`` 終了時にもう一度書き込まないようにしている。
        """
        self._ensure_open()
        # replace はメモリ上で準備し、save または正常終了した with でだけファイルへ反映する。
        if (
            self._pending is not None
            and not self._read_only
            and not self._dry_run
            and not is_dry_run()
        ):
            self._write(self._pending)
            self._pending = None

    def _write(self, table: Table) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (
            atomic_write(self.path) as temporary_path,
            temporary_path.open("w", encoding=self._write_encoding, newline="") as file,
        ):
            if not table.columns:
                return
            writer = csv.DictWriter(file, fieldnames=table.columns, extrasaction="raise")
            writer.writeheader()
            writer.writerows(table.read_rows())

    @property
    def _write_encoding(self) -> str:
        return Encoding.UTF8_SIG if self._encoding == Encoding.AUTO else self._encoding

    def count(self) -> int:
        """データ行数を返す。"""
        self._ensure_open()
        return len(self._pending) if self._pending is not None else len(self.read())
