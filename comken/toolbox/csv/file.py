"""comken/toolbox/csv/file.py — CSV ファイルを1つのデータ領域として扱う。"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast

from comken.core.encoding import CP932, UTF8, UTF8_SIG, normalize_encoding
from comken.core.files import atomic_write
from comken.core.table.model import Table
from comken.core.timer import measure
from comken.core.types import Row, TypeMap, Value
from comken.exceptions.files import (
    ComkenFileNotFoundError,
    CSVError,
    UnsupportedFileSuffixError,
)
from comken.exceptions.tables import InvalidTableInputError, TableError
from comken.runtime import is_dry_run

logger = logging.getLogger(__name__)

# 追記のとき、見出し行と文字コードを調べるために読むバイト数。全件は読まない
_APPEND_HEAD_BYTES = 64 * 1024


def _table_not_open_error(table_type: str) -> TableError:
    """``TableError`` の「with 文の外で表を操作した」文言。

    ``with`` の中で使うべきテーブルを、外で操作したときに使う。CSV は
    ``__enter__`` でファイルを開き、``__exit__`` で書き出すため、
    外で開くとファイルが閉じている。
    """
    return TableError(
        f"{table_type} は with 文の中で使ってください。"
        "\n対処: with 文の中で使う（CSV / Excel などは __enter__ で表を開く）。"
    )


def _read_only_write_error() -> TableError:
    """``TableError`` の「read_only のテーブルに書き込もうとした」文言。"""
    return TableError(
        "read_only=True のCSVには書き込めません。"
        "\n対処: 対象が読み取り専用でないか確認してください。"
        "書き込みたいときは read_only=True を外してください。"
    )


def _missing_header_message(path: Path) -> str:
    """``CSVError`` の「見出し行が無い」文言。"""
    return (
        f"CSV に見出し行がありません: {path}\n"
        "columns を指定するか、見出し行を追加してください。"
        "\n対処: 見出し行を追加するか、ヘッダーなし CSV なら columns を指定してください。"
    )


def _invalid_header_message(path: Path, reason: str) -> str:
    """``CSVError`` の「見出しに空欄・重複がある」文言。"""
    return (
        f"CSV の見出しが不正です: {path}\n{reason}"
        "\n対処: 1行目にある空欄・重複した見出しを直してください。"
        "新規 CSV に書き出すときは CSV(columns=[...]) で列を指定してください。"
    )


def _columns_required_message(path: Path) -> str:
    """``CSVError`` の「空 CSV に列を決定できない」文言。"""
    return (
        f"空の新規 CSV の列を決定できません: {path}\n"
        "CSV(columns=[...]) を指定してください。"
        "\n対処: 新規 CSV に書き出すときは CSV(columns=[...]) で列を指定してください。"
    )


def _row_length_error(path: Path, line_number: int, expected: int, actual: int) -> CSVError:
    """``CSVError`` の「データ行の列数が見出し数と一致しない」文言。"""
    return CSVError(
        f"CSV の{line_number}行目は列数が一致しません: {path}\n"
        f"見出しは{expected}列、データは{actual}列です。"
        "\n対処: 表示された行の区切り文字と値の数を確認してください。"
    )


def _encoding_detection_error(path: Path) -> CSVError:
    """``CSVError`` の「文字コードを判定できない」文言。"""
    return CSVError(
        "文字コードを判定できませんでした（UTF-8 / CP932 のどちらでも読めません）: "
        f"{path}\nencoding 引数で明示してください。"
        "\n対処: CSV の保存形式を確認し、管理者へ連絡してください。"
    )


def _inspect_csv_head(head: bytes) -> tuple[list[str], str, str] | None:
    """ファイルの先頭から ``(見出し, 文字コード, 改行)`` を読む。決められなければ ``None``。

    文字コードは、BOM 付きなら ``utf-8-sig``、見出しに ASCII 以外があれば ``utf-8`` →
    ``cp932`` の順。見出しが ASCII だけで BOM も無いものは、先頭だけでは決められないので ``None``
    （全件を書き直す経路は、こういうファイルを UTF-8 BOM 付きにそろえる約束がある）。
    """
    has_bom = head.startswith(b"\xef\xbb\xbf")
    body = head[3:] if has_bom else head
    newline_at = body.find(b"\n")
    if newline_at == -1:
        return None
    line = body[:newline_at]
    terminator = "\n"
    if line.endswith(b"\r"):
        line = line[:-1]
        terminator = "\r\n"
    if has_bom:
        encoding, text = UTF8_SIG, line.decode(UTF8, errors="replace")
    elif line.isascii():
        return None
    else:
        for candidate in (UTF8, CP932):
            try:
                text = line.decode(candidate)
            except UnicodeDecodeError:
                continue
            encoding = candidate
            break
        else:
            return None
    if text.count('"') % 2:
        return None
    parsed = list(csv.reader([text]))
    if len(parsed) != 1:
        return None
    return parsed[0], encoding, terminator


def _unencodable_error(
    path: Path, encoding: str, exc: UnicodeEncodeError
) -> InvalidTableInputError:
    """保った文字コードで表せない文字があるときのエラー（``?`` への暗黙の置換はしない）。"""
    offending = repr(exc.object[exc.start : exc.end])
    return InvalidTableInputError(
        f"CSV を {encoding} で書き込めません（保った文字コードで表せない文字があります）: "
        f"{path}\n"
        f"表せない文字: {offending}\n"
        "対処: ファイルを UTF-8 (BOM 付き) で保存し直すか、"
        "表せない文字を含む行を修正してください。"
    )


def _encoding_mismatch_error(path: Path, detected: str) -> CSVError:
    """``CSVError`` の「先頭で判定した文字コードと途中の行が一致しない」文言。"""
    return CSVError(
        f"CSV の途中から判定した文字コード {detected!r} で読めない行があります: {path}"
        "\n対処: encoding= 引数で文字コード（cp932 / utf-8-sig / utf-8 など）を明示してください。"
    )


_CSV_DETECTION_HEAD_BYTES = 1024 * 1024


def _trim_incomplete_multibyte_tail(raw: bytes) -> bytes:
    """末尾の不完全なマルチバイトシーケンスを切り詰める。

    ファイル先頭から 1 MiB を読み出したとき、その境界で UTF-8 や CP932 の
    文字が切れていると ``raw.decode("utf-8")`` / ``raw.decode("cp932")`` が
    失敗し、``_detect_csv_encoding`` が誤判定する（切れたバイトをゴミとして
    扱い、違う文字コードと判定される）。末尾から「両方の codec が strict で
    復号できる最後の位置」を見つけて切り詰めることで、境界にある曖昧さだけを
    取り除き、判定材料はできるかぎり残す。
    """
    if not raw:
        return raw
    n = len(raw)
    # 末尾の UTF-8 は最大 4 バイト、CP932 は最大 2 バイト。
    # 8 バイト以内のトリムで必ず安全な位置が見つかる想定で走査する。
    for trim in range(8):
        if trim >= n:
            break
        candidate = raw[: n - trim]
        try:
            candidate.decode(UTF8)
        except UnicodeDecodeError:
            continue
        try:
            candidate.decode(CP932)
        except UnicodeDecodeError:
            continue
        return candidate
    return raw[: max(n - 8, 0)]


def _detect_csv_encoding(raw: bytes) -> str | None:
    """CSV バイト列の文字コードを推定する（読み込みと書き込みで共有）。

    戻り値:

    - ``utf-8-sig``: 先頭が UTF-8 BOM
    - ``utf-8``: BOM が無く、非 ASCII を含み UTF-8 として読める
    - ``cp932``: 上記以外で CP932 として読める
    - ``None``: 空 / 全部 ASCII（BOM なし）/ どちらも読めない

    読み込み時は ``utf-8-sig`` codec を使い（``utf-8`` 判定の場合も
    BOM の有無を codec が吸収する）、書き込み時は BOM の有無を保ったまま
    codec を選ぶ。``None`` の場合は読み込み・書き込みとも既定の
    ``utf-8-sig`` にフォールバックする。

    ``read_text()``（読み込み）と ``CSV`` の書き込み（``_write_encoding``）で同じ判定を
    共有する（プログラムが書く分は UTF-8 BOM 付きだが、人が Excel で開いて保存し直すと
    CP932 へ化けることがあるため、読みと書きで規則が食い違わないようにする）。
    """
    if not raw:
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        return UTF8_SIG
    # ASCII だけなら UTF-8 / CP932 どちらも復号でき、区別できない。
    # 呼び出し側で新規ファイルと同じ既定（``utf-8-sig``）を選んでもらう。
    if not any(byte > 0x7F for byte in raw):
        return None
    try:
        raw.decode(UTF8)
        return UTF8
    except UnicodeDecodeError:
        pass
    try:
        raw.decode(CP932)
        return CP932
    except UnicodeDecodeError:
        return None


def read_text(path: str | Path, *, encoding: str | None = None) -> str:
    """CSV ファイルをバイト列として読み、文字コードを判定して文字列を返す。

    文字コードは次の順で試す:

    1. ``encoding`` が ``None`` 以外なら、それをそのまま使う
       （`csv.reader` 側にも渡す想定なので、Python の codec 名を入れる。
       ``normalize_encoding`` で表記ゆれを吸収してから復号する）
    2. ``None``（既定）のときは ``_detect_csv_encoding`` で判定する:
       - ``utf-8-sig`` / ``utf-8`` の判定 → ``utf-8-sig`` codec で復号する
         （``utf-8-sig`` は BOM の有無を codec が吸収する）
       - ``cp932`` の判定 → ``cp932`` codec で復号する
       - 判定不能（空 / 全部 ASCII / どちらも読めない）→
         従来どおり ``utf-8-sig`` → ``cp932`` の順で
         ``UnicodeDecodeError`` をベースに再試行する

    ``None`` でどちらも読めなければ ``CSVError`` を投げる。
    ファイルの存在チェック・空ファイル分岐・BOM 除去などは呼び出し側に
    任せる（``CSV.read()`` では BOM 除去も含めて ``csv.reader`` が処理する）。

    ``CSV`` の読み込みと書き込み（``_write_encoding``）で同じ判定（``_detect_csv_encoding``）を
    共有する（プログラムが書く分は UTF-8 BOM 付きだが、人が Excel で開いて保存し直すと
    CP932 へ化けることがあるため、書き込みでも既存ファイルの文字コードを保つ）。
    """
    path = Path(path)
    raw = path.read_bytes()
    if encoding is not None:
        normalized = normalize_encoding(encoding)
        logger.debug("CSV 読み込み: %s, encoding=%s", path, normalized)
        try:
            return raw.decode(normalized)
        except (LookupError, ValueError) as error:
            # ``normalize_encoding`` は ``ValueError`` を上げる。
            # それ以外の codec 失敗（通常は UnicodeDecodeError）も同じ ``CSVError`` に
            # 揃えて、利用者へ対処法を伝える。
            raise CSVError(_invalid_encoding_message(path, encoding, error)) from error
    detected = _detect_csv_encoding(raw)
    if detected is None:
        # 判定不能（空 / 全部 ASCII）: 従来の utf-8-sig → cp932 の順で再試行する。
        # ASCII ファイルでは utf-8-sig が必ず成功する。
        candidates: tuple[str, ...] = (UTF8_SIG, CP932)
    elif detected == UTF8:
        # BOM なし UTF-8。``utf-8-sig`` codec なら BOM が無くても復号できる。
        candidates = (UTF8_SIG,)
    else:
        # ``utf-8-sig`` (BOM あり) / ``cp932`` の判定結果そのまま。
        candidates = (detected,)
    for candidate in candidates:
        try:
            decoded = raw.decode(candidate)
            logger.debug("CSV 読み込み: %s, encoding=%s (auto)", path, candidate)
            return decoded
        except UnicodeDecodeError:
            continue
    logger.debug("CSV 読み込み: 文字コードを判定できません: %s", path)
    raise _encoding_detection_error(path)


def parse_text(text: str) -> list[list[str]]:
    """CSV 文字列を行ごとに ``list[str]`` へ分解する（comken 内部用）。

    公開 API（``csv/__init__.py`` の ``__all__``）には出さない。Bulk API 2.0 の
    結果 CSV を ``toolbox.salesforce`` から分解するためだけに置く。
    """
    return list(csv.reader(io.StringIO(text)))


def encode_rows_as_bytes(
    rows: list[dict[str, str]],
    *,
    write_bom: bool,
    write_header: bool,
) -> bytes:
    """``rows`` を ``csv.DictWriter`` の Excel ダイヤで ``\\r\\n`` 区切りに書き、
    バイト列で返す（comken 内部用）。

    ``CSV._write`` が ``csv.DictWriter`` で書く出力と同じバイト列になるダイヤ
    （Excel ダイヤ）を使う。 ``atomically ではない`` （``atomic_write`` 経由
    を**しない**）ので、``history.py`` のような「既存ファイルに末尾 1 行だけ
    足す」用途に使える。

    ``write_bom=True`` のときは先頭に BOM を付ける（新規ファイル用）、
    ``False`` のときは BOM を付けない（既存ファイルへの追記用）。
    ``write_header=True`` のときは ``csv.DictWriter.writeheader()`` の出力を
    先頭に書き足す（_新規ファイル_用）。既存ファイルへの追記では
    ``False`` を渡す（見出しは既にファイルにあるので二重に出力しない）。

    文字コードは UTF-8 系（``utf-8-sig`` / ``utf-8``）で、``CSV._write``
    の出力とバイト互換。

    公開 API には出さない（``csv/__init__.py`` の ``__all__`` に入れない）。
    """
    if not rows:
        return b""
    text_buf = io.StringIO(newline="")
    columns = list(rows[0].keys())
    writer = csv.DictWriter(text_buf, fieldnames=columns, extrasaction="raise")
    if write_header:
        writer.writeheader()
    writer.writerows(rows)
    text = text_buf.getvalue()
    if write_bom:
        return text.encode("utf-8-sig")
    return text.encode("utf-8")


def _invalid_encoding_message(path: Path, encoding: str, error: BaseException) -> str:
    """``CSVError`` の「指定された encoding が使えない」文言。"""
    return (
        f"CSV を指定された encoding で読み込めません: {path}\n"
        f"指定された encoding: {encoding!r}\n"
        f"詳細: {error}\n"
        "対処: encoding 引数を省略すると自動判定します。"
        "明示するときは主に cp932 / utf-8-sig / utf-8 を指定してください。"
    )


class CSV:
    """CSV ファイルを1つのデータ領域として読み書きする。

    Table と同じ「行の集合」として ``Table.transfer_from()`` へ渡せる境界を提供する。
    ヘッダーのないファイルは ``columns`` で列名を指定する。

    文字コード:

    - 読み込み時（``encoding=`` を ``None`` にした既定）は
      ``UTF-8 BOM 付き → BOM なし UTF-8 → CP932`` の順で自動判定する。
      詳細は ``read_text`` を参照。
    - 書き込み時は ``encoding=`` を明示すればその codec をそのまま使う。
      明示しない ``None`` のときは、**既存ファイルの文字コードを保つ**
      （BOM 付き UTF-8 は BOM 付きのまま、BOM なし UTF-8 は BOM なしのまま、
      CP932 は CP932 のまま）。新規ファイルや中身が空のファイル、
      ASCII だけで判定できないファイルは ``UTF-8 BOM 付き`` を既定にする。
    - 保った文字コードでは表せない文字を書き込もうとすると、
      ``?`` に置換せず ``InvalidTableInputError`` で停止する。
      このとき一時ファイルは ``atomic_write`` が片付けるため、
      元のファイルは無傷で残る。
    """

    def __init__(
        self,
        source: str | Path,
        *,
        encoding: str | None = None,
        columns: list[str] | None = None,
        types: TypeMap | None = None,
        read_only: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.path = Path(source)
        if self.path.suffix.lower() != ".csv":
            raise UnsupportedFileSuffixError(self.path, (".csv",))
        # ``None`` は「自動判定」、それ以外は表記ゆれを codec 名へそろえてから保持する。
        # 無効な名前はここで ``CSVError`` に揃えて、利用者へ対処法を一緒に伝える。
        if encoding is None:
            self._encoding: str | None = None
        else:
            try:
                self._encoding = normalize_encoding(encoding)
            except ValueError as error:
                raise CSVError(_invalid_encoding_message(self.path, encoding, error)) from error
        self._columns = list(columns) if columns is not None else None
        self._types = dict(types or {})
        self._read_only = read_only
        self._dry_run = dry_run
        self._pending: Table | None = None
        # 既存ファイルへ「行を足すだけ」のときの保留。ファイルの中身は読まず、足す行だけを
        # 持つ（確定時にファイルの末尾へ書き足す）。``_plan_in_place_append`` が参照
        self._appended: Table | None = None
        # 末尾へ書き足すときの (文字コード, 改行) 。``_appended`` と同時に入る
        self._append_plan: tuple[str, str] | None = None
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
        if exc_type is None and not (self._read_only or self._dry_run or is_dry_run()):
            if self._appended is not None:
                logger.debug("CSV withブロック終了時に追記分を書き足し: %s", self.path)
                self._flush_appended()
            elif self._pending is not None:
                logger.debug("CSV withブロック終了時に保留内容を書き出し: %s", self.path)
                self._write(self._pending)
        self._is_open = False

    def _ensure_open(self) -> None:
        if not self._is_open:
            raise _table_not_open_error("CSV")

    @measure
    def read(self) -> Table:
        """全行を読み、指定された列だけを変換したTableを返す。

        ファイルの内容を**全件メモリに展開**する。行数が大きいファイル
        （目安: 1 万行を超えるもの）は ``iter_rows()`` を使い、1 行ずつ処理する
        ことでメモリ消費を抑える。``iter_rows()`` は列名も返さないので、
        列名は ``read()`` または ``columns`` 引数で先に取っておく。
        """
        self._ensure_open()
        self._materialize_appended()
        if self._pending is not None:
            # replace/write の結果は保存前でも、同じ処理中の「現在の Table」として読める。
            logger.debug("CSV read は保留中 Table を返します: %s", self.path)
            return self._pending
        logger.debug("CSV 読み込み開始: %s", self.path)
        if not self.path.exists():
            logger.debug("CSV ファイルが存在しません: %s", self.path)
            raise ComkenFileNotFoundError("CSV ファイル", self.path)
        if self.path.stat().st_size == 0:
            logger.debug("CSV は空ファイルです: %s", self.path)
            if self._columns is None:
                raise CSVError(_missing_header_message(self.path))
            return Table(self._columns, [], types=self._types)
        raw_rows = list(csv.reader(io.StringIO(self._read_text())))
        if not raw_rows and self._columns is None:
            # UTF-8 BOM は文字ではなく署名なので、BOM だけのファイルにも見出しはない。
            raise CSVError(_missing_header_message(self.path))
        columns = self._columns if self._columns is not None else raw_rows.pop(0)
        self._validate_columns(columns)
        first_data_line = 1 if self._columns is not None else 2
        rows: list[dict[str, str]] = []
        for line_number, values in enumerate(raw_rows, start=first_data_line):
            if len(values) != len(columns):
                raise _row_length_error(self.path, line_number, len(columns), len(values))
            rows.append(dict(zip(columns, values, strict=True)))
        logger.debug(
            "CSV 読み込み完了: %s, %d 行, %d 列",
            self.path,
            len(rows),
            len(columns),
        )
        return Table(columns, rows, types=self._types)

    def iter_rows(self) -> Iterator[Row]:
        """CSV を 1 行ずつ ``{列名: 値}`` の dict で返すイテレーター。

        ``read()`` と違ってファイル全体を内存に展開しないため、**行数が大きい
        CSV（数万件以上）**ではこちらを使う。``read()`` と同じく見出し行を
        自動で解釈し、列名は ``csv.DictReader`` の動作に従う。

        列名は戻り値の dict から直接取れない（イテレーターは順番に値を返す
        だけ）。先に ``csv.read().columns`` または ``csv.columns`` 引数で
        列名を取得しておく。

        このメソッドは ``with`` の中でだけ呼ぶこと（``TableError``）。
        文字コードの自動判定（``encoding=None`` のとき）は ``read()`` と
        同じ ``_read_text`` を使う。
        """
        # generator 関数のため body は ``next()`` まで遅延評価される。
        # ``with`` 外での呼び出しを即座に ``TableError`` で止めるため、
        # 先に ``_ensure_open`` だけを実行する内部ヘルパーを通す。
        self._ensure_open()
        return self._iter_rows()

    def _iter_rows(self) -> Iterator[Row]:
        """``iter_rows()`` のジェネレータ本体（事前条件は ``_ensure_open`` が済んでいること）。"""
        self._materialize_appended()
        if self._pending is not None:
            # ``read()`` と同じく保留中の Table を 1 行ずつ返す。読み取り経路で
            # ``replace`` された結果はここでストリーム消費できる。
            logger.debug("CSV iter_rows は保留中 Table を返します: %s", self.path)
            yield from self._pending.to_rows()
            return
        logger.debug("CSV iter_rows 開始: %s", self.path)
        if not self.path.exists():
            raise ComkenFileNotFoundError("CSV ファイル", self.path)
        if self.path.stat().st_size == 0:
            if self._columns is None:
                raise CSVError(_missing_header_message(self.path))
            return
        if self._encoding is None:
            # 自動判定は先頭 1 MiB を読んで ``_detect_csv_encoding`` に渡す。
            # ファイル全体を読み出す ``read_text`` 経由はメモリに全行を載せてしまうため、
            # 数万件以上の CSV では避けたい。境界で切れたマルチバイト文字は
            # ``_trim_incomplete_multibyte_tail`` で取り除いて誤判定を防ぐ。
            with self.path.open("rb") as raw_stream:
                head = raw_stream.read(_CSV_DETECTION_HEAD_BYTES)
            head = _trim_incomplete_multibyte_tail(head)
            detected = _detect_csv_encoding(head)
            if detected is None:
                # 判定不能（空 / 全部 ASCII）: 既存仕様の utf-8-sig を既定にする。
                encoding = UTF8_SIG
            elif detected == UTF8:
                # BOM なし UTF-8。``utf-8-sig`` codec は BOM が無くても復号できる。
                encoding = UTF8_SIG
            else:
                # ``utf-8-sig`` (BOM あり) / ``cp932`` の判定結果そのまま。
                encoding = detected
            logger.debug(
                "CSV iter_rows: 文字コードを自動判定しました: %s, encoding=%s",
                self.path,
                encoding,
            )
            try:
                with self.path.open("r", encoding=encoding, newline="") as text_stream:
                    yield from self._iter_rows_from_source(text_stream)
            except UnicodeDecodeError as error:
                # 先頭 1 MiB から判定した文字コードで、途中のバイト列が読めない。
                # 文字コードを明示してもらうために ``CSVError`` に揃えて送出する。
                logger.debug(
                    "CSV iter_rows: 自動判定した文字コードで読めませんでした: %s, encoding=%s",
                    self.path,
                    encoding,
                )
                raise _encoding_mismatch_error(self.path, encoding) from error
            return
        # encoding が明示されているときはファイルをストリームとして開き、
        # 全体を読み込まずに 1 行ずつ ``DictReader`` に流す。``yield`` を含む
        # 関数内の ``with`` は、ジェネレータの ``close()``/GC 時に自動で閉じる。
        with self.path.open("r", encoding=self._encoding, newline="") as stream:
            yield from self._iter_rows_from_source(stream)

    def _iter_rows_from_source(self, source: io.TextIOBase) -> Iterator[Row]:
        """``DictReader`` の ``source`` を受けて、見出し列の扱いだけを共通化する内部ヘルパー。

        ``source`` は ``io.StringIO`` でも ``Path.open()`` したファイルでも
        ``DictReader`` にとっては同じ iterable なので、AUTO 経路と明示 encoding 経路の
        両方でこのヘルパーを共有する。

        ``csv.DictReader`` は列数が合わない行を検証せず、余分な値は ``None``
        キー配下へリストで積み、不足した列は ``None`` 値で埋めて黙って返す。
        ``read()`` は同じ不正入力を ``CSVError`` にするため、ここでも
        ``DictReader`` の戻り値からその2パターンを検出して揃える
        （1行ずつの ``O(1)`` チェックなので、ストリーミングの利点は損なわない）。
        """
        if self._columns is None:
            reader = csv.DictReader(source)
        else:
            # 列名があらかじめ決まっているときは DictReader の headers を上書きして
            # ``csv.DictReader`` にヘッダー行を読ませない。残るのはデータ行のみ。
            reader = csv.DictReader(source, fieldnames=self._columns)
        first_data_line = 1 if self._columns is not None else 2
        for line_number, row in enumerate(reader, start=first_data_line):
            expected = len(reader.fieldnames or ())
            # 型スタブ上は dict[str, str] だが、列数が多い行では csv.DictReader が
            # 実際には None キー（restkey）へ余分な値のリストを積む。cast() で
            # その実際のありうる形を明示し、ignore で握りつぶさない。
            extra = cast("dict[str | None, Any]", row).pop(None, None)
            if extra is not None:
                raise _row_length_error(self.path, line_number, expected, expected + len(extra))
            missing = sum(1 for value in row.values() if value is None)
            if missing:
                raise _row_length_error(self.path, line_number, expected, expected - missing)
            # DictReader は None を含むキー/値を返さない(上のチェックで排除済み)ので
            # ``dict(row)`` で十分
            yield dict(row)

    def _validate_columns(self, columns: list[str]) -> None:
        if not columns:
            raise CSVError(_missing_header_message(self.path))
        empty = [index for index, column in enumerate(columns, 1) if column == ""]
        if empty:
            raise CSVError(
                _invalid_header_message(self.path, f"空の見出しがあります（{empty}列目）。")
            )
        duplicates = [column for column in dict.fromkeys(columns) if columns.count(column) > 1]
        if duplicates:
            raise CSVError(
                _invalid_header_message(self.path, f"重複する見出しがあります: {duplicates}")
            )

    def _read_text(self) -> str:
        # 汎用ヘルパーに判定を委譲する（履歴CSVなどからも同じロジックを使う）
        return read_text(self.path, encoding=self._encoding)

    def replace(self, rows: list[dict[str, Value]] | Table) -> None:
        """ファイルのデータ領域を全置換する。"""
        self._ensure_open()
        if self._read_only:
            raise _read_only_write_error()
        if not isinstance(rows, (list, Table)):
            raise InvalidTableInputError("CSV の置換には Table または行リストを指定してください。")
        self._materialize_appended()
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
                raise CSVError(_columns_required_message(self.path))
            table = Table(columns, [], types=self._types)
        self._pending = table
        logger.debug(
            "CSV replace を保留: %s, %d 行, %d 列",
            self.path,
            len(table),
            len(table.columns),
        )
        # replace は計画を作るだけにする。途中で例外が起きたときに、
        # それまでの一部だけがファイルへ残ると復旧しにくいためである。

    def append(self, rows: list[dict[str, Value]] | dict[str, Value] | Table) -> None:
        """行を保留して追加する。確定は save または with 正常終了で行う。

        既存ファイルの文字コードが見出しから決まるとき（BOM 付き UTF-8、見出しに日本語が
        ある UTF-8 / CP932）で、``columns=`` と ``types=`` を指定していないときは、
        **ファイルの中身を読まず**、確定のときに末尾へ書き足す（行数によらず一定の時間）。
        それ以外は、従来どおり全件を読んで書き直す。追記のあとに ``read()`` などを
        呼ぶと、そこで初めてファイルを読む。
        """
        self._ensure_open()
        if self._read_only:
            raise _read_only_write_error()
        if isinstance(rows, Table):
            additions = rows.to_rows()
        elif isinstance(rows, dict):
            additions = [rows]
        elif isinstance(rows, list):
            additions = rows
        else:
            raise InvalidTableInputError(
                "CSV の追記には Table、1行、または行リストを指定してください。"
            )
        if self._appended is not None:
            self._appended.append(additions)
            logger.debug(
                "CSV append を保留（末尾へ書き足し）: %s, +%d 行", self.path, len(additions)
            )
            return
        plan = self._plan_in_place_append()
        if plan is not None:
            # ファイルの中身は読まない。足す行だけを持っておき、確定のときに末尾へ書き足す
            columns, encoding, terminator = plan
            staged = Table(columns, [])
            staged.append(additions)
            self._appended = staged
            self._append_plan = (encoding, terminator)
            logger.debug(
                "CSV append を保留（末尾へ書き足し）: %s, +%d 行", self.path, len(additions)
            )
            return
        if self._pending is not None or self.path.exists():
            current = self.read()
        elif self._columns is not None:
            current = Table(self._columns, [], types=self._types)
        else:
            raise ComkenFileNotFoundError("CSV ファイル", self.path)
        current.append(additions)
        self._pending = current
        logger.debug(
            "CSV append を保留: %s, +%d 行 (合計 %d 行)",
            self.path,
            len(additions),
            len(current),
        )

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
        if self._read_only or self._dry_run or is_dry_run():
            return
        if self._appended is not None:
            self._flush_appended()
        elif self._pending is not None:
            self._write(self._pending)
            self._pending = None

    def _plan_in_place_append(self) -> tuple[list[str], str, str] | None:
        """既存ファイルの末尾へ、行を足すだけで済むかを調べる（内部用）。

        足せるときは ``(列名, 書き足す文字コード, 改行)`` を返す。足せないとき
        （従来どおり全件を読んで書き直す）は ``None``。**ファイルの先頭だけを読み**、
        全件は読まない。次のどれかに当たるときは ``None``:

        - すでに保留中の内容がある、``columns=`` や ``types=`` を指定している
          （見出しの無いファイル・値の変換は、全件を書き直す従来の経路が担当する）
        - ファイルが無い・空・先頭 64 KiB に見出し行の終わりが無い・見出しの引用符が閉じていない
        - 文字コードが先頭だけでは決められない（見出しが ASCII だけで BOM も無い。全件を書き直す
          経路は、こういうファイルを UTF-8 BOM 付きにそろえる約束がある）、または ``encoding=`` の
          明示がファイルの文字コードと違う（変換して書き直す必要がある）
        """
        if self._pending is not None or self._columns is not None or self._types:
            return None
        try:
            if not self.path.is_file() or self.path.stat().st_size == 0:
                return None
            with self.path.open("rb") as binary:
                head = binary.read(_APPEND_HEAD_BYTES)
        except OSError:
            return None
        inspected = _inspect_csv_head(head)
        if inspected is None:
            return None
        columns, header_encoding, terminator = inspected
        self._validate_columns(columns)
        if self._encoding is not None and self._encoding != header_encoding:
            # 明示した文字コードがファイルのものと違えば、変換して全件を書き直す従来の経路へ
            return None
        # BOM はファイルの先頭にだけあればよい。書き足す分には付けない
        return columns, (UTF8 if header_encoding == UTF8_SIG else header_encoding), terminator

    def _flush_appended(self) -> None:
        """``_plan_in_place_append`` で保留した行を、ファイルの末尾へ書き足す（内部用）。"""
        table, plan = self._appended, self._append_plan
        self._appended = None
        self._append_plan = None
        if table is None or plan is None or len(table) == 0:
            return
        encoding, terminator = plan
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(
            buffer, fieldnames=table.columns, extrasaction="raise", lineterminator=terminator
        )
        writer.writerows(table.to_rows())
        try:
            payload = buffer.getvalue().encode(encoding)
        except UnicodeEncodeError as exc:
            raise _unencodable_error(self.path, encoding, exc) from exc
        logger.debug("CSV 書き足し: %s, +%d 行, encoding=%s", self.path, len(table), encoding)
        with self.path.open("r+b") as binary:
            binary.seek(0, io.SEEK_END)
            if binary.tell() > 0:
                # 前回の書き込みが途中で切れて末尾が改行で終わっていないときは、
                # 改行を足してから書く
                binary.seek(-1, io.SEEK_END)
                if binary.read(1) != b"\n":
                    binary.write(terminator.encode("ascii"))
            binary.write(payload)

    def _materialize_appended(self) -> None:
        """保留した「足すだけの行」を、全件の Table（``_pending``）に展開する（内部用）。

        追記のあとに ``read()`` / ``iter_rows()`` / ``replace()`` が呼ばれたとき、
        「ファイルの中身 + 足した行」を返す必要があるので、そこで初めてファイルを読む。
        """
        if self._appended is None:
            return
        additions = self._appended.to_rows()
        self._appended = None
        self._append_plan = None
        current = self.read()
        current.append(additions)
        self._pending = current

    def _write(self, table: Table) -> None:
        encoding = self._write_encoding
        logger.debug(
            "CSV 書き込み: %s, %d 行, %d 列, encoding=%s",
            self.path,
            len(table),
            len(table.columns),
            encoding,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with (
                atomic_write(self.path) as temporary_path,
                temporary_path.open("w", encoding=encoding, newline="") as file,
            ):
                if not table.columns:
                    return
                writer = csv.DictWriter(file, fieldnames=table.columns, extrasaction="raise")
                writer.writeheader()
                writer.writerows(table.to_rows())
        except UnicodeEncodeError as exc:
            # 保った文字コード（``encoding``）で表せない文字が含まれている。
            # ``atomic_write`` が一時ファイルを片付けるので、元のファイルは
            # 置き換えられずに無傷で残る。``?`` への暗黙の置換はしない。
            raise _unencodable_error(self.path, encoding, exc) from exc

    @property
    def _write_encoding(self) -> str:
        """書き込む codec を返す。

        - ``encoding=`` を明示したときはその値をそのまま使う（読み込みと同じ指定）。
        - ``encoding=None`` のとき、書き込み先が既存ファイルなら
          ``_detect_csv_encoding`` で文字コードを判定して保ったまま書き込む
          （UTF-8 BOM 付き → BOM 付き UTF-8、BOM なし UTF-8 → BOM なし UTF-8、
          CP932 → CP932）。新規ファイルや中身が無いファイル、
          ASCII だけで判定できないファイルは ``UTF-8 BOM 付き`` を既定にする。

        ``encoding`` を明示した ``CSV`` でも、保った codec と同じ理由で表せない
        文字を書き込もうとすると ``_write`` が ``InvalidTableInputError``
        を投げる（黙って ``?`` に置換しない）。
        """
        if self._encoding is not None:
            return self._encoding
        if not self.path.exists() or self.path.stat().st_size == 0:
            # 既存ファイルが無い、または中身が無い。判定しようがないので
            # 新規ファイルと同じ既定（``utf-8-sig``）にする。
            return UTF8_SIG
        detected = _detect_csv_encoding(self.path.read_bytes())
        # 判定不能（全部 ASCII / どちらも読めない）は既定の ``utf-8-sig`` に
        # フォールバックする。
        return detected if detected is not None else UTF8_SIG

    def count(self) -> int:
        """データ行数を返す。"""
        self._ensure_open()
        return len(self._pending) if self._pending is not None else len(self.read())
